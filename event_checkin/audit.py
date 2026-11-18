"""Nhật ký hoạt động (bảng audit_logs): ghi AI làm GÌ, lúc nào, từ IP nào.

- `log_action(...)`: ghi 1 dòng. Lỗi khi ghi nhật ký KHÔNG làm hỏng thao tác chính (chỉ ghi vào log máy chủ).
- `@audited(...)`: decorator đặt dưới @access; chỉ ghi khi thao tác THÀNH CÔNG (mã trả về < 400).
Giờ lưu là UTC (như các bảng khác); trang nhật ký đổi sang giờ Việt Nam khi hiển thị.
"""
import json
import logging
from functools import wraps

from flask import current_app, has_request_context, request

from event_checkin.access import get_current_admin
from event_checkin.models import db
from event_checkin.models.audit_log import AuditLog

logger = logging.getLogger(__name__)

# Tên hiển thị tiếng Việt cho từng loại thao tác (cũng là danh sách để lọc trên trang nhật ký).
ACTION_LABELS = {
    "auth.login": "Đăng nhập",
    "auth.login_failed": "Đăng nhập thất bại",
    "auth.logout": "Đăng xuất",
    "password.change": "Đổi mật khẩu",
    "password.forgot_request": "Yêu cầu quên mật khẩu",
    "password.forgot_throttled": "Quên mật khẩu bị chặn (quá số lần)",
    "password.reset_done": "Đặt lại mật khẩu qua email",
    "account.create": "Tạo tài khoản",
    "account.update": "Sửa tài khoản",
    "account.role_change": "Đổi vai trò",
    "account.lock": "Khóa tài khoản",
    "account.unlock": "Mở khóa tài khoản",
    "account.delete": "Xóa tài khoản",
    "account.reset_password": "Đặt lại mật khẩu cho tài khoản",
    "event.create": "Tạo sự kiện",
    "event.update": "Sửa sự kiện",
    "event.image": "Đổi ảnh sự kiện",
    "event.delete": "Xóa sự kiện",
    "certificate.send": "Gửi chứng chỉ",
    "certificate.resend": "Gửi lại chứng chỉ",
    "certificate.generate": "Tạo chứng chỉ",
    "certificate.template": "Đổi mẫu chứng chỉ",
    "certificate.layout": "Lưu bố cục chứng chỉ",
    "certificate.font": "Đổi font chứng chỉ",
    "certificate.purge": "Xóa file chứng chỉ",
    "checkin.add_manual": "Thêm check-in thủ công",
    "checkin.import": "Import check-in",
    "checkin.delete": "Xóa check-in",
    "checkin.dedupe": "Gộp check-in trùng",
    "checkin.display_name": "Sửa tên in chứng chỉ",
    "export.checkins": "Xuất Excel check-in",
    "export.registrations": "Xuất Excel đăng ký",
    "export.questions": "Xuất danh sách câu hỏi",
    "export.csv": "Xuất CSV đăng ký",
    "export.lucky": "Xuất Excel quay số",
    "donvi.create": "Thêm đơn vị",
    "donvi.update": "Sửa đơn vị",
    "donvi.delete": "Xóa đơn vị",
    "donvi.bulk": "Thao tác hàng loạt với đơn vị",
    "lucky.setup": "Lưu thiết lập quay số",
    "lucky.delete": "Xóa thiết lập quay số",
    "lucky.draw": "Quay số",
    "lucky.confirm": "Xác nhận kết quả quay số",
    "lucky.reject": "Từ chối kết quả quay số",
    "lucky.cancel_winner": "Hủy người trúng thưởng",
    "system.reset": "Xóa toàn bộ dữ liệu (reset)",
}


def action_label(action):
    return ACTION_LABELS.get(action, action)


def client_ip():
    # Sau ProxyFix (production) remote_addr đã là IP thật của người dùng.
    return ((request.remote_addr or "") if has_request_context() else "")[:64] or None


def log_action(action, target_type=None, target_id=None, detail=None, admin=None, username=None):
    """Ghi một dòng nhật ký. `admin` bỏ trống thì lấy tài khoản đang đăng nhập; truyền `username` khi chưa có tài khoản
    (vd. đăng nhập thất bại)."""
    try:
        if admin is None and username is None and has_request_context():
            admin = get_current_admin()
        db.session.add(AuditLog(
            admin_id=admin.id if admin else None,
            username=(admin.username if admin else username),
            action=action,
            target_type=target_type,
            target_id=None if target_id is None else str(target_id)[:100],
            detail=json.dumps(detail, ensure_ascii=False, default=str) if detail else None,
            ip=client_ip(),
        ))
        db.session.commit()
    except Exception:  # noqa: BLE001 -- nhật ký hỏng không được làm hỏng thao tác chính
        db.session.rollback()
        logger.exception("Không ghi được nhật ký hoạt động (%s)", action)


def audited(action, target_type=None, target_arg=None, skip=None):
    """Ghi nhật ký sau khi view trả về thành công (mã < 400). `target_arg` là tên tham số URL chứa id đối tượng
    (vd. "event_id"). `skip` là hàm trả True khi KHÔNG cần ghi (vd. chỉ xem thử, dry_run)."""

    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            response = view(*args, **kwargs)
            try:
                status = current_app.make_response(response).status_code
                if status < 400 and not (skip and skip()):
                    detail = {key: value for key, value in kwargs.items() if key != target_arg}
                    query = {key: value for key, value in request.args.items()}
                    if query:
                        detail["query"] = query
                    log_action(action, target_type, kwargs.get(target_arg) if target_arg else None, detail or None)
            except Exception:  # noqa: BLE001
                db.session.rollback()
                logger.exception("Không ghi được nhật ký hoạt động (%s)", action)
            return response

        return wrapper

    return decorator
