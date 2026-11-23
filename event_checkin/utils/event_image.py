"""Ảnh (banner) sự kiện: kiểm tra file tải lên, thu nhỏ/nén, lưu kích thước gốc, thông tin hiển thị.

Kích thước ảnh nằm ở 2 cột events.hinh_width / events.hinh_height (migration m008). Hai cột này CỐ Ý không khai báo
trong model Event: nếu khai báo, mọi câu INSERT/SELECT sự kiện đều đọc 2 cột đó, và DB chưa chạy m008 thì trang đăng ký
lẫn trang admin đều lỗi. Ở đây đọc/ghi bằng SQL riêng và chỉ khi m008 đã chạy (xem schema_status); thiếu m008 thì ảnh
vẫn hiện đúng, chỉ thiếu width/height trên thẻ <img>.
"""
from io import BytesIO
from pathlib import Path
import secrets

from flask import current_app, g, url_for
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import text

MAX_WIDTH = 2000                      # rộng hơn thì thu nhỏ về đúng mức này (giữ tỉ lệ)
MAX_BYTES = 2 * 1024 * 1024           # nặng hơn thì nén lại (kể cả khi không quá rộng)
MAX_PIXELS = 60_000_000               # chặn "ảnh bom" (khai báo kích thước khổng lồ để làm treo máy chủ)
JPEG_QUALITY = 85
WEBP_QUALITY = 85
ALLOWED_FORMATS = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}
EVENT_IMAGE_SUBDIR = "events"         # events.hinh = "events/<tên file>", phục vụ qua /static/events/...
DEFAULT_IMAGE = "images/event-default.svg"
DEFAULT_SIZE = (1600, 900)

INVALID_IMAGE_MESSAGE = "File này không phải ảnh hợp lệ (hoặc bị hỏng). Vui lòng chọn ảnh PNG, JPG hoặc WEBP."
TOO_MANY_PIXELS_MESSAGE = "Ảnh có kích thước quá lớn. Vui lòng chọn ảnh nhỏ hơn (tối đa khoảng 60 triệu điểm ảnh)."


class ImageRejected(Exception):
    pass


def image_dir():
    return Path(current_app.config["EVENT_IMAGE_DIR"])


# ---------- Xử lý file ----------

def open_image(data):
    """Mở ảnh từ bytes và kiểm tra đúng là ảnh PNG/JPEG/WEBP thật (không chỉ dựa vào đuôi file)."""
    try:
        with Image.open(BytesIO(data)) as probe:
            fmt = probe.format
            if fmt not in ALLOWED_FORMATS:
                raise ImageRejected(INVALID_IMAGE_MESSAGE)
            if probe.width * probe.height > MAX_PIXELS:
                raise ImageRejected(TOO_MANY_PIXELS_MESSAGE)
            probe.verify()                       # đọc hết file: phát hiện file cắt cụt/hỏng
        image = Image.open(BytesIO(data))        # verify() làm ảnh không dùng tiếp được -> mở lại
        image.load()
    except ImageRejected:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        raise ImageRejected(INVALID_IMAGE_MESSAGE)
    return image, fmt


def _has_alpha(image):
    return image.mode in ("RGBA", "LA", "PA") or (image.mode == "P" and "transparency" in image.info)


