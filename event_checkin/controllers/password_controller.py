"""Đổi mật khẩu, quên mật khẩu (qua email), đặt lại mật khẩu bằng link."""
import logging
import re
import threading
from datetime import datetime, timedelta

from flask import Blueprint, current_app, jsonify, render_template, request, session, url_for
from sqlalchemy import func, or_
from werkzeug.security import check_password_hash, generate_password_hash

from event_checkin import permissions as perm
from event_checkin import security
from event_checkin.access import access, get_current_admin
from event_checkin.audit import client_ip, log_action
from event_checkin.models import db
from event_checkin.models.admin import Admin
from event_checkin.models.audit_log import AuditLog
from event_checkin.models.password_reset import PasswordReset
from event_checkin.permissions import home_path_for_role
from event_checkin.utils.email_service import send_system_email

logger = logging.getLogger(__name__)

password_bp = Blueprint("password", __name__)

RESET_TOKEN_MINUTES = 30        # link hết hạn sau 30 phút và chỉ dùng 1 lần
FORGOT_LIMIT = 3                # tối đa 3 yêu cầu ...
FORGOT_WINDOW_MINUTES = 15      # ... trong 15 phút, tính riêng theo email và theo IP
FORGOT_SENT_MESSAGE = "Đã gửi liên kết đặt lại mật khẩu tới email của bạn. Vui lòng kiểm tra hộp thư (kể cả mục Spam)."
FORGOT_UNKNOWN_MESSAGE = "Email này chưa đăng ký tài khoản."
FORGOT_LOCKED_MESSAGE = "Tài khoản dùng email này đang bị khóa. Vui lòng liên hệ quản trị viên."
FORGOT_THROTTLED_PREFIX = "Bạn đã yêu cầu quá nhiều lần."


