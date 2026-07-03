from datetime import datetime

from event_checkin.models import db


class CheckIn(db.Model):
    __tablename__ = "checkins"
    __table_args__ = (
        db.UniqueConstraint("ma_cbsv", "event_id", name="uq_checkins_user_event"),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    ma_cbsv = db.Column(db.String(50), db.ForeignKey("users.ma_cbsv"), nullable=False, index=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=False, index=True)
    thoi_gian_checkin = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship("User", lazy="joined")
    event = db.relationship("Event", lazy="joined")

    @property
    def thoi_gian(self):
        return self.thoi_gian_checkin

    def to_dict(self):
        return {
            "id": self.id,
            "ma_cbsv": self.ma_cbsv,
            "event_id": self.event_id,
            "ho_ten": self.user.ho_ten if self.user else "",
            "email": self.user.email if self.user else "",
            "thoi_gian_checkin": self.thoi_gian_checkin.isoformat() if self.thoi_gian_checkin else None,
        }
