from flask import Blueprint, render_template

from event_checkin import permissions as perm
from event_checkin.access import access
from event_checkin.models.event import Event


staff_bp = Blueprint("staff", __name__)

STATUS_LABELS = {"ongoing": "Đang diễn ra", "upcoming": "Sắp diễn ra", "ended": "Đã kết thúc"}


@staff_bp.get("/staff/events")
@access(perm.EVENT_VIEW)
def events_page():
    """Trang đích của staff: danh sách sự kiện CHỈ XEM, mỗi dòng có nút Check-in.
    (Bước b: bản tối thiểu để staff có nơi đến; bước c bổ sung chi tiết sự kiện + danh sách đăng ký đã ẩn liên lạc.)"""
    events = Event.query.order_by(Event.ngay_bat_dau.desc()).all()
    return render_template("staff/events.html", events=events, status_labels=STATUS_LABELS)
