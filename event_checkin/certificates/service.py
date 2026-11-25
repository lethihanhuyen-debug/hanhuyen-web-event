from datetime import datetime
from io import BytesIO
import json
from pathlib import Path

from flask import current_app, url_for
from sqlalchemy import text

from event_checkin.certificates.generator import (
    certificate_values,
    render_certificate_image,
    save_pdf_certificate,
    save_png_certificate,
    save_svg_certificate,
)
from event_checkin.certificates.patron_lookup import PatronLookupError, PatronNotFound, lookup_patron
from event_checkin.certificates.validators import validate_certificate_eligibility
from event_checkin.models import db
from event_checkin.models.certificate import Certificate
from event_checkin.models.checkin_record import CheckinRecord
from event_checkin.models.user import User


DEFAULT_EVENT_ID = 1


class CertificateError(Exception):
    pass


LEGACY_STATIC_PREFIX = "/static/"
LEGACY_GENERATED_DIR = ("certificates", "generated")


def storage_root():
    """Thư mục lưu file chứng chỉ (ngoài static, xem Config.CERTIFICATE_STORAGE_DIR)."""
    return Path(current_app.config["CERTIFICATE_STORAGE_DIR"])


def legacy_storage_root():
    """Thư mục cũ trong static (trước m007). Chỉ còn dùng để đọc dữ liệu chưa chuyển và cho m007."""
    return Path(current_app.static_folder).joinpath(*LEGACY_GENERATED_DIR)


def _relative_path(path):
    return path.relative_to(storage_root()).as_posix()


def _stored_file_path(file_url):
    """Đường dẫn thật của file. file_url mới là đường dẫn tương đối trong storage_root(); dạng cũ
    "/static/certificates/generated/..." (chưa chạy m007) vẫn đọc được từ thư mục static cũ.
    Trả None nếu đường dẫn thoát ra ngoài thư mục cho phép (phòng dữ liệu lạ)."""
    if not file_url:
        return None
    if file_url.startswith(LEGACY_STATIC_PREFIX):
        root = legacy_storage_root()
        path = Path(current_app.static_folder) / file_url[len(LEGACY_STATIC_PREFIX):]
    else:
        root = storage_root()
        path = root / file_url
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return None
    return path


def _max_used_sequence(event_id):
    """Số thứ tự lớn nhất trong các mã chứng chỉ đang có của sự kiện (phần số cuối mã)."""
    highest = 0
    for (code,) in db.session.query(Certificate.certificate_code).filter(Certificate.event_id == event_id):
        tail = (code or "").rsplit("-", 1)[-1]
        if tail.isdigit():
            highest = max(highest, int(tail))
    return highest


def _next_certificate_code(event_id):
    """Mã mới = số thứ tự tiếp theo của bộ đếm events.certificate_seq (chỉ tăng).

    Trước đây lấy "số chứng chỉ hiện có + 1": xóa một chứng chỉ (vd. xóa check-in) làm số đếm giảm, nên mã đã gửi
    cho người A có thể bị cấp lại cho người B (link cũ của A mở ra chứng chỉ của B) hoặc trùng mã -> lỗi UNIQUE.
    Bộ đếm không bao giờ giảm; lần đầu (cột mới = 0) được nâng lên bằng số lớn nhất đang có.
    UPDATE khóa dòng sự kiện tới khi commit nên hai yêu cầu cùng lúc không lấy trùng số."""
    year = datetime.utcnow().year
    db.session.execute(
        text(
            "UPDATE events SET certificate_seq = "
            "CASE WHEN certificate_seq > :used THEN certificate_seq ELSE :used END + 1 WHERE id = :id"
        ),
        {"used": _max_used_sequence(event_id), "id": event_id},
    )
    sequence = db.session.execute(text("SELECT certificate_seq FROM events WHERE id = :id"), {"id": event_id}).scalar()
    return f"USSH-{year}-EVENT{event_id:03d}-{sequence:06d}"


