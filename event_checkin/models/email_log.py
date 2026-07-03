from datetime import datetime

from event_checkin.models import db


class EmailLog(db.Model):
    __tablename__ = "email_logs"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    ma_cbsv = db.Column(db.String(50), db.ForeignKey("users.ma_cbsv"), nullable=False, index=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=False, index=True)
    email_to = db.Column(db.String(255), nullable=False)
    email_type = db.Column(db.String(50), nullable=False, default="checkin_certificate")
    subject = db.Column(db.String(255), nullable=False)
    certificate_code = db.Column(db.String(100), db.ForeignKey("certificates.certificate_code"))
    attachment_path = db.Column(db.String(255))
    trang_thai = db.Column(db.String(20), nullable=False)
    error_message = db.Column(db.Text)
    sent_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
