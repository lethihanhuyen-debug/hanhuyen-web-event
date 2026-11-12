from datetime import datetime

from event_checkin.models import db


class AuditLog(db.Model):
    """Nhật ký hoạt động (chỉ thêm, không sửa/xóa). Lưu giờ UTC như phần lớn các bảng khác -> hiển thị bằng
    format_utc_as_vn().

    admin_id KHÔNG đặt khóa ngoại và có thêm `username` chụp lại lúc ghi: xóa tài khoản không làm mất/chặn nhật ký,
    và đăng nhập thất bại (không có tài khoản hợp lệ) vẫn ghi được."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        db.Index("ix_audit_logs_created_at", "created_at"),
        db.Index("ix_audit_logs_admin_created", "admin_id", "created_at"),
        db.Index("ix_audit_logs_action_created", "action", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    admin_id = db.Column(db.Integer)
    username = db.Column(db.String(100))
    action = db.Column(db.String(60), nullable=False)
    target_type = db.Column(db.String(40))
    target_id = db.Column(db.String(100))
    # Chuỗi JSON (dùng TEXT như certificate_layout để chạy được trên mọi phiên bản MySQL/MariaDB).
    detail = db.Column(db.Text)
    ip = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
