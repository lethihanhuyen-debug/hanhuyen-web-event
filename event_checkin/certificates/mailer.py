"""Gửi chứng chỉ qua email theo đợt -- chỉ chạy khi admin bấm "Gửi chứng chỉ" ở
trang Danh sách check-in, không còn tự gửi lúc check-in (check-in chỉ lưu mã +
thời gian, xem checkin_controller.py).

- Đợt gửi chạy NỀN phía server (request trả về ngay): admin đóng tab thì vẫn gửi
  tiếp, mở lại trang thấy tiến độ hiện tại qua get_job().
- Gửi TUẦN TỰ từng người (1 luồng duy nhất cho mọi sự kiện), mỗi email cách nhau
  SEND_DELAY_SECONDS giây để không dồn dập SMTP/Gmail.
- Tiến độ + nhật ký giữ trong bộ nhớ tiến trình (app chạy 1 tiến trình waitress).
  Trạng thái thật nằm trên checkin_records: server khởi động lại giữa chừng thì
  người chưa gửi vẫn là 'pending', admin bấm Gửi lại là chạy tiếp, người đã 'sent'
  không bị gửi lại.
- Mỗi patron_code chỉ gửi MỘT lần trong một đợt, kể cả khi chưa bấm Lọc trùng:
  chỉ dòng "chính" được gửi, các lượt quét trùng của cùng mã chuyển 'duplicate'.
  Bảng email_logs vẫn được ghi để lưu lịch sử.
"""
import logging
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from flask import url_for

from event_checkin.certificates.patron_lookup import PatronLookupError, PatronNotFound, lookup_patron
from event_checkin.certificates.service import (
    CertificateError,
    generate_certificate,
    get_certificate_file_path,
    resolve_display_name,
)
from event_checkin.models import db
from event_checkin.models.checkin_record import CheckinRecord
from event_checkin.models.email_log import EmailLog
from event_checkin.models.event import Event
from event_checkin.models.user import User
from event_checkin.utils.email_service import send_checkin_email
from event_checkin.utils.timezone import format_local, now_vn_naive


logger = logging.getLogger(__name__)

EMAIL_TYPE = "checkin_certificate"
EMAIL_SUBJECT = "Xác nhận tham gia sự kiện"
SEND_DELAY_SECONDS = float(os.getenv("CERTIFICATE_EMAIL_DELAY_SECONDS", "2"))
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="certificate-mailer")
_jobs = {}  # event_id -> dict tiến độ + nhật ký của đợt gần nhất
_jobs_lock = threading.Lock()


class CertificateJobError(Exception):
    pass


def primary_record(records):
    """Dòng đại diện cho 1 người trong các lượt quét (đã sắp theo thời gian):
    dòng đã gửi thành công nếu có, nếu không thì lượt quét sớm nhất chưa bị
    đánh dấu trùng."""
    sent = next((item for item in records if item.cert_status == "sent"), None)
    if sent:
        return sent
    return next((item for item in records if item.cert_status != "duplicate"), records[0])


def _records_by_patron(event_id, patron_code=None):
    query = CheckinRecord.query.filter_by(event_id=event_id)
    if patron_code:
        query = query.filter_by(patron_code=patron_code)
    groups = {}
    for item in query.order_by(CheckinRecord.checkin_at.asc(), CheckinRecord.id.asc()).all():
        groups.setdefault(item.patron_code, []).append(item)
    return groups


def patron_summary(event_id):
    """patron_code -> {"primary": dòng đại diện, "first_checkin_at": lượt quét
    sớm nhất (giờ VN), "scans": số lượt quét} cho mọi người đã check-in sự kiện."""
    return {
        code: {
            "primary": primary_record(records),
            "first_checkin_at": records[0].checkin_at,
            "scans": len(records),
        }
        for code, records in _records_by_patron(event_id).items()
    }


def select_targets(event_id, record_ids=None):
    """Danh sách patron_code sẽ gửi, mỗi mã 1 lần, theo thứ tự check-in.
    - Không truyền record_ids: mọi người có dòng chính đang 'pending'.
    - Có record_ids (các dòng admin đang chọn): mã của các dòng đó, bỏ qua dòng
      'duplicate'. Dòng đã 'sent' được chọn tay thì vẫn gửi lại (admin chủ động)."""
    summary = patron_summary(event_id)
    ordered = sorted(summary.items(), key=lambda pair: pair[1]["first_checkin_at"])
    if record_ids is None:
        return [code for code, info in ordered if info["primary"].cert_status == "pending"]
    chosen = {
        item.patron_code
        for item in CheckinRecord.query.filter(
            CheckinRecord.event_id == event_id,
            CheckinRecord.id.in_(record_ids),
            CheckinRecord.cert_status != "duplicate",
        )
    }
    return [code for code, _ in ordered if code in chosen]


