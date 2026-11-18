from flask import Blueprint, render_template

from event_checkin import permissions as perm
from event_checkin.access import access
from event_checkin.certificates import mailer
from event_checkin.models.event import Event
from event_checkin.models.registration import Registration
from event_checkin.utils.timezone import format_local


staff_bp = Blueprint("staff", __name__)

STATUS_LABELS = {"ongoing": "Đang diễn ra", "upcoming": "Sắp diễn ra", "ended": "Đã kết thúc"}


@staff_bp.get("/staff/events")
@access(perm.EVENT_VIEW)
def events_page():
    """Trang đích của staff: danh sách sự kiện CHỈ XEM. Mỗi sự kiện có nút "Xem danh sách" và nút "Check-in"
    (mở trang check-in /checkin/<id> giữ nguyên như cũ)."""
    events = Event.query.order_by(Event.ngay_bat_dau.desc()).all()
    return render_template("staff/events.html", events=events, status_labels=STATUS_LABELS)


@staff_bp.get("/staff/events/<int:event_id>")
@access(perm.EVENT_VIEW)
def event_page(event_id):
    """Chi tiết sự kiện CHỈ XEM cho staff: người đăng ký + trạng thái/giờ check-in.

    Chủ ý CHỈ lấy các cột cần cho việc check-in (mã, họ tên, đơn vị, check-in hay chưa, giờ check-in) -- không đưa
    email, số điện thoại, câu hỏi gửi diễn giả hay trạng thái gửi chứng chỉ vào dữ liệu trả về, nên dù xem mã nguồn
    trang cũng không lộ. Dữ liệu dựng sẵn ở server (không có API riêng cho staff để lộ thêm)."""
    event = Event.query.get_or_404(event_id)
    registrations = (
        Registration.query
        .filter_by(event_id=event_id)
        .order_by(Registration.thoi_gian_dang_ky.asc())
        .all()
    )
    checkin_map = mailer.patron_summary(event_id)

    rows = []
    for position, registration in enumerate(registrations, start=1):
        user = registration.user
        checkin_item = checkin_map.get(registration.ma_cbsv)
        rows.append({
            "stt": position,
            "ma_cbsv": registration.ma_cbsv,
            "ho_ten": user.ho_ten if user else "",
            "don_vi": user.ten_don_vi if user else "",
            "checked_in": bool(checkin_item),
            "checkin_time": format_local(checkin_item["first_checkin_at"]) if checkin_item else "",
        })

    checked = sum(1 for row in rows if row["checked_in"])
    return render_template(
        "staff/event.html",
        event=event,
        status_label=STATUS_LABELS.get(event.computed_status, event.computed_status),
        rows=rows,
        totals={"registrations": len(rows), "checkins": checked, "pending": len(rows) - checked},
    )