def _throttled_message(wait):
    """Câu báo khi vượt giới hạn, kèm số phút còn phải đợi (làm tròn lên, tối thiểu 1 phút)."""
    minutes = max(1, -(-int(wait.total_seconds()) // 60))
    return f"{FORGOT_THROTTLED_PREFIX} Vui lòng đợi {minutes} phút rồi thử lại."
INVALID_LINK_MESSAGE = "Liên kết không hợp lệ hoặc đã hết hạn. Hãy yêu cầu đặt lại mật khẩu để nhận liên kết mới."
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


# ---- Đổi mật khẩu của chính mình ---------------------------------------------------------------------------

@password_bp.get("/admin/change-password")
@access(perm.AUTHENTICATED)
def change_page():
    admin = get_current_admin()
    return render_template("admin/change_password.html", forced=bool(admin.must_change_password))


@password_bp.post("/api/admin/change-password")
@access(perm.AUTHENTICATED)
def change_api():
    admin = get_current_admin()
    payload = request.get_json(silent=True) or request.form
    current = payload.get("current_password") or ""
    new_password = payload.get("new_password") or ""
    if not check_password_hash(admin.password_hash, current):
        return jsonify({"success": False, "message": "Mật khẩu hiện tại không đúng."}), 400
    error = security.password_error(new_password)
    if error:
        return jsonify({"success": False, "message": error}), 400
    if payload.get("confirm_password") is not None and payload.get("confirm_password") != new_password:
        return jsonify({"success": False, "message": "Nhập lại mật khẩu mới chưa khớp."}), 400
    if new_password == current:
        return jsonify({"success": False, "message": "Mật khẩu mới phải khác mật khẩu hiện tại."}), 400

    admin.password_hash = generate_password_hash(new_password)
    admin.must_change_password = False
    admin.session_version = (admin.session_version or 0) + 1   # đăng xuất mọi phiên cũ (kể cả thiết bị khác)
    admin.updated_at = datetime.utcnow()
    db.session.commit()
    session["sv"] = admin.session_version                       # riêng phiên hiện tại được giữ lại
    log_action("password.change", "account", admin.id, admin=admin)
    return jsonify({"success": True, "message": "Đã đổi mật khẩu.", "home_path": home_path_for_role(admin.role)})


# ---- Quên mật khẩu -----------------------------------------------------------------------------------------

@password_bp.get("/admin/forgot-password")
@access(perm.PUBLIC)
def forgot_page():
    return render_template("admin/forgot_password.html")


def _run_async(function, *args):
    """Gửi email ở luồng riêng: thời gian phản hồi không phụ thuộc email có tồn tại hay không (không lộ qua độ trễ)."""
    app = current_app._get_current_object()

    def runner():
        with app.app_context():
            try:
                function(*args)
            except Exception:  # noqa: BLE001
                logger.exception("Gửi email đặt lại mật khẩu thất bại")

    threading.Thread(target=runner, daemon=True).start()


def _send_reset_mail(to_email, username, link):
    subject = "Đặt lại mật khẩu"
    text = (
        f"Xin chào {username},\n\n"
        "Chúng tôi nhận được yêu cầu đặt lại mật khẩu cho tài khoản của bạn. "
        f"Bấm vào liên kết dưới đây để đặt mật khẩu mới (liên kết có hiệu lực {RESET_TOKEN_MINUTES} phút và chỉ dùng được một lần):\n\n"
        f"{link}\n\n"
        "Nếu bạn không yêu cầu, hãy bỏ qua thư này; mật khẩu hiện tại vẫn giữ nguyên."
    )
    html = (
        f"<p>Xin chào <b>{username}</b>,</p>"
        "<p>Chúng tôi nhận được yêu cầu đặt lại mật khẩu cho tài khoản của bạn. "
        f"Liên kết có hiệu lực <b>{RESET_TOKEN_MINUTES} phút</b> và chỉ dùng được một lần:</p>"
        f'<p><a href="{link}">Đặt mật khẩu mới</a></p>'
        "<p>Nếu bạn không yêu cầu, hãy bỏ qua thư này; mật khẩu hiện tại vẫn giữ nguyên.</p>"
    )
    ok, error = send_system_email(to_email, subject, text, html)
    if not ok:
        logger.warning("Không gửi được email đặt lại mật khẩu: %s", error)


@password_bp.post("/api/admin/forgot-password")
@access(perm.PUBLIC)
def forgot_api():
    payload = request.get_json(silent=True) or request.form
    email = (payload.get("email") or "").strip().lower()
    if not email or not EMAIL_PATTERN.match(email):
        return jsonify({"success": False, "message": "Vui lòng nhập email hợp lệ."}), 400

    ip = client_ip()
    key = security.hash_email_key(email)
    now = datetime.utcnow()
    window = timedelta(minutes=FORGOT_WINDOW_MINUTES)
    recent = [row.created_at for row in AuditLog.query.with_entities(AuditLog.created_at).filter(
        AuditLog.action == "password.forgot_request",
        AuditLog.created_at >= now - window,
        or_(AuditLog.target_id == key, AuditLog.ip == ip) if ip else AuditLog.target_id == key,
    ).order_by(AuditLog.created_at).all()]
    if len(recent) >= FORGOT_LIMIT:
        # Quá số lần: chặn trước khi tra email, nên giới hạn này cũng hạn chế việc dò xem email nào đã có tài khoản.
        # Báo số phút còn phải đợi: đến khi đủ yêu cầu cũ ra khỏi cửa sổ để số yêu cầu xuống dưới giới hạn.
        log_action("password.forgot_throttled", "email_hash", key)
        return jsonify({"success": False, "message": _throttled_message(recent[len(recent) - FORGOT_LIMIT] + window - now)}), 429

    log_action("password.forgot_request", "email_hash", key)

    admin = Admin.query.filter(func.lower(Admin.email) == email).first()
    if not admin:
        return jsonify({"success": False, "message": FORGOT_UNKNOWN_MESSAGE}), 404
    if not admin.is_active:
        return jsonify({"success": False, "message": FORGOT_LOCKED_MESSAGE}), 403
    token = security.new_reset_token()
    now = datetime.utcnow()
    # Link mới làm các link cũ chưa dùng của tài khoản này mất hiệu lực
    PasswordReset.query.filter(PasswordReset.admin_id == admin.id, PasswordReset.used_at.is_(None)).update({"used_at": now})
    db.session.add(PasswordReset(
        admin_id=admin.id,
        token_hash=security.hash_token(token),
        expires_at=now + timedelta(minutes=RESET_TOKEN_MINUTES),
    ))
    db.session.commit()
    link = url_for("password.reset_page", token=token, _external=True)
    if not current_app.config.get("IS_PRODUCTION"):
        logger.info("[DEV] Link đặt lại mật khẩu cho %s: %s", admin.username, link)
    _run_async(_send_reset_mail, admin.email, admin.username, link)
    return jsonify({"success": True, "message": FORGOT_SENT_MESSAGE})


# ---- Đặt lại mật khẩu bằng link ---------------------------------------------------------------------------

def _find_valid_reset(token):
    reset = PasswordReset.query.filter_by(token_hash=security.hash_token(token)).first()
    if not reset or reset.used_at is not None or reset.expires_at <= datetime.utcnow():
        return None, None
    admin = db.session.get(Admin, reset.admin_id)
    if not admin or not admin.is_active:
        return None, None
    return reset, admin


@password_bp.get("/admin/reset-password/<token>")
@access(perm.PUBLIC)
def reset_page(token):
    reset, _admin = _find_valid_reset(token)
    return render_template("admin/reset_password.html", token=token, valid=reset is not None, invalid_message=INVALID_LINK_MESSAGE)


@password_bp.post("/api/admin/reset-password")
@access(perm.PUBLIC)
def reset_api():
    payload = request.get_json(silent=True) or request.form
    token = payload.get("token") or ""
    password = payload.get("password") or ""
    reset, admin = _find_valid_reset(token)
    if reset is None:
        return jsonify({"success": False, "message": INVALID_LINK_MESSAGE}), 400
    error = security.password_error(password)
    if error:
        return jsonify({"success": False, "message": error}), 400
    if payload.get("confirm_password") is not None and payload.get("confirm_password") != password:
        return jsonify({"success": False, "message": "Nhập lại mật khẩu mới chưa khớp."}), 400

    now = datetime.utcnow()
    admin.password_hash = generate_password_hash(password)
    admin.must_change_password = False
    admin.session_version = (admin.session_version or 0) + 1   # đăng xuất mọi phiên cũ
    admin.updated_at = now
    PasswordReset.query.filter(PasswordReset.admin_id == admin.id, PasswordReset.used_at.is_(None)).update({"used_at": now})
    db.session.commit()
    log_action("password.reset_done", "account", admin.id, admin=admin)
    return jsonify({"success": True, "message": "Đã đặt lại mật khẩu. Hãy đăng nhập bằng mật khẩu mới.", "login_url": url_for("admin.login_page")})