def get_job(event_id):
    with _jobs_lock:
        job = _jobs.get(event_id)
        if not job:
            return None
        return {**job, "current": dict(job["current"]) if job["current"] else None, "log": list(job["log"])}


def is_running(event_id):
    with _jobs_lock:
        job = _jobs.get(event_id)
        return bool(job and job["state"] in ("queued", "running"))


def start_job(app, base_url, event_id, record_ids=None):
    """Đưa 1 đợt gửi vào hàng đợi nền và trả về ngay."""
    event = Event.query.get(event_id)
    if not event:
        raise CertificateJobError("Sự kiện không tồn tại.")
    if not (event.certificate_enabled and event.certificate_template):
        raise CertificateJobError("Sự kiện này chưa có mẫu chứng chỉ. Vui lòng tải mẫu lên trước khi gửi.")

    targets = select_targets(event_id, record_ids)
    if not targets:
        raise CertificateJobError(
            "Các dòng đã chọn không có ai để gửi (dòng trùng được bỏ qua)." if record_ids is not None
            else "Không còn ai ở trạng thái 'Chưa gửi'. Muốn gửi lại dòng lỗi, hãy chọn dòng đó rồi bấm Gửi chứng chỉ."
        )

    with _jobs_lock:
        current = _jobs.get(event_id)
        if current and current["state"] in ("queued", "running"):
            raise CertificateJobError("Đang gửi chứng chỉ cho sự kiện này, vui lòng chờ đợt hiện tại xong.")
        job = {
            "state": "queued",
            "total": len(targets),
            "processed": 0,
            "sent": 0,
            "failed": 0,
            "current": None,
            "log": [],
            "started_at": format_local(now_vn_naive(), "%d/%m/%Y %H:%M:%S"),
            "finished_at": None,
        }
        _jobs[event_id] = job

    _executor.submit(_run_job, app, base_url, event_id, targets)
    return get_job(event_id)


def _run_job(app, base_url, event_id, targets):
    # Cần request context (không chỉ app context) vì generate_certificate() và
    # url_for(..., _external=True) gọi url_for() -- test_request_context() tạo
    # một context hợp lệ, rẻ, ngoài request thật, với base_url là domain admin đang dùng.
    with app.test_request_context(base_url=base_url):
        with _jobs_lock:
            _jobs[event_id]["state"] = "running"
        try:
            event = Event.query.get(event_id)
            ten_su_kien = event.ten_su_kien if event else ""
            for index, patron_code in enumerate(targets):
                with _jobs_lock:
                    _jobs[event_id]["current"] = {"code": patron_code, "name": _known_name(event_id, patron_code)}
                result = _send_one(event_id, patron_code, ten_su_kien)
                with _jobs_lock:
                    job = _jobs[event_id]
                    job["processed"] += 1
                    job["sent" if result["ok"] else "failed"] += 1
                    job["log"].append(result)
                if index < len(targets) - 1 and SEND_DELAY_SECONDS > 0:
                    time.sleep(SEND_DELAY_SECONDS)
        except Exception:
            logger.exception("Đợt gửi chứng chỉ cho sự kiện %s bị dừng giữa chừng", event_id)
        finally:
            db.session.remove()
            with _jobs_lock:
                _jobs[event_id].update(
                    state="done", current=None, finished_at=format_local(now_vn_naive(), "%d/%m/%Y %H:%M:%S")
                )


def _known_name(event_id, patron_code):
    """Tên để hiện ở dòng "Đang gửi tới" -- không gọi tra cứu ngoài, chỉ đọc nhanh DB."""
    try:
        record = (
            CheckinRecord.query.filter_by(event_id=event_id, patron_code=patron_code)
            .filter(CheckinRecord.cert_display_name.isnot(None)).first()
        )
        if record:
            return record.cert_display_name
        user = User.query.get(patron_code)
        return user.ho_ten if user else ""
    except Exception:
        return ""


