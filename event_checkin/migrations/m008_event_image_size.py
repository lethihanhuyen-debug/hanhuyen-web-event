"""Migration 008: kích thước ảnh sự kiện + thu nhỏ/nén ảnh cũ + dọn ảnh thừa.

Chạy tại thư mục gốc của app (nơi có app.py), bằng python của venv, SAU m001..m007:

    python -m event_checkin.migrations.m008_event_image_size --dry-run   # chỉ xem sẽ làm gì (dung lượng trước/sau)
    python -m event_checkin.migrations.m008_event_image_size             # thực hiện
    python -m event_checkin.migrations.m008_event_image_size --check     # kiểm tra (mã thoát 0 + "OK" là đạt)

Làm gì:
1. Thêm cột events.hinh_width, events.hinh_height (INT NULL).
2. Mỗi sự kiện có ảnh: ảnh rộng > 2000px hoặc nặng > 2MB thì thu nhỏ (giữ tỉ lệ) + nén, giống lúc tải ảnh mới
   (event_checkin/utils/event_image.optimize). Rồi ghi kích thước thật vào 2 cột trên.
3. Xóa file ảnh thừa trong thư mục ảnh sự kiện mà không sự kiện nào trỏ tới (vd. event_2_image.png khi DB dùng .jpg).
- TRƯỚC khi sửa hoặc xóa bất kỳ file nào: chép bản gốc sang EVENT_IMAGE_BACKUP_DIR (mặc định instance/event_images_goc),
  giữ nguyên tên và đường dẫn (vd. instance/event_images_goc/events/event_1_image.png), kiểm tra bản chép đủ dung lượng
  rồi mới đụng tới file. Bản chép đã có (cùng dung lượng) thì không chép lại.
- Chạy lại nhiều lần vẫn an toàn: ảnh đã đạt chuẩn thì không nén lại; chỉ cập nhật kích thước.
- LƯU Ý: bước 3 dựa trên DB đang trỏ tới. Nhiều DB dùng chung 1 thư mục ảnh (máy dev có DB thật + DB thử) thì ảnh
  chỉ DB kia dùng sẽ bị coi là thừa -> chạy trên bản sao thư mục (đặt EVENT_IMAGE_DIR) hoặc chỉ chạy trên DB chính.
- Không import app.py (xem _standalone_app).
"""
import shutil
import sys
from datetime import datetime
from pathlib import Path

from flask import current_app
from sqlalchemy import inspect, text

from event_checkin.utils.event_image import EVENT_IMAGE_SUBDIR, MAX_BYTES, MAX_WIDTH, ImageRejected, new_filename, optimize

COLUMNS = (("hinh_width", "ALTER TABLE events ADD COLUMN hinh_width INT NULL"),
           ("hinh_height", "ALTER TABLE events ADD COLUMN hinh_height INT NULL"))


def image_root():
    return Path(current_app.config["EVENT_IMAGE_DIR"])


def backup_root():
    return Path(current_app.config["EVENT_IMAGE_BACKUP_DIR"])


def _mb(size):
    return f"{size / 1024 / 1024:.1f}MB" if size >= 100 * 1024 else f"{size / 1024:.0f}KB"


def _size_of(data):
    from io import BytesIO

    from PIL import Image

    with Image.open(BytesIO(data)) as image:
        return f"{image.width}x{image.height}"


def _columns():
    from event_checkin.models import db

    return {item["name"] for item in inspect(db.engine).get_columns("events")}


def _events(connection):
    has_size = {"hinh_width", "hinh_height"} <= _columns()
    extra = ", hinh_width, hinh_height" if has_size else ", NULL AS hinh_width, NULL AS hinh_height"
    return connection.execute(
        text(f"SELECT id, hinh{extra} FROM events WHERE hinh IS NOT NULL AND hinh <> '' ORDER BY id")
    ).fetchall()


def _file_of(hinh):
    """File của events.hinh trong thư mục ảnh, None nếu không phải dạng "events/<tên>"."""
    prefix = EVENT_IMAGE_SUBDIR + "/"
    if not hinh.startswith(prefix) or "/" in hinh[len(prefix):] or "\\" in hinh:
        return None
    return image_root() / hinh[len(prefix):]


