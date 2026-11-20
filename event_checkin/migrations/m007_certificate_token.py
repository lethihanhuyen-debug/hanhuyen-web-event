"""Migration 007: token cho chứng chỉ + chuyển file chứng chỉ ra ngoài thư mục static.

Chạy tại thư mục gốc của app (nơi có app.py), bằng python của venv, SAU m001..m006:

    python -m event_checkin.migrations.m007_certificate_token --dry-run     # chỉ xem sẽ làm gì, không sửa gì
    python -m event_checkin.migrations.m007_certificate_token               # thực hiện
    python -m event_checkin.migrations.m007_certificate_token --check       # kiểm tra (mã thoát 0 + "OK" là đạt)
    python -m event_checkin.migrations.m007_certificate_token --remove-old  # xóa file cũ trong static (chỉ khi --check đạt)

Làm gì:
1. Thêm cột certificates.token VARCHAR(64) NULL + chỉ mục UNIQUE ux_certificates_token.
2. Sinh token ngẫu nhiên (secrets.token_urlsafe(24), 32 ký tự) cho mọi chứng chỉ chưa có token.
3. Chép file từ event_checkin/static/certificates/generated/<năm>/... sang CERTIFICATE_STORAGE_DIR/<năm>/...
   (mặc định instance/certificates), so kích thước từng file, rồi đổi certificates.file_url sang đường dẫn tương đối
   "<năm>/<tên file>".
- KHÔNG xóa file cũ. Chỉ `--remove-old` mới xóa, và chỉ khi mọi file đã có bản chép đúng kích thước ở thư mục mới.
- Chạy lại nhiều lần vẫn an toàn: phần nào đã xong thì bỏ qua.
- PHẢI chạy trước khi khởi động lại app với code mới (code mới đọc cột token).
- Không import app.py (xem _standalone_app).
"""
import secrets
import shutil
import sys
from pathlib import Path

from sqlalchemy import inspect, text

from config import Config

TOKEN_INDEX = "ux_certificates_token"
LEGACY_PREFIX = "/static/certificates/generated/"


def legacy_root():
    return Path(Config.BASE_DIR) / "event_checkin" / "static" / "certificates" / "generated"


def storage_root():
    return Path(Config.CERTIFICATE_STORAGE_DIR)


def _has_token_column():
    from event_checkin.models import db

    return "token" in {item["name"] for item in inspect(db.engine).get_columns("certificates")}


def _has_token_unique():
    from event_checkin.models import db

    inspector = inspect(db.engine)
    if any(index.get("unique") and index["column_names"] == ["token"] for index in inspector.get_indexes("certificates")):
        return True
    return any(item["column_names"] == ["token"] for item in inspector.get_unique_constraints("certificates"))


def _rows(connection):
    return connection.execute(text("SELECT id, certificate_code, token, file_url FROM certificates ORDER BY id")).fetchall()


def _plan_file(file_url):
    """(file cũ, file mới, đường dẫn tương đối mới) cho một file_url; None nếu không cần chuyển."""
    if not file_url or not file_url.startswith(LEGACY_PREFIX):
        return None
    relative = file_url[len(LEGACY_PREFIX):]
    return legacy_root() / relative, storage_root() / relative, relative


def _same_file(source, target):
    return target.is_file() and source.is_file() and source.stat().st_size == target.stat().st_size


def problems():
    """Những gì còn thiếu/sai (rỗng = đạt)."""
    from event_checkin.models import db

    if "certificates" not in inspect(db.engine).get_table_names():
        return ["thiếu bảng certificates"]
    result = []
    if not _has_token_column():
        return ["thiếu cột certificates.token"]
    if not _has_token_unique():
        result.append("thiếu chỉ mục UNIQUE cho certificates.token")
    with db.engine.connect() as connection:
        rows = _rows(connection)
    missing_token = sum(1 for row in rows if not row.token)
    legacy_urls = sum(1 for row in rows if row.file_url and row.file_url.startswith(LEGACY_PREFIX))
    if missing_token:
        result.append(f"{missing_token} chứng chỉ chưa có token")
    if legacy_urls:
        result.append(f"{legacy_urls} chứng chỉ còn trỏ tới file trong static")
    for row in rows:
        if not row.file_url or row.file_url.startswith(LEGACY_PREFIX):
            continue
        target = storage_root() / row.file_url
        old = legacy_root() / row.file_url
        if old.is_file() and not _same_file(old, target):
            result.append(f"file {row.file_url} ở thư mục mới thiếu hoặc khác kích thước bản cũ")
    return result


def missing_sources():
    """Chứng chỉ trỏ tới file không có ở cả thư mục cũ lẫn mới (chỉ cảnh báo: file sẽ được tạo lại khi admin gửi lại)."""
    from event_checkin.models import db

    if not _has_token_column():
        return []
    with db.engine.connect() as connection:
        rows = _rows(connection)
    result = []
    for row in rows:
        if not row.file_url:
            continue
        relative = row.file_url[len(LEGACY_PREFIX):] if row.file_url.startswith(LEGACY_PREFIX) else row.file_url
        if not (legacy_root() / relative).is_file() and not (storage_root() / relative).is_file():
            result.append(row.certificate_code)
    return result


