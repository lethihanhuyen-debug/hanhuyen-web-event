"""Việc dùng chung của quay số trúng thưởng: thư mục ảnh nền và dọn dữ liệu khi xóa sự kiện.
Đặt riêng (không nằm trong controller) để admin_controller.delete_event gọi được mà không bị import vòng."""
from pathlib import Path

from flask import current_app

from event_checkin.models import db
from event_checkin.models.lucky_draw import LuckyConfig, LuckyPrize, LuckyWinner

UPLOAD_SUBDIR = "lucky/uploads"  # tương đối so với thư mục static


def upload_dir():
    return Path(current_app.static_folder) / UPLOAD_SUBDIR


def background_path(relative):
    """Đường dẫn file ảnh nền trên đĩa, hoặc None nếu rỗng/nằm ngoài thư mục upload (chống trỏ lung tung)."""
    if not relative:
        return None
    path = (Path(current_app.static_folder) / relative).resolve()
    try:
        path.relative_to(upload_dir().resolve())
    except ValueError:
        return None
    return path


def purge_event_data(event_id):
    """Xóa dữ liệu quay số của sự kiện (chưa commit). Trả về đường dẫn ảnh nền cần xóa sau khi commit."""
    config = LuckyConfig.query.filter_by(event_id=event_id).first()
    file_path = background_path(config.hinh_nen) if config else None
    LuckyWinner.query.filter_by(event_id=event_id).delete()
    LuckyPrize.query.filter_by(event_id=event_id).delete()
    LuckyConfig.query.filter_by(event_id=event_id).delete()
    return [file_path] if file_path else []


def remove_files(paths):
    for path in paths:
        path.unlink(missing_ok=True)
