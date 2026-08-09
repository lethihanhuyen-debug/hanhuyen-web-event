import threading
from datetime import datetime

from flask import Blueprint, current_app, jsonify, render_template, request, url_for
from sqlalchemy.exc import IntegrityError
from event_checkin.certificates.service import (
    CertificateError,
    generate_certificate,
    get_certificate_file_path,
)
from event_checkin.models import db
from event_checkin.models.checkin import CheckIn
from event_checkin.models.email_log import EmailLog
from event_checkin.models.registration import Registration
from event_checkin.models.user import User
from event_checkin.utils.email_service import send_checkin_email
from event_checkin.utils.timezone import format_utc_as_vn


checkin_bp = Blueprint("checkin", __name__)


def _format_vn_datetime(dt):
    # thoi_gian_checkin is stored via datetime.utcnow() (see below), so it must be
    # converted to Vietnam local time before display -- formatting it as-is showed
    # the UTC hour (7 hours behind actual Vietnam wall-clock time).
    return format_utc_as_vn(dt, "%H:%M ngay %d/%m/%Y")


def _already_checked_in_response(user, existing_checkin):
    return jsonify({
        "success": False,
        "checked_in": True,
        "message": f"{user.ho_ten} đã check-in lúc {_format_vn_datetime(existing_checkin.thoi_gian_checkin)}.",
        "ho_ten": user.ho_ten,
        "thoi_gian": _format_vn_datetime(existing_checkin.thoi_gian_checkin),
    }), 200


@checkin_bp.get("/checkin")
def index():
    return render_template("checkin/index.html")


def _process_checkin_extras(app, base_url, ma_cbsv, event_id, ho_ten, email, thoi_gian_checkin, ten_su_kien):
    # Runs in a background thread so the check-in request doesn't block on PDF
    # rendering + a live SMTP round-trip to Gmail (the two slow steps). Needs a
    # request context (not just an app context) because generate_certificate()
    # and url_for(..., _external=True) call url_for() internally, which requires
    # one -- test_request_context() gives a valid, cheap one outside a real request.
    with app.test_request_context(base_url=base_url):
        certificate = None
        certificate_path = None
        try:
            certificate, _ = generate_certificate(ma_cbsv, event_id=event_id, file_type="pdf")
            certificate_path = get_certificate_file_path(certificate)
        except CertificateError:
            certificate = None
            certificate_path = None

        verify_url = None
        if certificate:
            verify_url = url_for("certificates.verify", certificate_code=certificate.certificate_code, _external=True)

        email_sent, email_error = send_checkin_email(
            ho_ten,
            email,
            thoi_gian_checkin,
            ten_su_kien=ten_su_kien,
            certificate_path=certificate_path,
            certificate_code=certificate.certificate_code if certificate else None,
            verify_url=verify_url,
            return_error=True,
        )

        db.session.add(EmailLog(
            ma_cbsv=ma_cbsv,
            event_id=event_id,
            email_to=email or "",
            email_type="checkin_certificate",
            subject="Xác nhận tham gia sự kiện",
            certificate_code=certificate.certificate_code if certificate else None,
            attachment_path=str(certificate_path) if certificate_path else None,
            trang_thai="success" if email_sent else "failed",
            error_message=email_error,
            sent_at=datetime.utcnow(),
        ))
        db.session.commit()


@checkin_bp.post("/api/checkin")
def checkin():
    payload = request.get_json(silent=True) or request.form
    ma_cbsv = (payload.get("ma_cbsv") or "").strip()
    event_id = int(payload.get("event_id") or 1)

    if not ma_cbsv:
        return jsonify({"success": False, "message": "Vui lòng nhập mã CB/SV."}), 400

    user = User.query.filter_by(ma_cbsv=ma_cbsv).first()
    if not user:
        return jsonify({"success": False, "message": f"Mã {ma_cbsv} không tồn tại trong hệ thống."}), 404

    registration = Registration.query.filter_by(ma_cbsv=ma_cbsv, event_id=event_id).first()
    if not registration:
        return jsonify({"success": False, "message": f"Mã {ma_cbsv} chưa đăng ký sự kiện này."}), 404

    existing_checkin = CheckIn.query.filter_by(ma_cbsv=ma_cbsv, event_id=event_id).first()

    if existing_checkin:
        return _already_checked_in_response(user, existing_checkin)

    checkin_record = CheckIn(
        ma_cbsv=ma_cbsv,
        event_id=event_id,
        thoi_gian_checkin=datetime.utcnow(),
    )
    db.session.add(checkin_record)
    try:
        db.session.commit()
    except IntegrityError:
        # Two requests for the same ma_cbsv landed at (almost) the same time
        # (e.g. a double-tap on the check-in button). The unique constraint
        # on (ma_cbsv, event_id) rejects the second insert; treat it as an
        # already-checked-in response instead of a 500.
        db.session.rollback()
        existing_checkin = CheckIn.query.filter_by(ma_cbsv=ma_cbsv, event_id=event_id).first()
        return _already_checked_in_response(user, existing_checkin)

    # Certificate rendering + email delivery happen off the request thread (see
    # _process_checkin_extras) -- the client polls /api/checkin/email-status for
    # the real outcome instead of waiting for it here.
    threading.Thread(
        target=_process_checkin_extras,
        args=(
            current_app._get_current_object(),
            request.host_url,
            ma_cbsv,
            event_id,
            user.ho_ten,
            user.email,
            checkin_record.thoi_gian_checkin,
            registration.event.ten_su_kien if registration.event else "",
        ),
        daemon=True,
    ).start()

    return jsonify({
        "success": True,
        "message": f"Cảm ơn {user.ho_ten} đã check-in.",
        "ho_ten": user.ho_ten,
        "thoi_gian": _format_vn_datetime(checkin_record.thoi_gian_checkin),
        "email_pending": True,
        "email": user.email,
    })


@checkin_bp.get("/api/checkin/email-status/<ma_cbsv>/<int:event_id>")
def checkin_email_status(ma_cbsv, event_id):
    log = (
        EmailLog.query
        .filter_by(ma_cbsv=ma_cbsv, event_id=event_id, email_type="checkin_certificate")
        .order_by(EmailLog.sent_at.desc())
        .first()
    )
    if not log:
        return jsonify({"success": True, "status": "pending"})
    return jsonify({
        "success": True,
        "status": log.trang_thai,
        "certificate_code": log.certificate_code,
    })
