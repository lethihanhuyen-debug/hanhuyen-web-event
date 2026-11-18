"""Quản lý tài khoản (chỉ super_admin) và trang Nhật ký hoạt động."""
import re
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, render_template, request
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash

from event_checkin import permissions as perm
from event_checkin import security
from event_checkin.access import access, get_current_admin
from event_checkin.audit import ACTION_LABELS, action_label, log_action
from event_checkin.models import db
from event_checkin.models.admin import Admin
from event_checkin.models.audit_log import AuditLog
from event_checkin.models.checkin_record import CheckinRecord
from event_checkin.models.event import Event
from event_checkin.models.password_reset import PasswordReset
from event_checkin.utils.timezone import format_utc_as_vn

account_bp = Blueprint("account", __name__)

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,50}$")
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
AUDIT_PAGE_SIZE = 50


def _error(message, status=400):
    return jsonify({"success": False, "message": message}), status


def _payload(admin, current_id):
    return {
        "id": admin.id,
        "username": admin.username,
        "email": admin.email or "",
        "role": admin.role,
        "role_label": perm.role_label(admin.role),
        "is_active": bool(admin.is_active),
        "must_change_password": bool(admin.must_change_password),
        "last_login_at": format_utc_as_vn(admin.last_login_at) if admin.last_login_at else "",
        "created_at": format_utc_as_vn(admin.created_at) if admin.created_at else "",
        "is_self": admin.id == current_id,
    }


def _is_last_active_super_admin(target):
    """True nếu `target` đang là super_admin hoạt động DUY NHẤT (mất người này thì không còn ai quản lý hệ thống)."""
    if target.role != perm.ROLE_SUPER_ADMIN or not target.is_active:
        return False
    others = Admin.query.filter(
        Admin.role == perm.ROLE_SUPER_ADMIN, Admin.is_active.is_(True), Admin.id != target.id
    ).count()
    return others == 0


def _normalize_email(raw):
    email = (raw or "").strip().lower()
    if not email:
        return None, None
    if len(email) > 255 or not EMAIL_PATTERN.match(email):
        return None, "Email không hợp lệ."
    return email, None


def _bump_session(admin):
    """Làm mọi phiên đăng nhập đang mở của tài khoản này mất hiệu lực ngay."""
    admin.session_version = (admin.session_version or 0) + 1
    admin.updated_at = datetime.utcnow()


# ---- Trang + danh sách -------------------------------------------------------------------------------------

@account_bp.get("/admin/accounts")
@access(perm.ACCOUNT_MANAGE)
def accounts_page():
    return render_template("admin/accounts.html", roles=[(r, perm.role_label(r)) for r in perm.ROLES])


@account_bp.get("/api/admin/accounts")
@access(perm.ACCOUNT_MANAGE)
def list_accounts():
    current = get_current_admin()
    query = Admin.query
    keyword = (request.args.get("q") or "").strip()
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(or_(Admin.username.ilike(like), Admin.email.ilike(like)))
    items = query.order_by(Admin.id.asc()).all()
    return jsonify({"success": True, "data": [_payload(item, current.id) for item in items]})


# ---- Tạo / sửa ---------------------------------------------------------------------------------------------

@account_bp.post("/api/admin/accounts")
@access(perm.ACCOUNT_MANAGE)
def create_account():
    current = get_current_admin()
    payload = request.get_json(silent=True) or request.form
    username = (payload.get("username") or "").strip()
    role = (payload.get("role") or "").strip()
    email, email_error = _normalize_email(payload.get("email"))
    if not USERNAME_PATTERN.match(username):
        return _error("Tên đăng nhập gồm 3-50 ký tự: chữ không dấu, số, dấu chấm, gạch dưới hoặc gạch ngang.")
    if not perm.is_valid_role(role):
        return _error("Vai trò không hợp lệ.")
    if email_error:
        return _error(email_error)
    if Admin.query.filter(db.func.lower(Admin.username) == username.lower()).first():
        return _error(f"Tên đăng nhập '{username}' đã tồn tại.", 409)
    if email and Admin.query.filter(db.func.lower(Admin.email) == email).first():
        return _error("Email này đã được tài khoản khác dùng.", 409)

    temp_password = security.generate_temp_password()
    admin = Admin(
        username=username,
        password_hash=generate_password_hash(temp_password),
        role=role,
        is_active=True,
        email=email,
        must_change_password=True,      # bắt buộc đổi mật khẩu tạm ở lần đăng nhập đầu
        created_by=current.id,
    )
    db.session.add(admin)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _error("Tên đăng nhập hoặc email đã tồn tại.", 409)
    log_action("account.create", "account", admin.id, {"username": username, "role": role})
    return jsonify({
        "success": True,
        "message": f"Đã tạo tài khoản {username}.",
        "data": _payload(admin, current.id),
        "temp_password": temp_password,   # chỉ hiện đúng 1 lần ở phản hồi này
    }), 201


