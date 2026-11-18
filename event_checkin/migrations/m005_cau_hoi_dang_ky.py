"""Migration 005: thêm ô "câu hỏi" tuỳ chọn vào form đăng ký.

Chạy tại thư mục gốc của app (nơi có app.py), bằng python của venv, SAU m001..m004:

    python -m event_checkin.migrations.m005_cau_hoi_dang_ky           # thêm cột
    python -m event_checkin.migrations.m005_cau_hoi_dang_ky --check   # chỉ kiểm tra đã chạy chưa (mã thoát 0 = đủ cột)

Thêm 3 cột (không sửa/xóa dữ liệu cũ):
- events.cho_phep_cau_hoi  BOOLEAN NOT NULL DEFAULT 0   (sự kiện cũ mặc định TẮT)
- events.tieu_de_cau_hoi   VARCHAR(255) NULL
- registrations.cau_hoi    TEXT NULL                    (đăng ký cũ = chưa có câu hỏi)

- Chạy lại nhiều lần vẫn an toàn: cột nào có rồi thì bỏ qua.
- PHẢI chạy trước khi khởi động lại app với code mới: code mới đọc các cột này, thiếu cột
  thì app không khởi động được (và mọi trang sự kiện/đăng ký lỗi).
"""
import sys

from sqlalchemy import inspect, text

COLUMNS = (
    ("events", "cho_phep_cau_hoi", "ALTER TABLE events ADD COLUMN cho_phep_cau_hoi BOOLEAN NOT NULL DEFAULT 0"),
    ("events", "tieu_de_cau_hoi", "ALTER TABLE events ADD COLUMN tieu_de_cau_hoi VARCHAR(255) NULL"),
    ("registrations", "cau_hoi", "ALTER TABLE registrations ADD COLUMN cau_hoi TEXT NULL"),
)


def missing_columns():
    from event_checkin.models import db

    inspector = inspect(db.engine)
    result = []
    for table, column, _sql in COLUMNS:
        existing = {item["name"] for item in inspector.get_columns(table)}
        if column not in existing:
            result.append(f"{table}.{column}")
    return result


def migrate():
    from event_checkin.models import db

    db.create_all()
    added = []
    for table, column, sql in COLUMNS:
        existing = {item["name"] for item in inspect(db.engine).get_columns(table)}
        if column in existing:
            continue
        with db.engine.begin() as connection:
            connection.execute(text(sql))
        added.append(f"{table}.{column}")
    return added


def _standalone_app():
    """Ứng dụng Flask tối thiểu (chỉ cấu hình + db). KHÔNG import app.py: khi khởi động, app.py đọc bảng
    events ngay, mà lúc chưa chạy m005 bảng này còn thiếu cột -> import app.py sẽ lỗi trước khi kịp migrate."""
    from flask import Flask

    from config import Config
    from event_checkin.models import db

    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)
    return app


def main():
    # Console Windows mặc định không in được tiếng Việt (cp1252) -> ép UTF-8 để thông báo không làm script lỗi
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    app = _standalone_app()
    with app.app_context():
        if "--check" in sys.argv[1:]:
            missing = missing_columns()
            if missing:
                print("CHƯA ĐỦ: còn thiếu cột " + ", ".join(missing) + ". Hãy chạy m005 (không kèm --check).")
                return 1
            print("OK: m005 đã chạy, đủ 3 cột (events.cho_phep_cau_hoi, events.tieu_de_cau_hoi, registrations.cau_hoi).")
            return 0
        added = migrate()
    print("Đã thêm: " + ", ".join(added) + "." if added else "Các cột đã có sẵn, không cần làm gì.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