def _encode(image, fmt):
    buffer = BytesIO()
    if fmt == "JPEG":
        image.convert("RGB").save(buffer, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
    elif fmt == "WEBP":
        image.save(buffer, "WEBP", quality=WEBP_QUALITY, method=6)
    else:
        image.save(buffer, "PNG", optimize=True)
    return buffer.getvalue()


def optimize(data):
    """(bytes, đuôi file, (rộng, cao), đã_đổi) của ảnh sẵn sàng để lưu.

    - Xoay đúng chiều theo EXIF (ảnh chụp bằng điện thoại).
    - Rộng > MAX_WIDTH hoặc nặng > MAX_BYTES: thu nhỏ về tối đa MAX_WIDTH (giữ tỉ lệ) rồi nén lại. PNG không trong suốt
      mà nén xong vẫn > MAX_BYTES (thường là ảnh chụp lưu dạng PNG) thì đổi sang JPEG.
    - Ảnh nhỏ, nhẹ, không cần xoay: giữ nguyên từng byte."""
    image, fmt = open_image(data)
    original_format = fmt
    needs_rotate = image.getexif().get(0x0112, 1) not in (1, None)
    if not needs_rotate and image.width <= MAX_WIDTH and len(data) <= MAX_BYTES:
        return data, ALLOWED_FORMATS[fmt], image.size, False

    if needs_rotate:
        image = ImageOps.exif_transpose(image)
    resized = image.width > MAX_WIDTH
    if resized:
        height = max(1, round(image.height * MAX_WIDTH / image.width))
        image = image.resize((MAX_WIDTH, height), Image.LANCZOS)
    output = _encode(image, fmt)
    if fmt == "PNG" and len(output) > MAX_BYTES and not _has_alpha(image):
        fmt = "JPEG"
        output = _encode(image, fmt)
    if not resized and not needs_rotate and len(output) >= len(data):
        return data, ALLOWED_FORMATS[original_format], image.size, False   # nén lại không nhỏ hơn -> giữ bản gốc
    return output, ALLOWED_FORMATS[fmt], image.size, True


def new_filename(event_id, extension):
    """Tên mới cho mỗi lần tải: trình duyệt không hiện ảnh cũ trong cache khi admin đổi ảnh."""
    return f"event_{event_id}_{secrets.token_hex(4)}{extension}"


def stored_path(hinh):
    """Đường dẫn file của events.hinh ("events/<tên>"), None nếu không hợp lệ hoặc thoát ra ngoài thư mục ảnh."""
    if not hinh or not hinh.startswith(EVENT_IMAGE_SUBDIR + "/"):
        return None
    root = image_dir()
    path = root / hinh[len(EVENT_IMAGE_SUBDIR) + 1:]
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return None
    return path


def save_event_image(event, data):
    """Kiểm tra + tối ưu + lưu ảnh mới cho sự kiện, ghi kích thước. Người gọi tự commit, RỒI MỚI xóa file cũ (giá
    trị trả về) -- commit lỗi thì sự kiện vẫn trỏ tới file cũ còn nguyên."""
    output, extension, (width, height), _changed = optimize(data)
    root = image_dir()
    root.mkdir(parents=True, exist_ok=True)
    filename = new_filename(event.id, extension)
    (root / filename).write_bytes(output)

    old_path = stored_path(event.hinh)
    event.hinh = f"{EVENT_IMAGE_SUBDIR}/{filename}"
    set_size(event.id, width, height)
    return old_path if old_path and old_path.name != filename else None


# ---------- Kích thước trong DB (cột của m008) ----------

def sizes_enabled():
    from event_checkin.schema_status import pending_migrations

    return "m008" not in pending_migrations()


def set_size(event_id, width, height):
    if not sizes_enabled():
        return
    from event_checkin.models import db

    db.session.execute(
        text("UPDATE events SET hinh_width = :w, hinh_height = :h WHERE id = :id"),
        {"w": width, "h": height, "id": event_id},
    )


def _all_sizes():
    """{event_id: (rộng, cao)} cho mọi sự kiện có ảnh -- đọc 1 lần mỗi request (bảng sự kiện nhỏ)."""
    if "event_image_sizes" not in g:
        sizes = {}
        if sizes_enabled():
            from event_checkin.models import db

            rows = db.session.execute(
                text("SELECT id, hinh_width, hinh_height FROM events WHERE hinh_width IS NOT NULL AND hinh_height IS NOT NULL")
            )
            sizes = {row.id: (row.hinh_width, row.hinh_height) for row in rows}
        g.event_image_sizes = sizes
    return g.event_image_sizes


def _field(event, name):
    return event.get(name) if isinstance(event, dict) else getattr(event, name, None)


def event_image(event):
    """Thông tin hiển thị ảnh của 1 sự kiện (Event hoặc dict có 'id'/'hinh'); không có ảnh -> ảnh mặc định."""
    hinh = _field(event, "hinh")
    if not hinh:
        width, height = DEFAULT_SIZE
        return {"url": url_for("static", filename=DEFAULT_IMAGE), "width": width, "height": height, "is_default": True}
    width, height = _all_sizes().get(_field(event, "id"), (None, None))
    return {"url": url_for("static", filename=hinh), "width": width, "height": height, "is_default": False}


def init_event_images(app):
    app.add_template_global(event_image, "event_image")
