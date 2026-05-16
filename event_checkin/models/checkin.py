from datetime import datetime

from event_checkin.models import db


class CheckIn(db.Model):
    __tablename__ = "checkins"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    registration_id = db.Column(db.Integer, db.ForeignKey("registrations.id"), nullable=False, index=True)
    ma_cbsv = db.Column(db.String(50), nullable=False, index=True)
    ho_ten = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255))
    thoi_gian = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "registration_id": self.registration_id,
            "ma_cbsv": self.ma_cbsv,
            "ho_ten": self.ho_ten,
            "email": self.email,
            "thoi_gian": self.thoi_gian.isoformat() if self.thoi_gian else None,
        }
