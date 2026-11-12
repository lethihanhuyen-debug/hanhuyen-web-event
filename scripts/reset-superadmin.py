"""Khôi phục tài khoản super_admin khi quên mật khẩu / bị khóa -- CHẠY TRỰC TIẾP TRÊN MÁY CHỦ.

    .venv\\Scripts\\python scripts\\reset-superadmin.py <tên_đăng_nhập>

Việc làm: đặt MẬT KHẨU TẠM ngẫu nhiên (in ra màn hình MỘT lần), bật must_change_password (đăng nhập xong bị buộc đổi ngay),
mở khóa tài khoản nếu đang bị khóa, đăng xuất mọi phiên cũ, và ghi một dòng vào Nhật ký hoạt động.

- Chỉ áp dụng cho tài khoản có vai trò super_admin (admin/staff thì nhờ super_admin đặt lại trong trang Quản lý tài khoản).
- Script in rõ đang thao tác trên DB nào. Thử trước trên DB thử:  $env:MYSQL_DATABASE = "checkin_event_test"
"""
import os
import sys
from datetime import datetime

# Chạy được từ bất kỳ thư mục nào: thêm thư mục gốc dự án vào đường dẫn import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402

from config import Config  # noqa: E402
from event_checkin import permissions as perm  # noqa: E402
from event_checkin import security  # noqa: E402
from event_checkin.models import db  # noqa: E402
from event_checkin.models.admin import Admin  # noqa: E402
from event_checkin.models.audit_log import AuditLog  # noqa: E402
from event_checkin.models.password_reset import PasswordReset  # noqa: E402


def fail(message):
    print("LỖI: " + message)
    sys.exit(1)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) != 2 or sys.argv[1].startswith("-"):
        fail("Cách dùng:  python scripts\\reset-superadmin.py <tên_đăng_nhập>")
    username = sys.argv[1].strip()

    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)
    with app.app_context():
        print(f"DB đang dùng: {Config.MYSQL_DATABASE} @ {Config.MYSQL_HOST}")
        admin = Admin.query.filter_by(username=username).first()
        if not admin:
            fail(f"Không có tài khoản '{username}'.")
        if admin.role != perm.ROLE_SUPER_ADMIN:
            fail(f"'{username}' không phải super_admin (đang là {admin.role}). Hãy nhờ super_admin đặt lại trong trang Quản lý tài khoản.")

        temp_password = security.generate_temp_password()
        now = datetime.utcnow()
        was_locked = not admin.is_active
        admin.password_hash = generate_password_hash(temp_password)
        admin.must_change_password = True
        admin.is_active = True
        admin.session_version = (admin.session_version or 0) + 1
        admin.updated_at = now
        PasswordReset.query.filter(PasswordReset.admin_id == admin.id, PasswordReset.used_at.is_(None)).update({"used_at": now})
        db.session.add(AuditLog(
            admin_id=admin.id, username=admin.username, action="account.reset_password", target_type="account",
            target_id=str(admin.id), detail='{"via": "scripts/reset-superadmin.py", "unlocked": %s}' % ("true" if was_locked else "false"),
        ))
        db.session.commit()

    print(f"Đã đặt lại mật khẩu cho super_admin: {username}" + (" (và mở khóa tài khoản)" if was_locked else ""))
    print(f"Mật khẩu tạm (chỉ hiện lần này): {temp_password}")
    print("Đăng nhập bằng mật khẩu này, hệ thống sẽ bắt đổi mật khẩu ngay.")


if __name__ == "__main__":
    main()
