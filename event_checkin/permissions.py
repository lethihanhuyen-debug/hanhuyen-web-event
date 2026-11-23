"""Phân quyền tập trung: vai trò -> tập quyền. Thêm/bớt quyền chỉ cần sửa file này.

Ba vai trò (từ thấp đến cao):
- staff        : nhân viên check-in. Xem sự kiện/người đăng ký (ẩn thông tin liên lạc) và check-in.
- admin        : quản lý sự kiện, check-in, chứng chỉ, xuất dữ liệu, đơn vị, quay số. KHÔNG xóa sự kiện,
                 KHÔNG quản lý tài khoản, KHÔNG xem nhật ký, KHÔNG dùng /admin/reset.
- super_admin  : toàn quyền.

Mỗi route được khai báo MỘT mức truy cập (bước b sẽ gắn vào toàn bộ route):
- PUBLIC         : ai cũng truy cập được (không cần đăng nhập)
- AUTHENTICATED  : mọi tài khoản đã đăng nhập (đổi mật khẩu, đăng xuất, /api/admin/me)
- <tên quyền>    : tài khoản đăng nhập và vai trò có quyền đó (xem ROLE_PERMISSIONS)

File này chỉ chứa dữ liệu + hàm thuần Python, KHÔNG import Flask/DB để import ở đâu cũng được.
"""

ROLE_STAFF = "staff"
ROLE_ADMIN = "admin"
ROLE_SUPER_ADMIN = "super_admin"

# Thứ tự từ thấp đến cao; dùng cho giao diện (dropdown) và so sánh cấp bậc.
ROLES = (ROLE_STAFF, ROLE_ADMIN, ROLE_SUPER_ADMIN)

ROLE_LABELS = {
    ROLE_STAFF: "Nhân viên check-in",
    ROLE_ADMIN: "Quản trị viên",
    ROLE_SUPER_ADMIN: "Quản trị cao cấp",
}

# Trang đích sau đăng nhập / khi bị từ chối vì thiếu quyền (route /staff/events sẽ có ở bước c).
ROLE_HOME_PATHS = {
    ROLE_STAFF: "/staff/events",
    ROLE_ADMIN: "/admin",
    ROLE_SUPER_ADMIN: "/admin",
}

# Mức truy cập đặc biệt (không phải tên quyền).
PUBLIC = "public"
AUTHENTICATED = "authenticated"

# ---- Tên quyền -----------------------------------------------------------------------------------------------

# Quyền của staff (admin và super_admin cũng có).
EVENT_VIEW = "event.view"                  # xem danh sách/chi tiết sự kiện ở chế độ chỉ xem
CHECKIN_VIEW = "checkin.view"              # xem danh sách đã check-in (ẩn email, trạng thái chứng chỉ)
CHECKIN_PERFORM = "checkin.perform"        # thực hiện check-in
PATRON_LOOKUP = "patron.lookup"            # tra mã CB/SV (trả họ tên + đơn vị)

# Quyền thêm của admin.
ADMIN_AREA = "admin.area"                  # vào khu /admin (trang tổng, dashboard)
REGISTRATION_VIEW_FULL = "registration.view_full"  # xem đủ thông tin đăng ký (email, SĐT, câu hỏi)
REGISTRATION_DELETE = "registration.delete"        # hủy (xóa mềm) / khôi phục đăng ký của người đăng ký
EVENT_MANAGE = "event.manage"              # tạo/sửa sự kiện, ảnh sự kiện
CHECKIN_MANAGE = "checkin.manage"          # thêm tay/import/xóa/gộp trùng check-in, sửa tên in chứng chỉ
CERTIFICATE_MANAGE = "certificate.manage"  # gửi/gửi lại/tạo chứng chỉ; mẫu, bố cục, font; kho chứng chỉ
DATA_EXPORT = "data.export"                # xuất Excel/CSV
DONVI_MANAGE = "donvi.manage"              # quản lý đơn vị
LUCKY_MANAGE = "lucky.manage"              # bốc thăm may mắn

# Quyền thêm của super_admin.
EVENT_DELETE = "event.delete"              # xóa sự kiện
SYSTEM_RESET = "system.reset"              # /admin/reset: xóa toàn bộ dữ liệu
ACCOUNT_MANAGE = "account.manage"          # quản lý tài khoản, đổi vai trò, đặt lại mật khẩu
AUDIT_VIEW = "audit.view"                  # xem nhật ký hoạt động

_STAFF_PERMISSIONS = frozenset({
    EVENT_VIEW,
    CHECKIN_VIEW,
    CHECKIN_PERFORM,
    PATRON_LOOKUP,
})

_ADMIN_EXTRA = frozenset({
    ADMIN_AREA,
    REGISTRATION_VIEW_FULL,
    REGISTRATION_DELETE,
    EVENT_MANAGE,
    CHECKIN_MANAGE,
    CERTIFICATE_MANAGE,
    DATA_EXPORT,
    DONVI_MANAGE,
    LUCKY_MANAGE,
})

_SUPER_ADMIN_EXTRA = frozenset({
    EVENT_DELETE,
    SYSTEM_RESET,
    ACCOUNT_MANAGE,
    AUDIT_VIEW,
})

ROLE_PERMISSIONS = {
    ROLE_STAFF: _STAFF_PERMISSIONS,
    ROLE_ADMIN: _STAFF_PERMISSIONS | _ADMIN_EXTRA,
    ROLE_SUPER_ADMIN: _STAFF_PERMISSIONS | _ADMIN_EXTRA | _SUPER_ADMIN_EXTRA,
}

ALL_PERMISSIONS = frozenset().union(*ROLE_PERMISSIONS.values())


# ---- Hàm tiện ích --------------------------------------------------------------------------------------------

def is_valid_role(role):
    return role in ROLE_PERMISSIONS


def permissions_of(role):
    """Tập quyền của vai trò. Vai trò lạ/rỗng -> tập rỗng (không quyền gì): sai dữ liệu thì chặn, không mở."""
    return ROLE_PERMISSIONS.get(role, frozenset())


def has_permission(role, permission):
    """True nếu vai trò `role` có quyền `permission`. PUBLIC luôn đúng; AUTHENTICATED đúng với mọi vai trò hợp lệ.
    Tên quyền không có trong hệ thống -> ném lỗi (lỗi gõ sai tên quyền phải lộ ra ngay, không âm thầm từ chối/cho phép)."""
    if permission == PUBLIC:
        return True
    if permission == AUTHENTICATED:
        return is_valid_role(role)
    if permission not in ALL_PERMISSIONS:
        raise ValueError(f"Quyền không tồn tại: {permission!r}")
    return permission in permissions_of(role)


def home_path_for_role(role):
    """Trang đích theo vai trò; vai trò lạ -> trang đăng nhập."""
    return ROLE_HOME_PATHS.get(role, "/admin/login")


def role_label(role):
    return ROLE_LABELS.get(role, role or "")
