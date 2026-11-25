"""Tải / xem / xác minh chứng chỉ.

Công khai (không đăng nhập), mỗi IP tối đa CERT_PUBLIC_RATE_LIMIT request/phút cho tất cả các route dưới đây:
- /c/<token>, /c/<token>/view   tải / xem file. token ngẫu nhiên 32 ký tự (m007), không đoán được.
- /verify/t/<token>             trang xác minh, có nút tải (người có token là chủ chứng chỉ).
- /verify/<mã tuần tự>          trang xác minh TỐI THIỂU (họ tên, sự kiện, ngày, trạng thái), không có file.
- /api/certificates/<mã>[/view] link CŨ đã gửi qua email: phải nhập đúng mã CB/SV của người được cấp, đúng thì
                                chuyển sang link token. Sai tối đa 5 lần / 15 phút cho mỗi mã và mỗi IP.
Token/mã sai, chứng chỉ đã thu hồi, thiếu file đều trả 404 giống nhau.

Admin (quyền certificate.manage; staff không có): /api/admin/certificates/<mã>[/view].
"""
from datetime import datetime, timedelta

from flask import Blueprint, abort, current_app, jsonify, redirect, render_template, request, send_file, url_for

from event_checkin import permissions as perm
from event_checkin.access import access
from event_checkin.audit import audited, client_ip, log_action
from event_checkin.utils.rate_limit import PerIpRateLimiter
from event_checkin.certificates.service import (
    CertificateError,
    DEFAULT_EVENT_ID,
    certificate_links,
    generate_certificate,
    get_certificate_file_path,
    resolve_display_name,
)
from event_checkin.models import db
from event_checkin.models.audit_log import AuditLog
from event_checkin.models.certificate import Certificate


certificate_bp = Blueprint("certificates", __name__)

STATUS_LABELS = {"generated": "Hợp lệ", "revoked": "Đã thu hồi"}
LEGACY_FAIL_LIMIT = 5                 # số lần nhập sai mã CB/SV tối đa ...
LEGACY_FAIL_WINDOW_MINUTES = 15       # ... trong 15 phút, tính riêng theo mã chứng chỉ và theo IP
LEGACY_MISMATCH_MESSAGE = "Thông tin không khớp."
LEGACY_THROTTLED_MESSAGE = f"Bạn đã nhập sai quá nhiều lần. Thử lại sau {LEGACY_FAIL_WINDOW_MINUTES} phút."
RATE_LIMITED_MESSAGE = "Quá nhiều yêu cầu. Vui lòng thử lại sau ít phút."
PRIVATE_HEADERS = {"Cache-Control": "private, no-store", "X-Robots-Tag": "noindex, nofollow"}


# ---- Giới hạn tần suất theo IP (event_checkin/utils/rate_limit.py) -------------------------------------------

public_limiter = PerIpRateLimiter()


@certificate_bp.before_request
def _limit_public_routes():
    if request.endpoint not in PUBLIC_ENDPOINTS:
        return None
    if not public_limiter.allow(client_ip() or "?", current_app.config["CERT_PUBLIC_RATE_LIMIT"]):
        response = current_app.make_response((RATE_LIMITED_MESSAGE, 429))
        response.headers.update(PRIVATE_HEADERS)
        response.headers["Retry-After"] = "60"
        return response
    return None


@certificate_bp.after_request
def _private_headers(response):
    if request.endpoint in PUBLIC_ENDPOINTS or request.endpoint in ADMIN_FILE_ENDPOINTS:
        response.headers.update(PRIVATE_HEADERS)
    return response


# ---- Tiện ích ---------------------------------------------------------------------------------------------------

def _normalize_code(value):
    """So sánh mã CB/SV: không phân biệt hoa/thường, bỏ mọi khoảng trắng."""
    return "".join((value or "").split()).casefold()


def _by_token(token):
    certificate = Certificate.query.filter_by(token=token).first() if token else None
    if not certificate:
        abort(404)
    return certificate