def orphan_files():
    """File trong thư mục cũ mà không chứng chỉ nào trỏ tới (vd. ảnh xem trước, chứng chỉ đã xóa)."""
    from event_checkin.models import db

    root = legacy_root()
    if not root.is_dir():
        return []
    referenced = set()
    with db.engine.connect() as connection:
        for row in connection.execute(text("SELECT file_url FROM certificates")).fetchall():
            if row.file_url:
                relative = row.file_url[len(LEGACY_PREFIX):] if row.file_url.startswith(LEGACY_PREFIX) else row.file_url
                referenced.add(relative)
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*")
                  if path.is_file() and path.relative_to(root).as_posix() not in referenced)


def migrate(dry_run=False):
    from event_checkin.models import db

    messages = []
    say = (lambda text_: messages.append("[xem trước] " + text_)) if dry_run else messages.append

    if not _has_token_column():
        say("thêm cột certificates.token")
        if not dry_run:
            with db.engine.begin() as connection:
                connection.execute(text("ALTER TABLE certificates ADD COLUMN token VARCHAR(64) NULL"))
    if dry_run and not _has_token_column():
        say(f"tạo chỉ mục UNIQUE {TOKEN_INDEX}")
        with db.engine.connect() as connection:
            count = connection.execute(text("SELECT COUNT(*) FROM certificates")).scalar()
        say(f"sinh token cho {count} chứng chỉ")
    else:
        if not _has_token_unique():
            say(f"tạo chỉ mục UNIQUE {TOKEN_INDEX}")
            if not dry_run:
                with db.engine.begin() as connection:
                    connection.execute(text(f"CREATE UNIQUE INDEX {TOKEN_INDEX} ON certificates (token)"))
        with db.engine.connect() as connection:
            without_token = [row.id for row in _rows(connection) if not row.token]
        if without_token:
            say(f"sinh token cho {len(without_token)} chứng chỉ")
            if not dry_run:
                with db.engine.begin() as connection:
                    for certificate_id in without_token:
                        connection.execute(
                            text("UPDATE certificates SET token = :token WHERE id = :id AND token IS NULL"),
                            {"token": secrets.token_urlsafe(24), "id": certificate_id},
                        )

    with db.engine.connect() as connection:
        rows = connection.execute(text("SELECT id, certificate_code, file_url FROM certificates ORDER BY id")).fetchall()
    copied = already = converted = 0
    for row in rows:
        plan = _plan_file(row.file_url)
        if not plan:
            continue
        source, target, relative = plan
        if source.is_file():
            if _same_file(source, target):
                already += 1
            else:
                copied += 1
                if not dry_run:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
                    if not _same_file(source, target):
                        raise SystemExit(f"LỖI: chép {source} sang {target} không đúng kích thước. Dừng, chưa đổi DB.")
        converted += 1
        if not dry_run:
            with db.engine.begin() as connection:
                connection.execute(text("UPDATE certificates SET file_url = :url WHERE id = :id"), {"url": relative, "id": row.id})
    if copied or already:
        say(f"chép {copied} file sang {storage_root()} ({already} file đã có sẵn đúng kích thước)")
    if converted:
        say(f"đổi đường dẫn file của {converted} chứng chỉ sang thư mục mới")
    return messages


def remove_old():
    """Xóa thư mục cũ static/certificates/generated -- CHỈ khi problems() rỗng (mọi file đã chép đúng kích thước)."""
    found = problems()
    if found:
        print("KHÔNG XÓA: " + "; ".join(found) + ". Hãy chạy m007 (không kèm tham số) rồi --check trước.")
        return 1
    root = legacy_root()
    files = [path for path in root.rglob("*") if path.is_file()] if root.is_dir() else []
    for path in files:
        path.unlink()
    for directory in sorted((p for p in root.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        directory.rmdir()
    print(f"Đã xóa {len(files)} file trong {root}.")
    return 0


def _standalone_app():
    """Ứng dụng Flask tối thiểu (chỉ cấu hình + db). KHÔNG import app.py: code mới đọc cột certificates.token, lúc
    chưa chạy m007 cột này chưa có."""
    from flask import Flask

    from event_checkin.models import db

    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)
    return app


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    app = _standalone_app()
    with app.app_context():
        if "--check" in argv:
            found = problems()
            for code in missing_sources():
                print(f"Cảnh báo: chứng chỉ {code} không còn file (sẽ được tạo lại khi admin gửi lại).")
            if found:
                print("CHƯA ĐỦ: " + "; ".join(found) + ". Hãy chạy m007 (không kèm --check).")
                return 1
            print(f"OK: m007 đã chạy (mọi chứng chỉ có token, file nằm ở {storage_root()}).")
            return 0
        if "--remove-old" in argv:
            return remove_old()
        dry_run = "--dry-run" in argv
        messages = migrate(dry_run=dry_run)
        print("; ".join(messages) + "." if messages else "Mọi thứ đã có sẵn, không cần làm gì.")
        for code in missing_sources():
            print(f"Cảnh báo: chứng chỉ {code} không còn file ở thư mục cũ lẫn mới (sẽ được tạo lại khi admin gửi lại).")
        orphans = orphan_files()
        if orphans:
            print(f"Lưu ý: {len(orphans)} file trong thư mục cũ không thuộc chứng chỉ nào (không chép, sẽ bị xóa khi "
                  f"chạy --remove-old): " + ", ".join(orphans[:10]) + (" ..." if len(orphans) > 10 else ""))
        if dry_run:
            return 0
        found = problems()
    if found:
        print("CẢNH BÁO: " + "; ".join(found))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
