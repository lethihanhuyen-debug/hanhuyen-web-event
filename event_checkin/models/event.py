from datetime import datetime

from event_checkin.models import db
from event_checkin.utils.timezone import now_vn_naive


class Event(db.Model):
    __tablename__ = "events"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    ten_su_kien = db.Column(db.String(255), nullable=False)
    hinh = db.Column(db.String(255))
    mo_ta = db.Column(db.Text)
    dia_diem = db.Column(db.String(255))
    ngay_bat_dau = db.Column(db.DateTime, nullable=False)
    ngay_ket_thuc = db.Column(db.DateTime, nullable=False)
    thang = db.Column(db.Integer, nullable=False)
    nam = db.Column(db.Integer, nullable=False)
    thoi_gian_mo_dang_ky = db.Column(db.DateTime, nullable=False)
    thoi_gian_dong_dang_ky = db.Column(db.DateTime, nullable=False)
    trang_thai = db.Column(db.String(50), nullable=False, default="upcoming")
    certificate_enabled = db.Column(db.Boolean, nullable=False, default=True)
    certificate_template = db.Column(db.String(255))
    certificate_layout = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey("admins.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_by = db.Column(db.Integer, db.ForeignKey("admins.id"))
    updated_at = db.Column(db.DateTime)

    @property
    def computed_status(self):
        """Live event status derived from the schedule, not the stored `trang_thai`
        column (which is only a best-effort snapshot) -- always reflects "now".
        """
        now = now_vn_naive()
        if now < self.ngay_bat_dau:
            return "upcoming"
        if now <= self.ngay_ket_thuc:
            return "ongoing"
        return "ended"

    @property
    def registration_block_reason(self):
        """None if registration is currently allowed, otherwise a Vietnamese
        message explaining why (event ended / registration window not open)."""
        if self.computed_status == "ended":
            return "Sự kiện đã kết thúc, không thể đăng ký."
        now = now_vn_naive()
        if now < self.thoi_gian_mo_dang_ky:
            return "Chưa đến thời gian mở đăng ký cho sự kiện này."
        if now > self.thoi_gian_dong_dang_ky:
            return "Đã hết thời gian đăng ký cho sự kiện này."
        return None

    @property
    def is_registration_open(self):
        return self.registration_block_reason is None
