"""Tạo nhanh một tài khoản (staff / admin / super_admin) bằng dòng lệnh, chạy TRỰC TIẾP trên máy chủ/máy dev.

Dùng khi chưa có trang "Quản lý tài khoản" (bước d), hoặc khi cần cứu hộ. Chạy tại thư mục gốc dự án:

    .venv\\Scripts\\python scripts\\tao_tai_khoan.py nv_checkin staff
    .venv\\Scripts\\python scripts\\tao_tai_khoan.py qtv_su_kien admin
    .venv\\Scripts\\python scripts\\tao_tai_khoan.py ten_dang_nhap staff --password "MatKhau123" --email a@b.vn

- Không có --password thì tự sinh mật khẩu ngẫu nhiên và in ra màn hình MỘT lần (hãy ghi lại).
- Script in rõ đang thao tác trên DB nào. Muốn thử trên DB thử:  $env:MYSQL_DATABASE = "checkin_event_test"
- Tên đăng nhập đã tồn tại thì dừng, không ghi đè.
"""
import argparse
import os
import secrets
import string
import sys
from datetime import datetime

# Chạy được từ bất kỳ thư mục nào: thêm thư mục gốc dự án vào đường dẫn import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402

from config import Config  # noqa: E402
from event_checkin import permissions as perm  # noqa: E402
from event_checkin.models import db  # noqa: E402
from event_checkin.models.admin import Admin  # noqa: E402


def random_password(length=12):
    """Mật khẩu ngẫu nhiên có chữ hoa, chữ thường và số (không dùng ký tự dễ nhầm như 0/O, 1/l/I)."""
    letters = "".join(c for c in string.ascii_letters if c not in "lIO")
    digits = "".join(c for c in string.digits if c not in "01")
    while True:
        password = "".join(secrets.choice(letters + digits) for _ in range(length))
        if any(c.islower() for c in password) and any(c.isupper() for c in password) and any(c.isdigit() for c in password):
            return password


def fail(message):
    print("LỖI: " + message)
    sys.exit(1)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Tạo tài khoản đăng nhập")
    parser.add_argument("username", help="tên đăng nhập")
    parser.add_argument("role", choices=perm.ROLES, help="vai trò: " + " | ".join(perm.ROLES))
    parser.add_argument("--password", help="mật khẩu (bỏ trống = tự sinh)")
    parser.add_argument("--email", help="email (tùy chọn, dùng cho Quên mật khẩu)")
    args = parser.parse_args()

    username = args.username.strip()
    password = args.password or random_password()
    email = (args.email or "").strip().lower() or None
    if not username:
        fail("Tên đăng nhập không được để trống.")
    if len(password) < 8 or not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        fail("Mật khẩu tối thiểu 8 ký tự, có cả chữ và số.")

    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)
    with app.app_context():
        print(f"DB đang dùng: {Config.MYSQL_DATABASE} @ {Config.MYSQL_HOST}")
        if Admin.query.filter_by(username=username).first():
            fail(f"Tên đăng nhập '{username}' đã tồn tại, không ghi đè.")
        if email and Admin.query.filter_by(email=email).first():
            fail(f"Email '{email}' đã được tài khoản khác dùng.")
        db.session.add(Admin(
            username=username,
            password_hash=generate_password_hash(password),
            role=args.role,
            is_active=True,
            email=email,
            created_at=datetime.utcnow(),
        ))
        db.session.commit()
    print(f"Đã tạo tài khoản: {username}  |  vai trò: {perm.role_label(args.role)} ({args.role})")
    if not args.password:
        print(f"Mật khẩu (chỉ hiện lần này): {password}")


if __name__ == "__main__":
    main()
