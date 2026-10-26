"""Migration 004: tạo 3 bảng quay số trúng thưởng (lucky_configs, lucky_prizes, lucky_winners).

Chạy tại thư mục gốc của app (nơi có app.py), bằng python của venv:

    python -m event_checkin.migrations.m004_lucky_draw
    python -m event_checkin.migrations.m004_lucky_draw --print-sql   # in câu CREATE TABLE cho MySQL

- Chỉ TẠO bảng mới bằng db.create_all() (bảng đã có thì bỏ qua) -- không sửa/xoá bảng hay
  dữ liệu hiện có, kể cả checkin_records.
- Chạy lại nhiều lần vẫn an toàn.
- Nên chạy ngay sau khi chép code mới lên server: xoá sự kiện và trang quay số cần các bảng này.
"""
import argparse
import sys

from sqlalchemy import inspect
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateIndex, CreateTable

TABLES = ("lucky_configs", "lucky_prizes", "lucky_winners")


def _check_old_schema(db):
    """Bảng lucky_* có thể đã được app tự tạo (db.create_all() lúc khởi động) từ bản thử cũ, thiếu
    cột mới. create_all không sửa bảng đã có, nên báo rõ để xoá 3 bảng (đang rỗng) rồi chạy lại."""
    inspector = inspect(db.engine)
    if "lucky_configs" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("lucky_configs")}
    missing = {"phien_ban", "created_at", "updated_at"} - columns
    if missing:
        raise SystemExit(
            "Bảng lucky_configs đang có là bản cũ (thiếu cột: " + ", ".join(sorted(missing)) + "). "
            "Hãy xoá 3 bảng lucky_winners, lucky_prizes, lucky_configs (theo thứ tự này) rồi chạy lại m004 -- "
            "xem hướng dẫn trong DEPLOYMENT.md."
        )


def migrate():
    from event_checkin.models import db

    _check_old_schema(db)
    existing = set(inspect(db.engine).get_table_names())
    db.create_all()
    return [name for name in TABLES if name not in existing]


def print_mysql_ddl():
    from event_checkin.models import db

    for name in TABLES:
        table = db.metadata.tables[name]
        print(str(CreateTable(table).compile(dialect=mysql.dialect())).strip() + ";")
        for index in sorted(table.indexes, key=lambda item: item.name):
            print(str(CreateIndex(index).compile(dialect=mysql.dialect())).strip() + ";")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--print-sql", action="store_true", help="in câu SQL tạo bảng cho MySQL rồi thoát")
    args = parser.parse_args()

    from app import app

    if args.print_sql:
        with app.app_context():
            print_mysql_ddl()
        return 0

    with app.app_context():
        created = migrate()
    print(f"Đã tạo bảng: {', '.join(created)}." if created else "Các bảng quay số đã có sẵn, không cần làm gì.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
