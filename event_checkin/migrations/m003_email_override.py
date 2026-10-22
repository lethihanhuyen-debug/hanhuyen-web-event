"""Migration 003: thêm cột email_override (email admin nhập tay cho dòng gửi lỗi) vào checkin_records.

Chạy tại thư mục gốc của app (nơi có app.py), bằng python của venv, SAU m001 và m002:

    python -m event_checkin.migrations.m003_email_override

- Chạy lại nhiều lần vẫn an toàn: cột đã có thì bỏ qua.
- PHẢI chạy ngay sau khi chép code mới lên server: code mới đọc cột này, thiếu cột
  thì mọi trang dùng bảng check-in sẽ lỗi.
"""
import sys

from sqlalchemy import inspect, text

COLUMN_SQL = "ALTER TABLE checkin_records ADD COLUMN email_override VARCHAR(255) NULL"


def migrate():
    from event_checkin.models import db

    db.create_all()
    columns = {column["name"] for column in inspect(db.engine).get_columns("checkin_records")}
    if "email_override" in columns:
        return False
    with db.engine.begin() as connection:
        connection.execute(text(COLUMN_SQL))
    return True


def main():
    from app import app

    with app.app_context():
        added = migrate()
    print("Đã thêm cột checkin_records.email_override." if added else "Cột email_override đã có sẵn, không cần làm gì.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