@account_bp.put("/api/admin/accounts/<int:account_id>")
@access(perm.ACCOUNT_MANAGE)
def update_account(account_id):
    current = get_current_admin()
    admin = db.get_or_404(Admin, account_id)
    payload = request.get_json(silent=True) or request.form
    changes = {}

    if "role" in payload and (payload.get("role") or "").strip() != admin.role:
        new_role = (payload.get("role") or "").strip()
        if not perm.is_valid_role(new_role):
            return _error("Vai trò không hợp lệ.")
        if admin.id == current.id:
            return _error("Bạn không thể tự đổi vai trò của chính mình.", 409)
        if new_role != perm.ROLE_SUPER_ADMIN and _is_last_active_super_admin(admin):
            return _error("Đây là quản trị cao cấp cuối cùng đang hoạt động, không thể hạ quyền.", 409)
        changes["role"] = (admin.role, new_role)

    if "email" in payload:
        email, email_error = _normalize_email(payload.get("email"))
        if email_error:
            return _error(email_error)
        if email != (admin.email or None):
            if email and Admin.query.filter(db.func.lower(Admin.email) == email, Admin.id != admin.id).first():
                return _error("Email này đã được tài khoản khác dùng.", 409)
            changes["email"] = (admin.email, email)

    if not changes:
        return jsonify({"success": True, "message": "Không có thay đổi.", "data": _payload(admin, current.id)})

    if "role" in changes:
        admin.role = changes["role"][1]
        _bump_session(admin)            # đổi quyền có hiệu lực ngay: phiên cũ bị đăng xuất
    if "email" in changes:
        admin.email = changes["email"][1]
        admin.updated_at = datetime.utcnow()
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _error("Email này đã được tài khoản khác dùng.", 409)

    if "role" in changes:
        log_action("account.role_change", "account", admin.id,
                   {"username": admin.username, "from": changes["role"][0], "to": changes["role"][1]})
    if "email" in changes:
        log_action("account.update", "account", admin.id, {"username": admin.username, "fields": ["email"]})
    return jsonify({"success": True, "message": "Đã cập nhật tài khoản.", "data": _payload(admin, current.id)})


# ---- Khóa / mở khóa / xóa / đặt lại mật khẩu -------------------------------------------------------------------

@account_bp.post("/api/admin/accounts/<int:account_id>/lock")
@access(perm.ACCOUNT_MANAGE)
def lock_account(account_id):
    current = get_current_admin()
    admin = db.get_or_404(Admin, account_id)
    if admin.id == current.id:
        return _error("Bạn không thể tự khóa tài khoản của chính mình.", 409)
    if _is_last_active_super_admin(admin):
        return _error("Đây là quản trị cao cấp cuối cùng đang hoạt động, không thể khóa.", 409)
    admin.is_active = False
    _bump_session(admin)
    db.session.commit()
    log_action("account.lock", "account", admin.id, {"username": admin.username})
    return jsonify({"success": True, "message": f"Đã khóa tài khoản {admin.username}.", "data": _payload(admin, current.id)})


@account_bp.post("/api/admin/accounts/<int:account_id>/unlock")
@access(perm.ACCOUNT_MANAGE)
def unlock_account(account_id):
    current = get_current_admin()
    admin = db.get_or_404(Admin, account_id)
    admin.is_active = True
    admin.updated_at = datetime.utcnow()
    db.session.commit()
    log_action("account.unlock", "account", admin.id, {"username": admin.username})
    return jsonify({"success": True, "message": f"Đã mở khóa tài khoản {admin.username}.", "data": _payload(admin, current.id)})


