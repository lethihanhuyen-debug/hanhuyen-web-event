"""Migration 006: phân quyền 3 cấp (super_admin / admin / staff).

Chạy tại thư mục gốc của app (nơi có app.py), bằng python của venv, SAU m001..m005:

    python -m event_checkin.migrations.m006_phan_quyen           # thực hiện
    python -m event_checkin.migrations.m006_phan_quyen --check   # chỉ kiểm tra (mã thoát 0 = đã đủ)

Thêm (không sửa/xóa dữ liệu cũ):
- admins.email                 VARCHAR(255) NULL, UNIQUE khi có giá trị  (cho "Quên mật khẩu")
- admins.must_change_password  BOOLEAN NOT NULL DEFAULT 0
- admins.session_version       INT NOT NULL DEFAULT 0                    (đăng xuất phiên cũ khi đổi mật khẩu/quyền)
- admins.last_login_at         DATETIME NULL
- events.updated_by            INT NULL, khóa ngoại -> admins.id
- checkin_records.checked_in_by INT NULL, khóa ngoại -> admins.id
- bảng audit_logs, password_resets (nếu chưa có)

Vai trò: tài khoản hiện có mà `role` không thuộc {super_admin, admin, staff} (rỗng/giá trị lạ) được gán super_admin
(đúng yêu cầu "tài khoản hiện tại thành super_admin"). Tài khoản đã có vai trò hợp lệ giữ nguyên.

- Chạy lại nhiều lần vẫn an toàn: cột/bảng/chỉ mục nào có rồi thì bỏ qua.
- PHẢI chạy trước khi khởi động lại app với code mới: code mới đọc các cột này, thiếu cột thì app không khởi động
  được (app.py đọc bảng admins ngay lúc khởi động).
- Không import app.py (xem _standalone_app).
"""
import sys

from sqlalchemy import inspect, text

from event_checkin.permissions import ROLE_SUPER_ADMIN, ROLES

# (bảng, cột, câu ALTER cho MySQL/MariaDB, câu ALTER cho SQLite, tên khóa ngoại nếu cột tham chiếu admins.id)
# SQLite không có ADD CONSTRAINT nên khóa ngoại khai báo ngay trong ADD COLUMN; MySQL lại bỏ qua REFERENCES
# trong ADD COLUMN nên phải ADD CONSTRAINT riêng.
COLUMNS = (
    ("admins", "email", "ALTER TABLE admins ADD COLUMN email VARCHAR(255) NULL", None, None),
    ("admins", "must_change_password",
     "ALTER TABLE admins ADD COLUMN must_change_password BOOLEAN NOT NULL DEFAULT 0", None, None),
    ("admins", "session_version", "ALTER TABLE admins ADD COLUMN session_version INT NOT NULL DEFAULT 0", None, None),
    ("admins", "last_login_at", "ALTER TABLE admins ADD COLUMN last_login_at DATETIME NULL", None, None),
    ("events", "updated_by",
     "ALTER TABLE events ADD COLUMN updated_by INT NULL",
     "ALTER TABLE events ADD COLUMN updated_by INTEGER NULL REFERENCES admins (id)",
     "fk_events_updated_by"),
    ("checkin_records", "checked_in_by",
     "ALTER TABLE checkin_records ADD COLUMN checked_in_by INT NULL",
     "ALTER TABLE checkin_records ADD COLUMN checked_in_by INTEGER NULL REFERENCES admins (id)",
     "fk_checkin_records_checked_in_by"),
)

NEW_TABLES = ("audit_logs", "password_resets")
EMAIL_INDEX = "ux_admins_email"


def _columns(table):
    from event_checkin.models import db

    return {item["name"] for item in inspect(db.engine).get_columns(table)}


def _has_email_unique():
    """True nếu admins.email đã có ràng buộc/chỉ mục UNIQUE (do mình tạo hoặc do db.create_all tạo sẵn)."""
    from event_checkin.models import db

    inspector = inspect(db.engine)
    for index in inspector.get_indexes("admins"):
        if index.get("unique") and index["column_names"] == ["email"]:
            return True
    for constraint in inspector.get_unique_constraints("admins"):
        if constraint["column_names"] == ["email"]:
            return True
    return False


