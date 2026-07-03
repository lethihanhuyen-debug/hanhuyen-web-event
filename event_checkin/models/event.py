from datetime import datetime

from event_checkin.models import db


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
