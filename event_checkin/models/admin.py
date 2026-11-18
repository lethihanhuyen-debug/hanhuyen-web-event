from datetime import datetime

from event_checkin.models import db
from event_checkin.permissions import ROLE_STAFF


class Admin(db.Model):
    __tablename__ = "admins"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    # 'super_admin' | 'admin' | 'staff' (xem event_checkin/permissions.py). Kiểm tra ở tầng ứng dụng, không dùng
    # ENUM của MySQL để dễ thêm vai trò sau này. Mặc định thấp nhất (staff) -- quên gán thì không có thêm quyền.
    role = db.Column(db.String(50), nullable=False, default=ROLE_STAFF)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    # Dùng cho "Quên mật khẩu" qua email; để NULL nếu chưa có (không bắt buộc, UNIQUE khi có giá trị).
    email = db.Column(db.String(255), unique=True)
    # True sau khi super_admin đặt lại mật khẩu: bắt buộc đổi mật khẩu trước khi dùng các trang khác.
    must_change_password = db.Column(db.Boolean, nullable=False, default=False)
    # Tăng mỗi khi đổi/đặt lại mật khẩu, đổi vai trò hoặc khóa: phiên cũ (lưu số này trong cookie) tự mất hiệu lực.
    session_version = db.Column(db.Integer, nullable=False, default=0)
    last_login_at = db.Column(db.DateTime)
    created_by = db.Column(db.Integer, db.ForeignKey("admins.id"))
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime)
