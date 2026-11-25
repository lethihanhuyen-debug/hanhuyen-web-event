from flask import Blueprint, jsonify, redirect, render_template, request, url_for

from event_checkin import permissions as perm
from event_checkin.access import access, get_current_admin
from event_checkin.models import db
from event_checkin.models.admin import Admin
from event_checkin.models.checkin_record import CheckinRecord
from event_checkin.models.event import Event
from event_checkin.models.registration import Registration
from event_checkin.utils.timezone import format_local, now_vn_naive


CHECKIN_SUCCESS_MESSAGE = "Check-in thành công! Chứng chỉ sẽ được gửi qua email sau sự kiện."

checkin_bp = Blueprint("checkin", __name__)


def _events_open_for_checkin():
    """Sự kiện đang diễn ra hoặc sắp diễn ra, mới nhất trước -- dùng cho trang
    chọn sự kiện ở /checkin khi không có event_id trong URL. computed_status là
    property tính từ giờ hiện tại, không phải cột DB nên phải lọc ở Python."""
    events = Event.query.order_by(Event.ngay_bat_dau.asc()).all()
    # Gồm cả sự kiện vừa kết thúc còn trong thời gian cho phép check-in (CHECKIN_GRACE_HOURS)
    order = {"open": 0, "grace": 1, "upcoming": 2}
    open_events = [e for e in events if e.checkin_state in order]
    open_events.sort(key=lambda e: (order[e.checkin_state], e.ngay_bat_dau))
    return open_events


def _duplicate_payload(first, ma_cbsv, now):
    """Phản hồi cho lần quét một mã ĐÃ check-in trước đó: vẫn là success (lượt quét đã được ghi như thiết kế cũ) nhưng
    kèm cảnh báo "đã check-in lúc HH:mm bởi [tên]" để staff biết ngay."""
    by_name = "không rõ người thực hiện"
    if first.checked_in_by:
        by = db.session.get(Admin, first.checked_in_by)
        if by:
            by_name = by.username
    when = format_local(first.checkin_at, "%H:%M")
    if first.checkin_at.date() != now.date():
        when += " ngày " + format_local(first.checkin_at, "%d/%m/%Y")
    return {
        "success": True,
        "already_checked_in": True,
        "first_checkin_at": when,
        "first_checkin_by": by_name,
        "message": f"Mã {ma_cbsv} đã check-in lúc {when} bởi {by_name}. Lượt quét này vẫn được ghi lại; người này chỉ nhận một chứng chỉ.",
    }


@checkin_bp.get("/checkin")
@access(perm.CHECKIN_PERFORM)
def index():
    # Không còn suy đoán event_id=1 khi thiếu -- nếu chỉ có đúng 1 sự kiện đang
    # diễn ra/sắp diễn ra thì vào thẳng luôn cho tiện, nếu có nhiều hơn (nhiều
    # địa điểm/sự kiện cùng lúc) thì bắt buộc chọn để tránh check-in nhầm sự kiện.
    open_events = _events_open_for_checkin()
    if len(open_events) == 1:
        return redirect(url_for("checkin.event_index", event_id=open_events[0].id))
    return render_template("checkin/select_event.html", events=open_events)


@checkin_bp.get("/checkin/<int:event_id>")
@access(perm.CHECKIN_PERFORM)
def event_index(event_id):
    event = Event.query.get_or_404(event_id)
    return render_template("checkin/index.html", event=event)


@checkin_bp.post("/api/checkin")
@access(perm.CHECKIN_PERFORM)
def checkin():
    payload = request.get_json(silent=True) or request.form
    ma_cbsv = (payload.get("ma_cbsv") or "").strip()

    if not ma_cbsv:
        return jsonify({"success": False, "message": "Vui lòng nhập mã CB/SV."}), 400

    # Không còn mặc định event_id=1 khi thiếu -- trang /checkin/<event_id> luôn
    # gửi kèm event_id thật, thiếu/sai coi là lỗi thay vì âm thầm check-in nhầm
    # vào sự kiện #1 (xem checkin/index.html).
    try:
        event_id = int(payload.get("event_id"))
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Thiếu hoặc sai event_id."}), 400

    if not Event.query.get(event_id):
        return jsonify({"success": False, "message": "Sự kiện không tồn tại."}), 404

    # Vẫn bắt buộc đã đăng ký sự kiện (1 truy vấn theo UNIQUE index, rất nhanh) vì
    # chưa tích hợp Sierra: họ tên/email để gửi chứng chỉ lấy từ dữ liệu đăng ký.
    registration = Registration.active().filter_by(ma_cbsv=ma_cbsv, event_id=event_id).first()  # đã hủy = chưa đăng ký
    if not registration:
        return jsonify({"success": False, "message": f"Mã {ma_cbsv} chưa đăng ký sự kiện này."}), 404

    # Cùng quy tắc với giao diện (Event.checkin_state): kết thúc rồi vẫn check-in được đến CHECKIN_GRACE_HOURS sau;
    # quá mốc đó chỉ admin thêm tay (POST /api/admin/events/<id>/checkins).
    state = registration.event.checkin_state if registration.event else None
    if state == "upcoming":
        return jsonify({"success": False, "message": "Sự kiện chưa bắt đầu, chưa thể check-in."}), 400
    if state == "closed":
        return jsonify({"success": False, "message": (
            f"Sự kiện đã kết thúc lúc {registration.event.ended_label} và đã quá thời gian cho phép check-in "
            f"(đến {registration.event.checkin_deadline_label}). Vui lòng báo admin để thêm check-in thủ công."
        )}), 400

    # Chỉ INSERT 1 dòng, KHÔNG chặn quét trùng (dòng trùng được đánh dấu 'duplicate' lúc gửi chứng chỉ), không
    # tạo chứng chỉ, không gửi email -- việc đó do admin bấm "Gửi chứng chỉ" (certificates/mailer.py).
    # Giờ check-in luôn do server tạo theo giờ Việt Nam, không nhận từ client. checked_in_by = tài khoản đang đăng nhập.
    admin = get_current_admin()
    record = CheckinRecord(
        event_id=event_id,
        patron_code=ma_cbsv,
        checked_in_by=admin.id,
        checkin_at=now_vn_naive(),
        cert_status="pending",
    )
    db.session.add(record)
    db.session.commit()

    # Nhận diện quét trùng SAU khi ghi: lượt quét "đầu tiên" là dòng sớm nhất (theo giờ, rồi theo id). Nếu dòng vừa ghi
    # không phải dòng đó thì đây là lần quét trùng. Làm sau khi ghi (thay vì kiểm tra trước) để 2 staff quét cùng
    # lúc vẫn nhất quán: dòng ghi sau luôn thấy dòng ghi trước, không ai bị bỏ sót cảnh báo.
    first = (
        CheckinRecord.query
        .filter_by(event_id=event_id, patron_code=ma_cbsv)
        .order_by(CheckinRecord.checkin_at.asc(), CheckinRecord.id.asc())
        .first()
    )
    if first is not None and first.id != record.id:
        return jsonify(_duplicate_payload(first, ma_cbsv, record.checkin_at))

    return jsonify({"success": True, "already_checked_in": False, "message": CHECKIN_SUCCESS_MESSAGE})