def _backup(path):
    """Chép file sang thư mục bản gốc (giữ tên + đường dẫn). Dừng hẳn nếu chép không đủ dung lượng."""
    target = backup_root() / EVENT_IMAGE_SUBDIR / path.name
    if target.is_file() and target.stat().st_size == path.stat().st_size:
        return target
    if target.exists():
        # đã có bản gốc khác cùng tên (file bị thay sau lần chạy trước): không ghi đè, thêm mốc thời gian
        target = target.with_name(f"{target.stem}.{datetime.now():%Y%m%d%H%M%S}{target.suffix}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)
    if target.stat().st_size != path.stat().st_size:
        raise SystemExit(f"LỖI: chép {path} sang {target} không đủ dung lượng. Dừng, chưa sửa/xóa file nào thêm.")
    return target


def orphan_files(connection):
    root = image_root()
    if not root.is_dir():
        return []
    used = {_file_of(row.hinh).name for row in _events(connection) if _file_of(row.hinh)}
    return sorted(path for path in root.iterdir() if path.is_file() and path.name not in used)


def problems():
    """Những gì còn thiếu (rỗng = đạt)."""
    from event_checkin.models import db

    missing = [name for name, _sql in COLUMNS if name not in _columns()]
    if missing:
        return [f"thiếu cột events.{name}" for name in missing]
    result = []
    with db.engine.connect() as connection:
        rows = _events(connection)
        orphans = orphan_files(connection)
    for row in rows:
        path = _file_of(row.hinh)
        if not path or not path.is_file():
            continue                                   # thiếu file: chỉ cảnh báo (missing_files), không chặn
        if row.hinh_width is None or row.hinh_height is None:
            result.append(f"sự kiện {row.id} chưa có kích thước ảnh")
        try:
            from PIL import Image

            with Image.open(path) as image:
                too_wide = image.width > MAX_WIDTH
        except OSError:
            continue
        if too_wide or path.stat().st_size > MAX_BYTES:
            result.append(f"ảnh {path.name} chưa được thu nhỏ/nén")
    if orphans:
        result.append(f"{len(orphans)} file ảnh thừa chưa dọn")
    return result


def schema_problems():
    """Chỉ phần cột trong DB -- app.py gọi lúc khởi động (xem event_checkin/schema_status.py)."""
    missing = [name for name, _sql in COLUMNS if name not in _columns()]
    return [f"thiếu cột events.{name}" for name in missing]


def missing_files():
    from event_checkin.models import db

    with db.engine.connect() as connection:
        rows = _events(connection)
    return [(row.id, row.hinh) for row in rows if not _file_of(row.hinh) or not _file_of(row.hinh).is_file()]


def migrate(dry_run=False):
    from event_checkin.models import db

    lines = []
    say = (lambda text_: lines.append("[xem trước] " + text_)) if dry_run else lines.append
    saved = 0

    for name, sql in COLUMNS:
        if name not in _columns():
            say(f"thêm cột events.{name}")
            if not dry_run:
                with db.engine.begin() as connection:
                    connection.execute(text(sql))

    with db.engine.connect() as connection:
        rows = _events(connection)
    for row in rows:
        path = _file_of(row.hinh)
        if not path or not path.is_file():
            continue
        data = path.read_bytes()
        try:
            output, extension, (width, height), changed = optimize(data)
        except ImageRejected as error:
            say(f"BỎ QUA sự kiện {row.id} ({path.name}): {error}")
            continue
        new_hinh = row.hinh
        if changed:
            saved += len(data) - len(output)
            new_name = path.name if path.suffix.lower() == extension else new_filename(row.id, extension)
            say(f"thu nhỏ/nén ảnh sự kiện {row.id}: {path.name} {_size_of(data)} {_mb(len(data))} -> "
                f"{new_name} {width}x{height} {_mb(len(output))}")
            if not dry_run:
                _backup(path)
                target = path.with_name(new_name)
                temp = target.with_name(target.name + ".tmp")
                temp.write_bytes(output)
                temp.replace(target)
                new_hinh = f"{EVENT_IMAGE_SUBDIR}/{new_name}"
                if target != path:
                    path.unlink()                    # đuôi đổi (PNG -> JPG): bản gốc đã nằm trong thư mục bản gốc
        if (row.hinh_width, row.hinh_height) != (width, height) or new_hinh != row.hinh:
            if not changed:
                say(f"ghi kích thước ảnh sự kiện {row.id}: {width}x{height}")
            if not dry_run:
                with db.engine.begin() as connection:
                    connection.execute(
                        text("UPDATE events SET hinh = :hinh, hinh_width = :w, hinh_height = :h WHERE id = :id"),
                        {"hinh": new_hinh, "w": width, "h": height, "id": row.id},
                    )

    with db.engine.connect() as connection:
        orphans = orphan_files(connection)
    removed = 0
    for path in orphans:
        removed += path.stat().st_size
        say(f"xóa ảnh thừa {path.name} ({_mb(path.stat().st_size)}, không sự kiện nào dùng)")
        if not dry_run:
            _backup(path)
            path.unlink()
    if saved:
        say(f"thu nhỏ/nén giảm khoảng {_mb(saved)}")
    if removed:
        say(f"xóa ảnh thừa giải phóng {_mb(removed)}")
    if not dry_run and (saved or orphans):
        lines.append(f"Bản gốc nằm ở {backup_root() / EVENT_IMAGE_SUBDIR}")
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
        print(f"Thư mục ảnh: {image_root()}")
        if "--check" in argv:
            for event_id, hinh in missing_files():
                print(f"Cảnh báo: sự kiện {event_id} trỏ tới {hinh} nhưng không có file (sẽ hiện ảnh mặc định).")
            found = problems()
            if found:
                print("CHƯA ĐỦ: " + "; ".join(found) + ". Hãy chạy m008 (không kèm --check).")
                return 1
            print("OK: m008 đã chạy (có cột kích thước, ảnh đã thu nhỏ/nén, không còn ảnh thừa).")
            return 0
        dry_run = "--dry-run" in argv
        lines = migrate(dry_run=dry_run)
        print("\n".join(lines) if lines else "Mọi thứ đã có sẵn, không cần làm gì.")
        for event_id, hinh in missing_files():
            print(f"Cảnh báo: sự kiện {event_id} trỏ tới {hinh} nhưng không có file (sẽ hiện ảnh mặc định).")
        if dry_run:
            return 0
        found = problems()
    if found:
        print("CẢNH BÁO: " + "; ".join(found))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
