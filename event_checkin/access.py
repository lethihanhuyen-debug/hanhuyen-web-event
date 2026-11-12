"""Kiểm tra quyền truy cập cho MỌI route, theo nguyên tắc "mặc định chặn".

Cách dùng: mỗi view khai báo đúng MỘT mức truy cập bằng decorator `@access(...)` đặt ngay trên `def`
(dưới các `@bp.get/post/...`):

    @admin_bp.delete("/api/admin/events/<int:event_id>")
    @access(perm.EVENT_DELETE)
    def delete_event(event_id): ...

`@access` chỉ GẮN nhãn vào hàm; việc kiểm tra thật nằm ở `enforce_access` (đăng ký bằng before_request trong
create_app) nên không route nào lọt qua được chỉ vì quên bọc decorator:
- Route KHÔNG có nhãn -> bị từ chối với mọi người (kể cả super_admin) cho đến khi khai báo.
- PUBLIC -> ai cũng vào được. AUTHENTICATED -> mọi tài khoản đã đăng nhập. Còn lại -> tên quyền trong permissions.py.

Mỗi request đọc lại tài khoản từ DB (is_active, role, session_version) nên khóa tài khoản / đổi quyền / đổi mật khẩu
có hiệu lực ngay ở request kế tiếp, không phải chờ hết phiên.
"""
from flask import current_app, g, jsonify, redirect, request, session, url_for

from event_checkin import permissions as perm
from event_checkin.models import db
from event_checkin.models.admin import Admin


NOT_LOGGED_IN_MESSAGE = "Vui lòng đăng nhập admin."
NO_PERMISSION_MESSAGE = "Bạn không có quyền thực hiện thao tác này."
# Câu báo 403 cụ thể theo thao tác bị cấm (giao diện hiện nguyên văn); quyền không có trong bảng dùng câu chung.
DENIED_MESSAGES = {
    perm.EVENT_DELETE: "Bạn không có quyền xóa sự kiện. Chỉ quản trị cao cấp được xóa sự kiện.",
    perm.SYSTEM_RESET: "Bạn không có quyền xóa toàn bộ dữ liệu. Chỉ quản trị cao cấp được thực hiện.",
    perm.ACCOUNT_MANAGE: "Bạn không có quyền quản lý tài khoản.",
    perm.AUDIT_VIEW: "Bạn không có quyền xem nhật ký hoạt động.",
    perm.EVENT_MANAGE: "Bạn không có quyền tạo hoặc sửa sự kiện.",
    perm.CHECKIN_MANAGE: "Bạn không có quyền sửa dữ liệu check-in.",
    perm.CERTIFICATE_MANAGE: "Bạn không có quyền quản lý hoặc gửi chứng chỉ.",
    perm.DATA_EXPORT: "Bạn không có quyền xuất dữ liệu.",
    perm.DONVI_MANAGE: "Bạn không có quyền quản lý đơn vị.",
    perm.LUCKY_MANAGE: "Bạn không có quyền sử dụng chức năng quay số may mắn.",
}
NO_PAGE_PERMISSION_MESSAGE = "Bạn không có quyền truy cập trang đó nên đã được chuyển về trang của bạn."


def access(permission):
    """Gắn mức truy cập cho view. Sai tên quyền thì lỗi ngay lúc import (không để lọt đến lúc chạy)."""
    if permission not in (perm.PUBLIC, perm.AUTHENTICATED) and permission not in perm.ALL_PERMISSIONS:
        raise ValueError(f"Quyền không tồn tại: {permission!r}")

    def decorator(view):
        view.required_access = permission
        return view

    return decorator


def get_current_admin():
    """Tài khoản đang đăng nhập hợp lệ, hoặc None. Đọc DB 1 lần mỗi request (cache trong `g`).

    Phiên bị coi là hết hiệu lực (và được dọn) khi: tài khoản không còn/bị khóa, vai trò không hợp lệ, hoặc
    `session_version` trong cookie khác DB (đã đổi mật khẩu/quyền sau lúc đăng nhập, hoặc phiên cũ trước khi có
    phân quyền)."""
    if "current_admin" in g:
        return g.current_admin
    admin = None
    admin_id = session.get("admin_id")
    if admin_id:
        admin = db.session.get(Admin, admin_id)
        if (
            not admin
            or not admin.is_active
            or not perm.is_valid_role(admin.role)
            or session.get("sv") != admin.session_version
        ):
            admin = None
            session.clear()
    g.current_admin = admin
    return admin


def _wants_json():
    # Gồm cả POST/PUT/DELETE ngoài /api/ (vd. POST /admin/reset): các thao tác ghi không nên nhận trang HTML/redirect.
    return request.path.startswith("/api/") or request.method not in ("GET", "HEAD")


def _unauthenticated_response():
    if _wants_json():
        return jsonify({"success": False, "message": NOT_LOGGED_IN_MESSAGE}), 401
    next_url = request.full_path if request.query_string else request.path
    return redirect(url_for("admin.login_page", next=next_url))


def _forbidden_response(admin, required=None):
    if _wants_json():
        return jsonify({"success": False, "message": DENIED_MESSAGES.get(required, NO_PERMISSION_MESSAGE)}), 403
    target = perm.home_path_for_role(admin.role)
    if target == request.path:
        # Trang đích của chính vai trò này cũng bị từ chối (cấu hình sai) -> không redirect vòng.
        return jsonify({"success": False, "message": NO_PERMISSION_MESSAGE}), 403
    session["access_notice"] = NO_PAGE_PERMISSION_MESSAGE
    return redirect(target)


def enforce_access():
    endpoint = request.endpoint
    # Không khớp route nào -> để Flask tự trả 404/405 (không lộ route nào tồn tại). /static là file tĩnh.
    if endpoint is None or endpoint == "static":
        return None

    view = current_app.view_functions.get(endpoint)
    required = getattr(view, "required_access", None)
    if required == perm.PUBLIC:
        return None

    admin = get_current_admin()
    if admin is None:
        return _unauthenticated_response()
    if required is None:
        current_app.logger.error("Route %s chưa khai báo quyền (@access) -> mặc định từ chối.", endpoint)
        return _forbidden_response(admin)
    if perm.has_permission(admin.role, required):
        return None
    return _forbidden_response(admin, required)


def _pop_access_notice():
    return session.pop("access_notice", None)


def _template_context():
    admin = get_current_admin() if session.get("admin_id") else None
    return {
        "current_admin": admin,
        "admin_home_path": perm.home_path_for_role(admin.role) if admin else None,
        "admin_role_label": perm.role_label(admin.role) if admin else None,
        "can": (lambda permission: bool(admin) and perm.has_permission(admin.role, permission)),
        # base.html gọi hàm này để hiện thông báo "không đủ quyền" đúng 1 lần (không bị HTML con tiêu thụ nhầm).
        "pop_access_notice": _pop_access_notice,
    }


def init_access(app):
    app.before_request(enforce_access)
    app.context_processor(_template_context)