def resolve_display_name(event_id, ma_cbsv):
    """Họ tên in trên chứng chỉ, theo thứ tự ưu tiên:
    1. Tên admin sửa tay (checkin_records.cert_display_name)
    2. Tên tra từ Sierra (chưa tích hợp) / 3. tên lúc đăng ký -- cả hai qua patron_lookup
    """
    records = (
        CheckinRecord.query.filter_by(event_id=event_id, patron_code=ma_cbsv)
        .order_by(CheckinRecord.checkin_at.asc(), CheckinRecord.id.asc())
        .all()
    )
    # Ưu tiên giá trị trên dòng chính (không phải 'duplicate'), phòng khi lọc trùng/xoá
    # dòng làm giá trị nằm lại ở một dòng trùng.
    for item in sorted(records, key=lambda record: record.cert_status == "duplicate"):
        if item.cert_display_name:
            return item.cert_display_name
    try:
        # Bước 2+3: tra Sierra (khi đã tích hợp), hiện tạm là dữ liệu đăng ký -- xem patron_lookup.py
        return lookup_patron(ma_cbsv).name or ma_cbsv
    except (PatronNotFound, PatronLookupError):
        return ma_cbsv


def event_layout(event, layout=None):
    """(đường dẫn ảnh nền, layout đã gắn đường dẫn font) của sự kiện. Truyền layout
    để dùng cấu hình chưa lưu (xem trước trong trình thiết kế) thay cho bản đã lưu."""
    template_path = None
    if event and event.certificate_enabled and event.certificate_template:
        template_path = Path(current_app.static_folder) / event.certificate_template
    if layout is None and event and event.certificate_layout:
        try:
            layout = json.loads(event.certificate_layout)
        except json.JSONDecodeError:
            layout = None
    if isinstance(layout, dict):
        for config in layout.values():
            if isinstance(config, dict) and config.get("font_file"):
                config["font_path"] = str(Path(current_app.static_folder) / config["font_file"])
    if not template_path or not template_path.exists():
        raise CertificateError("Sự kiện này chưa có mẫu giấy chứng nhận. Vui lòng vào Quản trị > Chứng chỉ để tải mẫu lên.")
    return template_path, layout


PREVIEW_SAMPLE = {"student_name": "Nguyễn Văn A", "ma_cbsv": "2456090063", "don_vi": "Công tác xã hội - Nhân học"}


def render_preview_png(event, patron_code=None, display_name=None, layout=None):
    """Ảnh PNG xem trước, vẽ trong bộ nhớ bằng CÙNG hàm vẽ với chứng chỉ gửi thật.
    Không lưu file, không tạo/tốn mã chứng chỉ. Không có patron_code -> dữ liệu mẫu."""
    template_path, layout = event_layout(event, layout)
    issued_at = datetime.utcnow()
    certificate_code = f"USSH-{issued_at.year}-EVENT{event.id:03d}-XXXXXX"
    if patron_code:
        user = User.query.get(patron_code)
        if not user:
            raise CertificateError(f"Không tìm thấy thông tin của mã {patron_code}.")
        existing = Certificate.query.filter_by(ma_cbsv=patron_code, event_id=event.id).first()
        if existing:
            certificate_code = existing.certificate_code
            issued_at = existing.issued_at or issued_at
        name = display_name or resolve_display_name(event.id, patron_code)
        unit = user.ten_don_vi
    else:
        name = display_name or PREVIEW_SAMPLE["student_name"]
        patron_code = PREVIEW_SAMPLE["ma_cbsv"]
        unit = PREVIEW_SAMPLE["don_vi"]

    values = certificate_values(name, patron_code, unit, certificate_code, issued_at, event.ten_su_kien)
    image = render_certificate_image(template_path, values, layout)
    if image is None:
        raise CertificateError("Không thể vẽ chứng chỉ. Vui lòng kiểm tra file mẫu và font chữ.")
    buffer = BytesIO()
    image.save(buffer, "PNG", optimize=False)
    return buffer.getvalue()


