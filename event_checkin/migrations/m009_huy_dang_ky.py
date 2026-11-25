"""Migration 009: hủy (xóa mềm) đăng ký.

Chạy tại thư mục gốc của app (nơi có app.py), bằng python của venv, SAU m001..m008:

    python -m event_checkin.migrations.m009_huy_dang_ky --dry-run   # chỉ xem sẽ làm gì
    python -m event_checkin.migrations.m009_huy_dang_ky             # thực hiện
    python -m event_checkin.migrations.m009_huy_dang_ky --check     # kiểm tra (mã thoát 0 + "OK" là đạt)

Thêm vào bảng registrations (không xóa/sửa dữ liệu cũ; đăng ký cũ = đang hiệu lực):
- trang_thai        VARCHAR(20) NOT NULL DEFAULT 'active'   ('active' | 'cancelled')
- huy_luc           DATETIME NULL       (giờ Việt Nam, lúc admin hủy)
- huy_boi           INT NULL, khóa ngoại -> admins.id (tài khoản đã hủy)
- ly_do_huy         VARCHAR(500) NULL
- chan_dang_ky_lai  BOOLEAN NOT NULL DEFAULT 0  (1 = mã này không được tự đăng ký lại sự kiện này)
- chỉ mục ix_registrations_event_status (event_id, trang_thai)

- Chạy lại nhiều lần vẫn an toàn: cột/chỉ mục nào có rồi thì bỏ qua.
- PHẢI chạy trước khi khởi động lại app với code mới (code mới đọc các cột này). Quên chạy thì app vẫn khởi động
  nhưng mọi trang có đọc đăng ký báo bảo trì (xem event_checkin/schema_status.py).
- Không import app.py (xem _standalone_app).
"""
import sys

from sqlalchemy import inspect, text

# (cột, câu ALTER cho MySQL/MariaDB, câu ALTER cho SQLite, tên khóa ngoại nếu cột tham chiếu admins.id)
COLUMNS = (
    ("trang_thai", "ALTER TABLE registrations ADD COLUMN trang_thai VARCHAR(20) NOT NULL DEFAULT 'active'", None, None),
    ("huy_luc", "ALTER TABLE registrations ADD COLUMN huy_luc DATETIME NULL", None, None),
    ("huy_boi", "ALTER TABLE registrations ADD COLUMN huy_boi INT NULL",
     "ALTER TABLE registrations ADD COLUMN huy_boi INTEGER NULL REFERENCES admins (id)", "fk_registrations_huy_boi"),
    ("ly_do_huy", "ALTER TABLE registrations ADD COLUMN ly_do_huy VARCHAR(500) NULL", None, None),
    ("chan_dang_ky_lai", "ALTER TABLE registrations ADD COLUMN chan_dang_ky_lai BOOLEAN NOT NULL DEFAULT 0", None, None),
)
INDEX_NAME = "ix_registrations_event_status"
INDEX_SQL = f"CREATE INDEX {INDEX_NAME} ON registrations (event_id, trang_thai)"


def _columns():
    from event_checkin.models import db

    return {item["name"] for item in inspect(db.engine).get_columns("registrations")}


def _has_index():
    from event_checkin.models import db

    return any(item["name"] == INDEX_NAME for item in inspect(db.engine).get_indexes("registrations"))


def schema_problems():
    """Phần cột/chỉ mục còn thiếu (rỗng = đạt). app.py gọi lúc khởi động (xem schema_status.py)."""
    existing = _columns()
    result = [f"thiếu cột registrations.{name}" for name, *_rest in COLUMNS if name not in existing]
    if not result and not _has_index():
        result.append(f"thiếu chỉ mục {INDEX_NAME}")
    return result


def problems():
    return schema_problems()


def migrate(dry_run=False):
    from event_checkin.models import db

    lines = []
    is_mysql = db.engine.dialect.name in ("mysql", "mariadb")
    existing = _columns()
    for column, mysql_sql, sqlite_sql, fk_name in COLUMNS:
        if column in existing:
            continue
        lines.append(("[xem trước] " if dry_run else "") + f"thêm cột registrations.{column}")
        if dry_run:
            continue
        with db.engine.begin() as connection:
            connection.execute(text(mysql_sql if (is_mysql or not sqlite_sql) else sqlite_sql))
            if is_mysql and fk_name:
                connection.execute(text(
                    f"ALTER TABLE registrations ADD CONSTRAINT {fk_name} FOREIGN KEY ({column}) REFERENCES admins (id)"
                ))
    if not _has_index():
        lines.append(("[xem trước] " if dry_run else "") + f"tạo chỉ mục {INDEX_NAME} (event_id, trang_thai)")
        if not dry_run:
            with db.engine.begin() as connection:
                connection.execute(text(INDEX_SQL))
    return lines


def _standalone_app():
    """Ứng dụng Flask tối thiểu (chỉ cấu hình + db). KHÔNG import app.py."""
    from flask import Flask

    from config import Config
    from event_checkin.models import db

    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)
    return app


def main(argv=None, app=None):
    argv = sys.argv[1:] if argv is None else argv
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    app = app or _standalone_app()
    with app.app_context():
        if "--check" in argv:
            found = problems()
            if found:
                print("CHƯA ĐỦ: " + "; ".join(found) + ". Hãy chạy m009 (không kèm --check).")
                return 1
            print("OK: m009 đã chạy (đủ cột hủy đăng ký và chỉ mục).")
            return 0
        dry_run = "--dry-run" in argv
        lines = migrate(dry_run=dry_run)
        print("\n".join(lines) if lines else "Mọi thứ đã có sẵn, không cần làm gì.")
        if dry_run:
            return 0
        found = problems()
    if found:
        print("CẢNH BÁO: " + "; ".join(found))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