def _send_one(event_id, patron_code, ten_su_kien):
    """Quy trình cho 1 người: tra thông tin -> kiểm tra đủ tên/email -> tạo chứng chỉ
    -> gửi email -> ghi trạng thái lên dòng chính. Không ném lỗi ra ngoài để 1 người
    lỗi không dừng cả đợt. Trả về 1 dòng nhật ký."""
    records = _records_by_patron(event_id, patron_code).get(patron_code)
    if not records:
        # admin đã xoá check-in trong lúc đợt đang chạy
        return _log_entry(patron_code, "", "", False, "Dòng check-in đã bị xoá trong lúc gửi.")
    primary = primary_record(records)
    checkin_at = primary.checkin_at
    email_override = next((item.email_override for item in records if item.email_override), None)

    patron_name = patron_email = None
    certificate = certificate_path = None
    email_sent, error = False, None
    try:
        # a. Tra thông tin (Sierra khi đã tích hợp; hiện là dữ liệu đăng ký)
        info = lookup_patron(patron_code)
        patron_name = info.name or None
        patron_email = email_override or info.email or None
        # b. Thiếu thông tin -> lỗi, chuyển người tiếp theo
        if not patron_name:
            error = "Thiếu họ tên của người nhận."
        elif not patron_email:
            error = "Thiếu email người nhận. Nhập email tay rồi gửi lại."
        elif not EMAIL_PATTERN.match(patron_email):
            error = f"Email không hợp lệ: {patron_email}."
        else:
            # c. Tạo chứng chỉ theo cấu hình đã lưu (Phần 3) -- tên in ưu tiên tên sửa tay
            certificate, _ = generate_certificate(patron_code, event_id=event_id, file_type="pdf")
            certificate_path = get_certificate_file_path(certificate)
            verify_url = url_for("certificates.verify", certificate_code=certificate.certificate_code, _external=True)
            # d. Gửi email: giờ check-in lấy đúng cột checkin_at đã lưu, không phải giờ gửi
            email_sent, error = send_checkin_email(
                resolve_display_name(event_id, patron_code),
                patron_email,
                checkin_at,
                ten_su_kien=ten_su_kien,
                certificate_path=certificate_path,
                certificate_code=certificate.certificate_code,
                verify_url=verify_url,
                return_error=True,
            )
            if not email_sent:
                error = f"Lỗi gửi email: {error}"
    except PatronNotFound as exc:
        error = str(exc)
    except PatronLookupError as exc:
        error = f"Lỗi tra cứu thông tin: {exc}"
    except CertificateError as exc:
        db.session.rollback()
        error = f"Lỗi tạo chứng chỉ: {exc}"
    except Exception as exc:
        db.session.rollback()
        logger.exception("Gửi chứng chỉ thất bại cho %s (sự kiện %s)", patron_code, event_id)
        error = "Có lỗi hệ thống khi gửi chứng chỉ (chi tiết đã ghi ở nhật ký máy chủ). Hãy thử gửi lại, nếu vẫn lỗi hãy báo người quản trị kỹ thuật."

    # e. Ghi trạng thái. generate_certificate() tự commit/rollback nên nạp lại các dòng.
    records = _records_by_patron(event_id, patron_code).get(patron_code)
    if not records:
        return _log_entry(patron_code, patron_name, patron_email, False, "Dòng check-in đã bị xoá trong lúc gửi.")
    primary = primary_record(records)
    for item in records:
        if item is not primary and item.cert_status != "sent":
            item.cert_status = "duplicate"
    if patron_name:
        primary.patron_name = patron_name
    if patron_email:
        primary.patron_email = patron_email
    if email_sent:
        primary.cert_status = "sent"
        primary.cert_sent_at = now_vn_naive()
        primary.send_count = (primary.send_count or 0) + 1
        primary.error_msg = None
    else:
        # Gửi lại cho người đã nhận trước đó mà lỗi thì vẫn giữ 'sent' (họ đã có
        # chứng chỉ), chỉ ghi lại lỗi để admin biết.
        if primary.cert_status != "sent":
            primary.cert_status = "failed"
        primary.error_msg = error

    # email_logs có khoá ngoại sang users -- chỉ ghi lịch sử khi mã có trong users
    # (luôn đúng khi còn bắt buộc đăng ký; sau này check-in qua Sierra có thể không).
    if User.query.get(patron_code):
        db.session.add(EmailLog(
            ma_cbsv=patron_code,
            event_id=event_id,
            email_to=patron_email or "",
            email_type=EMAIL_TYPE,
            subject=EMAIL_SUBJECT,
            certificate_code=certificate.certificate_code if certificate else None,
            attachment_path=str(certificate_path) if certificate_path else None,
            trang_thai="success" if email_sent else "failed",
            error_message=error,
            sent_at=datetime.utcnow(),
        ))
    db.session.commit()
    return _log_entry(patron_code, patron_name, patron_email, email_sent, error)


def _log_entry(patron_code, name, email, ok, reason):
    return {
        "time": format_local(now_vn_naive(), "%H:%M:%S"),
        "code": patron_code,
        "name": name or "",
        "email": email or "",
        "ok": bool(ok),
        "reason": "" if ok else (reason or "Không rõ lý do."),
    }
