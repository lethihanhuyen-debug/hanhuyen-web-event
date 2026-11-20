"""Kiểm tra lúc khởi động: DB đã chạy đủ các migration mà code hiện tại cần chưa.

Migration (event_checkin/migrations) phải chạy bằng tay theo DEPLOYMENT.md. Nếu quên, trước đây app lỗi 500 ở
chỗ đọc cột còn thiếu (vd. "Unknown column 'certificates.token'"). Giờ app vẫn chạy, nhưng:
- ghi log lỗi rõ ràng "Chưa chạy migration m00X, xem DEPLOYMENT.md";
- hiện banner đỏ trên mọi trang admin/staff;
- thiếu m007: các route chứng chỉ trả "Hệ thống chứng chỉ đang bảo trì" (503);
- thiếu m006: các trang cần tài khoản (đăng nhập, admin, staff, check-in) trả trang bảo trì (503), vì bảng admins
  thiếu cột thì không đăng nhập được. Trang đăng ký vẫn mở.
Chỉ kiểm tra MỘT LẦN lúc khởi động: chạy migration xong phải khởi động lại app.
"""
from flask import current_app, jsonify, render_template, request
from sqlalchemy.exc import OperationalError, ProgrammingError

from event_checkin.migrations import m006_phan_quyen, m007_certificate_token

CHECKS = (
    ("m006", m006_phan_quyen.schema_problems),
    ("m007", m007_certificate_token.schema_problems),
)
EXTENSION_KEY = "pending_migrations"
CERT_MAINTENANCE_MESSAGE = "Hệ thống chứng chỉ đang bảo trì. Vui lòng thử lại sau."
ACCOUNT_MAINTENANCE_MESSAGE = "Hệ thống quản trị đang bảo trì. Vui lòng thử lại sau."
# Blueprint đọc bảng admins dù route là công khai (đăng nhập, quên mật khẩu...)
ACCOUNT_BLUEPRINTS = {"admin", "staff", "password", "account", "checkin", "lucky"}


def migration_message(name, found):
    return f"Chưa chạy migration {name}, xem DEPLOYMENT.md ({'; '.join(found)})."


def check_migrations():
    """{tên migration: [vấn đề]} cho những migration chưa chạy đủ (rỗng = DB đã đủ). Cần app context."""
    pending = {}
    for name, schema_problems in CHECKS:
        try:
            found = schema_problems()
        except (OperationalError, ProgrammingError) as error:
            found = [f"không kiểm tra được ({error.__class__.__name__})"]
        if found:
            pending[name] = found
    return pending


def pending_migrations(app=None):
    return (app or current_app).extensions.get(EXTENSION_KEY, {})


def _wants_json():
    if request.method not in ("GET", "HEAD"):
        return True
    if request.blueprint == "certificates":
        # Link chứng chỉ công khai (kể cả link cũ /api/certificates/<mã> trong email) được mở bằng trình duyệt
        from event_checkin.controllers.certificate_controller import PUBLIC_ENDPOINTS

        if request.endpoint in PUBLIC_ENDPOINTS:
            return False
    return request.path.startswith("/api/")


def maintenance_response(message):
    if _wants_json():
        response = jsonify({"success": False, "code": "maintenance", "message": message})
    else:
        response = current_app.make_response(render_template("maintenance.html", message=message))
    response.status_code = 503
    response.headers["Retry-After"] = "300"
    response.headers["Cache-Control"] = "no-store"
    return response


def _blocked_message():
    """Thông báo bảo trì nếu request này chạm phần DB còn thiếu, hoặc None."""
    pending = pending_migrations()
    if not pending or request.endpoint in (None, "static"):
        return None
    if "m006" in pending:
        from event_checkin import permissions as perm

        view = current_app.view_functions.get(request.endpoint)
        if request.blueprint in ACCOUNT_BLUEPRINTS or getattr(view, "required_access", None) != perm.PUBLIC:
            return ACCOUNT_MAINTENANCE_MESSAGE
    if "m007" in pending and request.blueprint == "certificates":
        return CERT_MAINTENANCE_MESSAGE
    return None


def block_unmigrated_routes():
    message = _blocked_message()
    return maintenance_response(message) if message else None


def handle_database_error(error):
    """Lỗi DB còn sót (vd. trang admin có đọc bảng certificates) khi đang thiếu migration -> trang bảo trì thay
    cho 500. DB đã đủ migration thì đây là lỗi thật: để Flask xử lý như bình thường (500 + log)."""
    pending = pending_migrations()
    if not pending:
        raise error
    from event_checkin.models import db

    db.session.rollback()
    current_app.logger.error("Lỗi DB khi chưa chạy đủ migration (%s): %s", ", ".join(pending), error.orig)
    return maintenance_response(ACCOUNT_MAINTENANCE_MESSAGE if "m006" in pending else CERT_MAINTENANCE_MESSAGE)


def _template_context():
    pending = pending_migrations()
    show = bool(pending) and request.path.startswith(("/admin", "/staff"))
    return {"migration_warnings": [migration_message(name, found) for name, found in pending.items()] if show else []}


def init_schema_status(app):
    """Đăng ký hook. Gọi TRƯỚC init_access: before_request chạy theo thứ tự đăng ký, phải chặn trước bước đọc
    tài khoản đăng nhập (bảng admins)."""
    app.extensions[EXTENSION_KEY] = {}
    app.before_request(block_unmigrated_routes)
    app.register_error_handler(OperationalError, handle_database_error)
    app.register_error_handler(ProgrammingError, handle_database_error)
    app.context_processor(_template_context)


def record_pending_migrations(app):
    """Kiểm tra DB và ghi log lỗi cho migration còn thiếu. Gọi trong app context, sau db.create_all và
    ensure_schema_upgrades."""
    pending = check_migrations()
    app.extensions[EXTENSION_KEY] = pending
    for name, found in pending.items():
        app.logger.error(migration_message(name, found))
    return pending