def _render_certificate_file(registration, certificate_code, issued_at, requested_type):
    user = registration.user
    event = registration.event
    student_name = resolve_display_name(registration.event_id, registration.ma_cbsv)
    student_unit = user.ten_don_vi if user else ""
    event_name = event.ten_su_kien if event else ""
    template_path, layout = event_layout(event)
    year_dir = storage_root() / str(issued_at.year)
    if requested_type == "pdf":
        output_path = year_dir / f"{certificate_code}.pdf"
        rendered_path = save_pdf_certificate(
            output_path,
            student_name,
            registration.ma_cbsv,
            student_unit,
            certificate_code,
            issued_at,
            template_path=template_path,
            layout=layout,
            event_name=event_name,
        )
        if rendered_path is None:
            raise CertificateError("Không thể tạo PDF chứng nhận. Vui lòng kiểm tra Pillow và file mẫu chứng nhận.")
        return output_path, "pdf"

    output_path = year_dir / f"{certificate_code}.png"
    rendered_path = save_png_certificate(
        output_path,
        student_name,
        registration.ma_cbsv,
        student_unit,
        certificate_code,
        issued_at,
        template_path=template_path,
        layout=layout,
        event_name=event_name,
    )
    if rendered_path is None:
        output_path = year_dir / f"{certificate_code}.svg"
        save_svg_certificate(output_path, student_name, registration.ma_cbsv, student_unit, certificate_code, issued_at)
        return output_path, "svg"
    return output_path, "png"


def generate_certificate(ma_cbsv, event_id=DEFAULT_EVENT_ID, file_type="pdf"):
    event_id = int(event_id or DEFAULT_EVENT_ID)
    requested_type = (file_type or "png").lower()

    existing = Certificate.query.filter_by(ma_cbsv=ma_cbsv, event_id=event_id).first()
    if existing:
        eligible, _, registration = validate_certificate_eligibility(ma_cbsv, event_id)
        if eligible:
            previous_path = _stored_file_path(existing.file_url)
            output_path, actual_type = _render_certificate_file(
                registration,
                existing.certificate_code,
                existing.issued_at or datetime.utcnow(),
                requested_type,
            )
            existing.file_url = _relative_path(output_path)
            existing.file_type = actual_type
            existing.ensure_token()
            db.session.commit()
            if previous_path and previous_path != output_path and previous_path.exists():
                previous_path.unlink(missing_ok=True)
        return existing, False

    eligible, message, registration = validate_certificate_eligibility(ma_cbsv, event_id)
    if not eligible:
        raise CertificateError(message)

    issued_at = datetime.utcnow()
    certificate_code = _next_certificate_code(event_id)
    output_path, actual_type = _render_certificate_file(registration, certificate_code, issued_at, requested_type)

    certificate = Certificate(
        ma_cbsv=registration.ma_cbsv,
        event_id=event_id,
        certificate_code=certificate_code,
        token=Certificate.new_token(),
        file_url=_relative_path(output_path),
        file_type=actual_type,
        status="generated",
        issued_at=issued_at,
        created_at=issued_at,
    )
    db.session.add(certificate)
    db.session.commit()
    return certificate, True


def get_certificate_file_path(certificate):
    return _stored_file_path(certificate.file_url)


def certificate_links(certificate, external=False):
    """Link công khai (theo token) của một chứng chỉ, dùng cho email và trang admin. Chứng chỉ chưa có token
    (dữ liệu trước m007) được sinh token ngay -- người gọi tự commit."""
    token = certificate.ensure_token()
    return {
        "download_url": url_for("certificates.token_download", token=token, _external=external),
        "view_url": url_for("certificates.token_view", token=token, _external=external),
        "verify_url": url_for("certificates.token_verify", token=token, _external=external),
    }
