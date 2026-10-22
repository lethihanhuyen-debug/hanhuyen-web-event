from flask import Blueprint, jsonify, redirect, render_template, request, url_for

from event_checkin.models import db
from event_checkin.models.checkin_record import CheckinRecord
from event_checkin.models.event import Event
from event_checkin.models.registration import Registration
from event_checkin.utils.timezone import now_vn_naive


CHECKIN_SUCCESS_MESSAGE = "Check-in thành công! Chứng chỉ sẽ được gửi qua email sau sự kiện."

checkin_bp = Blueprint("checkin", __name__)


def _events_open_for_checkin():
    """Sự kiện đang diễn ra hoặc sắp diễn ra, mới nhất trước -- dùng cho trang
    chọn sự kiện ở /checkin khi không có event_id trong URL. computed_status là
    property tính từ giờ hiện tại, không phải cột DB nên phải lọc ở Python."""
    events = Event.query.order_by(Event.ngay_bat_dau.asc()).all()
    open_events = [e for e in events if e.computed_status in ("ongoing", "upcoming")]
    open_events.sort(key=lambda e: (e.computed_status != "ongoing", e.ngay_bat_dau))
    return open_events


@checkin_bp.get("/checkin")
def index():
    # Không còn suy đoán event_id=1 khi thiếu -- nếu chỉ có đúng 1 sự kiện đang
    # diễn ra/sắp diễn ra thì vào thẳng luôn cho tiện, nếu có nhiều hơn (nhiều
    # địa điểm/sự kiện cùng lúc) thì bắt buộc chọn để tránh check-in nhầm sự kiện.
    open_events = _events_open_for_checkin()
    if len(open_events) == 1:
        return redirect(url_for("checkin.event_index", event_id=open_events[0].id))
    return render_template("checkin/select_event.html", events=open_events)


@checkin_bp.get("/checkin/<int:event_id>")
def event_index(event_id):
    event = Event.query.get_or_404(event_id)
    return render_template("checkin/index.html", event=event)


@checkin_bp.post("/api/checkin")
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
    registration = Registration.query.filter_by(ma_cbsv=ma_cbsv, event_id=event_id).first()
    if not registration:
        return jsonify({"success": False, "message": f"Mã {ma_cbsv} chưa đăng ký sự kiện này."}), 404

    event_status = registration.event.computed_status if registration.event else None
    if event_status == "upcoming":
        return jsonify({"success": False, "message": "Sự kiện chưa bắt đầu, chưa thể check-in."}), 400
    if event_status == "ended":
        return jsonify({"success": False, "message": "Sự kiện đã kết thúc, không thể check-in."}), 400

    # Chỉ INSERT 1 dòng: không kiểm tra quét trùng (dòng trùng được đánh dấu
    # 'duplicate' lúc gửi chứng chỉ), không tra cứu, không tạo chứng chỉ, không
    # gửi email -- việc đó do admin bấm "Gửi chứng chỉ" (certificates/mailer.py).
    # Giờ check-in luôn do server tạo theo giờ Việt Nam, không nhận từ client.
    db.session.add(CheckinRecord(
        event_id=event_id,
        patron_code=ma_cbsv,
        checkin_at=now_vn_naive(),
        cert_status="pending",
    ))
    db.session.commit()

    return jsonify({"success": True, "message": CHECKIN_SUCCESS_MESSAGE})