def _send_stored_file(certificate, as_attachment):
    """Trả file đã lưu (KHÔNG tạo lại file -- route công khai không được làm server tốn công vẽ chứng chỉ)."""
    if certificate.status == "revoked":
        abort(404)
    path = get_certificate_file_path(certificate)
    if not path or not path.is_file():
        abort(404)
    return send_file(path, as_attachment=as_attachment, download_name=f"{certificate.certificate_code}{path.suffix.lower()}")


def _verify_context(certificate):
    """CHỈ thông tin tối thiểu: họ tên, tên sự kiện, ngày cấp, trạng thái. Không email, mã CB/SV, đơn vị."""
    return {
        "ho_ten": resolve_display_name(certificate.event_id, certificate.ma_cbsv),
        "ten_su_kien": certificate.event.ten_su_kien if certificate.event else "",
        "ngay_cap": certificate.issued_at.strftime("%d/%m/%Y") if certificate.issued_at else "",
        "valid": certificate.status != "revoked",
        "status_label": STATUS_LABELS.get(certificate.status, certificate.status),
    }


# ---- Link mới theo token ----------------------------------------------------------------------------------------

@certificate_bp.get("/c/<token>")
@access(perm.PUBLIC)
def token_download(token):
    return _send_stored_file(_by_token(token), as_attachment=True)


@certificate_bp.get("/c/<token>/view")
@access(perm.PUBLIC)
def token_view(token):
    return _send_stored_file(_by_token(token), as_attachment=False)


@certificate_bp.get("/verify/t/<token>")
@access(perm.PUBLIC)
def token_verify(token):
    certificate = _by_token(token)
    context = _verify_context(certificate)
    return render_template(
        "certificates/verify.html",
        info=context,
        download_url=url_for("certificates.token_download", token=token) if context["valid"] else None,
        view_url=url_for("certificates.token_view", token=token) if context["valid"] else None,
    )


# ---- Link cũ theo mã tuần tự ------------------------------------------------------------------------------------

@certificate_bp.get("/verify/<certificate_code>")
@access(perm.PUBLIC)
def verify(certificate_code):
    certificate = Certificate.query.filter_by(certificate_code=certificate_code).first_or_404()
    context = _verify_context(certificate)
    return render_template(
        "certificates/verify.html",
        info=context,
        # Không có file ở đây: muốn tải phải qua trang xác nhận mã CB/SV
        confirm_url=url_for("certificates.download", certificate_code=certificate_code) if context["valid"] else None,
    )


def _legacy_failures(certificate_code, ip):
    since = datetime.utcnow() - timedelta(minutes=LEGACY_FAIL_WINDOW_MINUTES)
    query = AuditLog.query.filter(AuditLog.action == "certificate.legacy_failed", AuditLog.created_at >= since)
    by_code = query.filter(AuditLog.target_id == certificate_code[:100]).count()
    by_ip = query.filter(AuditLog.ip == ip).count() if ip else 0
    return max(by_code, by_ip)


def _legacy_page(certificate_code, mode, message=None, status=200):
    response = current_app.make_response((
        render_template("certificates/confirm.html", certificate_code=certificate_code, mode=mode, message=message),
        status,
    ))
    return response


