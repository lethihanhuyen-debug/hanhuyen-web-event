from datetime import datetime

from event_checkin.models import db


class Registration(db.Model):
    __tablename__ = "registrations"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    ma_cbsv = db.Column(db.String(50), db.ForeignKey("users.ma_cbsv"), nullable=False, index=True)
    ho_ten = db.Column(db.String(255), nullable=False)
    don_vi = db.Column(db.String(255))
    email = db.Column(db.String(255))
    thoi_gian_dang_ky = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "ma_cbsv": self.ma_cbsv,
            "ho_ten": self.ho_ten,
            "don_vi": self.don_vi,
            "email": self.email,
            "thoi_gian_dang_ky": self.thoi_gian_dang_ky.isoformat() if self.thoi_gian_dang_ky else None,
        }
