from datetime import datetime

from event_checkin.models import db


class PasswordReset(db.Model):
    """Yêu cầu đặt lại mật khẩu qua email. Chỉ lưu BĂM (sha256) của token, không lưu token gốc:
    lộ DB cũng không dùng lại được link. Link hết hạn sau 30 phút (expires_at) và chỉ dùng 1 lần (used_at)."""

    __tablename__ = "password_resets"
    __table_args__ = (
        db.Index("ix_password_resets_admin_created", "admin_id", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    admin_id = db.Column(db.Integer, db.ForeignKey("admins.id"), nullable=False)
    token_hash = db.Column(db.String(64), nullable=False, unique=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    used_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