def _legacy_confirm(certificate_code, mode):
    """GET: trang nhập mã CB/SV (hiện giống hệt nhau dù mã chứng chỉ có tồn tại hay không).
    POST: đúng mã CB/SV của người được cấp -> chuyển sang link token; sai -> "Thông tin không khớp"."""
    if request.method == "GET":
        return _legacy_page(certificate_code, mode)

    ip = client_ip()
    if _legacy_failures(certificate_code, ip) >= LEGACY_FAIL_LIMIT:
        log_action("certificate.legacy_throttled", "certificate_code", certificate_code)
        return _legacy_page(certificate_code, mode, LEGACY_THROTTLED_MESSAGE, 429)

    entered = request.form.get("ma_cbsv") or (request.get_json(silent=True) or {}).get("ma_cbsv") or ""
    certificate = Certificate.query.filter_by(certificate_code=certificate_code).first()
    if (
        not certificate
        or certificate.status == "revoked"
        or not _normalize_code(entered)
        or _normalize_code(entered) != _normalize_code(certificate.ma_cbsv)
    ):
        log_action("certificate.legacy_failed", "certificate_code", certificate_code)
        return _legacy_page(certificate_code, mode, LEGACY_MISMATCH_MESSAGE, 400)

    if not certificate.token:
        certificate.ensure_token()
        db.session.commit()
    log_action("certificate.legacy_success", "certificate_code", certificate_code, {"mode": mode})
    endpoint = "certificates.token_view" if mode == "view" else "certificates.token_download"
    return redirect(url_for(endpoint, token=certificate.token), code=303)


@certificate_bp.route("/api/certificates/<certificate_code>", methods=["GET", "POST"])
@access(perm.PUBLIC)
def download(certificate_code):
    return _legacy_confirm(certificate_code, "download")


@certificate_bp.route("/api/certificates/<certificate_code>/view", methods=["GET", "POST"])
@access(perm.PUBLIC)
def view_certificate(certificate_code):
    return _legacy_confirm(certificate_code, "view")


PUBLIC_ENDPOINTS = {
    "certificates.token_download",
    "certificates.token_view",
    "certificates.token_verify",
    "certificates.verify",
    "certificates.download",
    "certificates.view_certificate",
}


# ---- Admin (đăng nhập, quyền certificate.manage) ---------------------------------------------------------------

def _admin_file(certificate_code, as_attachment):
    certificate = Certificate.query.filter_by(certificate_code=certificate_code).first_or_404()
    try:
        # Admin xem/tải thì vẽ lại theo mẫu + tên hiện tại (như trước), rồi trả file vừa vẽ
        certificate, _ = generate_certificate(certificate.ma_cbsv, event_id=certificate.event_id, file_type="pdf")
    except CertificateError as error:
        abort(400, description=str(error))
    path = get_certificate_file_path(certificate)
    if not path or not path.is_file():
        abort(404)
    return send_file(path, as_attachment=as_attachment, download_name=f"{certificate.certificate_code}{path.suffix.lower()}")


@certificate_bp.get("/api/admin/certificates/<certificate_code>")
@access(perm.CERTIFICATE_MANAGE)
def admin_download(certificate_code):
    return _admin_file(certificate_code, as_attachment=True)


@certificate_bp.get("/api/admin/certificates/<certificate_code>/view")
@access(perm.CERTIFICATE_MANAGE)
def admin_view(certificate_code):
    return _admin_file(certificate_code, as_attachment=False)


ADMIN_FILE_ENDPOINTS = {"certificates.admin_download", "certificates.admin_view"}


@certificate_bp.post("/api/certificates/generate")
@access(perm.CERTIFICATE_MANAGE)
@audited("certificate.generate")
def generate():
    payload = request.get_json(silent=True) or request.form
    ma_cbsv = (payload.get("ma_cbsv") or "").strip()
    event_id = payload.get("event_id") or DEFAULT_EVENT_ID
    file_type = (payload.get("file_type") or "pdf").strip().lower()

    if not ma_cbsv:
        return jsonify({"success": False, "message": "Vui lòng nhập mã CB/SV."}), 400

    try:
        certificate, created = generate_certificate(ma_cbsv, event_id=event_id, file_type=file_type)
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "event_id không hợp lệ."}), 400
    except CertificateError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400

    links = certificate_links(certificate)
    return jsonify({
        "success": True,
        "created": created,
        "message": "Đã tạo chứng nhận." if created else "Chứng nhận đã tồn tại.",
        "data": certificate.to_dict(),
        "download_url": links["download_url"],
        "verify_url": links["verify_url"],
        "admin_download_url": url_for("certificates.admin_download", certificate_code=certificate.certificate_code),
    })
