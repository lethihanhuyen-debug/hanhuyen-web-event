from datetime import datetime

from event_checkin.models import db


class Certificate(db.Model):
    __tablename__ = "certificates"
    __table_args__ = (
        db.UniqueConstraint("ma_cbsv", "event_id", name="uq_certificates_user_event"),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    ma_cbsv = db.Column(db.String(50), db.ForeignKey("users.ma_cbsv"), nullable=False, index=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=False, default=1, index=True)
    certificate_code = db.Column(db.String(100), unique=True, nullable=False, index=True)
    file_url = db.Column(db.String(255))
    file_type = db.Column(db.String(20), nullable=False, default="svg")
    status = db.Column(db.String(50), nullable=False, default="generated")
    issued_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship("User", lazy="joined")
    event = db.relationship("Event", lazy="joined")

    def to_dict(self):
        return {
            "id": self.id,
            "ma_cbsv": self.ma_cbsv,
            "event_id": self.event_id,
            "certificate_code": self.certificate_code,
            "file_url": self.file_url,
            "file_type": self.file_type,
            "status": self.status,
            "issued_at": self.issued_at.isoformat() if self.issued_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