@account_bp.delete("/api/admin/accounts/<int:account_id>")
@access(perm.ACCOUNT_MANAGE)
def delete_account(account_id):
    current = get_current_admin()
    admin = db.get_or_404(Admin, account_id)
    if admin.id == current.id:
        return _error("Bạn không thể tự xóa tài khoản của chính mình.", 409)
    if _is_last_active_super_admin(admin):
        return _error("Đây là quản trị cao cấp cuối cùng đang hoạt động, không thể xóa.", 409)

    # Tài khoản đã gắn với dữ liệu (sự kiện đã tạo/sửa, lượt check-in, tài khoản do mình tạo) thì không xóa được:
    # xóa sẽ làm mất "ai đã làm" của dữ liệu đó. Khuyên khóa thay vì xóa.
    related = (
        Event.query.filter(or_(Event.created_by == admin.id, Event.updated_by == admin.id)).count()
        + CheckinRecord.query.filter(CheckinRecord.checked_in_by == admin.id).count()
        + Admin.query.filter(Admin.created_by == admin.id).count()
    )
    if related:
        return _error(
            f"Tài khoản này đã gắn với {related} dữ liệu (sự kiện, lượt check-in hoặc tài khoản do họ tạo) nên không thể xóa. "
            "Hãy khóa tài khoản thay vì xóa.", 409)

    username = admin.username
    PasswordReset.query.filter_by(admin_id=admin.id).delete()
    db.session.delete(admin)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _error("Tài khoản này đang được dữ liệu khác sử dụng nên không thể xóa. Hãy khóa tài khoản thay vì xóa.", 409)
    log_action("account.delete", "account", account_id, {"username": username})
    return jsonify({"success": True, "message": f"Đã xóa tài khoản {username}."})


@account_bp.post("/api/admin/accounts/<int:account_id>/reset-password")
@access(perm.ACCOUNT_MANAGE)
def reset_account_password(account_id):
    current = get_current_admin()
    admin = db.get_or_404(Admin, account_id)
    if admin.id == current.id:
        return _error("Hãy dùng chức năng Đổi mật khẩu cho chính mình.", 409)
    temp_password = security.generate_temp_password()
    admin.password_hash = generate_password_hash(temp_password)
    admin.must_change_password = True
    _bump_session(admin)                # đăng xuất mọi phiên đang mở của tài khoản này
    PasswordReset.query.filter(PasswordReset.admin_id == admin.id, PasswordReset.used_at.is_(None)).update({"used_at": datetime.utcnow()})
    db.session.commit()
    log_action("account.reset_password", "account", admin.id, {"username": admin.username})
    return jsonify({
        "success": True,
        "message": f"Đã đặt lại mật khẩu cho {admin.username}.",
        "temp_password": temp_password,   # chỉ hiện đúng 1 lần
        "data": _payload(admin, current.id),
    })


# ---- Nhật ký hoạt động -------------------------------------------------------------------------------------

@account_bp.get("/admin/audit-log")
@access(perm.AUDIT_VIEW)
def audit_page():
    actions = sorted(ACTION_LABELS.items(), key=lambda pair: pair[1])
    return render_template("admin/audit_log.html", actions=actions)


def _parse_vn_day(value):
    """'YYYY-MM-DD' (ngày theo giờ Việt Nam) -> thời điểm 00:00 hôm đó quy ra UTC; sai định dạng -> None."""
    try:
        return datetime.strptime(value, "%Y-%m-%d") - timedelta(hours=7)
    except (TypeError, ValueError):
        return None


@account_bp.get("/api/admin/audit-logs")
@access(perm.AUDIT_VIEW)
def list_audit_logs():
    query = AuditLog.query
    who = (request.args.get("user") or "").strip()
    if who:
        query = query.filter(AuditLog.username.ilike(f"%{who}%"))
    action = (request.args.get("action") or "").strip()
    if action:
        query = query.filter(AuditLog.action == action)
    start = _parse_vn_day(request.args.get("from"))
    if start:
        query = query.filter(AuditLog.created_at >= start)
    end = _parse_vn_day(request.args.get("to"))
    if end:
        query = query.filter(AuditLog.created_at < end + timedelta(days=1))

    try:
        page = max(int(request.args.get("page", 1)), 1)
    except ValueError:
        page = 1
    total = query.count()
    rows = (
        query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset((page - 1) * AUDIT_PAGE_SIZE).limit(AUDIT_PAGE_SIZE).all()
    )
    return jsonify({
        "success": True,
        "data": [{
            "id": row.id,
            "time": format_utc_as_vn(row.created_at, "%d/%m/%Y %H:%M:%S"),
            "username": row.username or "(không đăng nhập)",
            "action": row.action,
            "action_label": action_label(row.action),
            "target": " ".join(part for part in (row.target_type, row.target_id) if part),
            "detail": row.detail or "",
            "ip": row.ip or "",
        } for row in rows],
        "page": page,
        "page_size": AUDIT_PAGE_SIZE,
        "total": total,
    })