def problems():
    """Danh sách những gì còn thiếu/sai (rỗng = đã đủ)."""
    from event_checkin.models import db

    result = []
    inspector = inspect(db.engine)
    tables = set(inspector.get_table_names())
    for table, column, *_rest in COLUMNS:
        if table not in tables:
            result.append(f"thiếu bảng {table}")
        elif column not in _columns(table):
            result.append(f"thiếu cột {table}.{column}")
    for table in NEW_TABLES:
        if table not in tables:
            result.append(f"thiếu bảng {table}")
    if "admins" in tables and "email" in _columns("admins") and not _has_email_unique():
        result.append("thiếu chỉ mục UNIQUE cho admins.email")
    if not result:
        marks = ", ".join(f"'{role}'" for role in ROLES)
        with db.engine.connect() as connection:
            invalid = connection.execute(
                text(f"SELECT COUNT(*) FROM admins WHERE role IS NULL OR role NOT IN ({marks})")
            ).scalar()
            supers = connection.execute(
                text("SELECT COUNT(*) FROM admins WHERE role = :role AND is_active = :active"),
                {"role": ROLE_SUPER_ADMIN, "active": True},
            ).scalar()
        if invalid:
            result.append(f"{invalid} tài khoản có vai trò không hợp lệ")
        if not supers:
            result.append("chưa có super_admin nào đang hoạt động")
    return result


def migrate():
    from event_checkin.models import db

    messages = []
    # Tạo bảng mới (audit_logs, password_resets); bảng đã có thì giữ nguyên, không đụng.
    before = set(inspect(db.engine).get_table_names())
    db.create_all()
    created = [table for table in NEW_TABLES if table not in before]
    if created:
        messages.append("đã tạo bảng " + ", ".join(created))

    dialect = db.engine.dialect.name
    is_mysql = dialect in ("mysql", "mariadb")
    for table, column, mysql_sql, sqlite_sql, fk_name in COLUMNS:
        if column in _columns(table):
            continue
        with db.engine.begin() as connection:
            connection.execute(text(mysql_sql if (is_mysql or not sqlite_sql) else sqlite_sql))
            if is_mysql and fk_name:
                connection.execute(text(
                    f"ALTER TABLE {table} ADD CONSTRAINT {fk_name} FOREIGN KEY ({column}) REFERENCES admins (id)"
                ))
        messages.append(f"đã thêm cột {table}.{column}")

    if not _has_email_unique():
        with db.engine.begin() as connection:
            connection.execute(text(f"CREATE UNIQUE INDEX {EMAIL_INDEX} ON admins (email)"))
        messages.append("đã tạo chỉ mục UNIQUE admins.email")

    # Chuẩn hóa vai trò: giá trị lạ/rỗng -> super_admin (tài khoản hiện có là admin cũ). Đã hợp lệ thì giữ nguyên.
    marks = ", ".join(f"'{role}'" for role in ROLES)
    with db.engine.begin() as connection:
        result = connection.execute(
            text(f"UPDATE admins SET role = :role WHERE role IS NULL OR role NOT IN ({marks})"),
            {"role": ROLE_SUPER_ADMIN},
        )
    if result.rowcount:
        messages.append(f"đã gán super_admin cho {result.rowcount} tài khoản có vai trò chưa hợp lệ")
    return messages


def _standalone_app():
    """Ứng dụng Flask tối thiểu (chỉ cấu hình + db). KHÔNG import app.py: khi khởi động, app.py đọc bảng
    admins/events ngay, mà lúc chưa chạy m006 các bảng này còn thiếu cột -> import app.py sẽ lỗi trước khi kịp migrate."""
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
            found = problems()
            if found:
                print("CHƯA ĐỦ: " + "; ".join(found) + ". Hãy chạy m006 (không kèm --check).")
                return 1
            print("OK: m006 đã chạy (đủ cột, bảng, chỉ mục; vai trò hợp lệ; có super_admin đang hoạt động).")
            return 0
        messages = migrate()
        found = problems()
    print("; ".join(messages) + "." if messages else "Mọi thứ đã có sẵn, không cần làm gì.")
    if found:
        print("CẢNH BÁO: " + "; ".join(found))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
