from flask import Blueprint, abort, jsonify, render_template, request, send_file

from event_checkin.certificates.service import (
    CertificateError,
    DEFAULT_EVENT_ID,
    generate_certificate,
    get_certificate_file_path,
)
from event_checkin.controllers.admin_controller import admin_required
from event_checkin.models.certificate import Certificate


certificate_bp = Blueprint("certificates", __name__)


@certificate_bp.post("/api/certificates/generate")
@admin_required
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

    return jsonify({
        "success": True,
        "created": created,
        "message": "Đã tạo chứng nhận." if created else "Chứng nhận đã tồn tại.",
        "data": certificate.to_dict(),
        "download_url": f"/api/certificates/{certificate.certificate_code}",
        "verify_url": f"/verify/{certificate.certificate_code}",
    })


@certificate_bp.get("/api/certificates/<certificate_code>")
def download(certificate_code):
    certificate = Certificate.query.filter_by(certificate_code=certificate_code).first_or_404()
    try:
        certificate, _ = generate_certificate(certificate.ma_cbsv, event_id=certificate.event_id, file_type="pdf")
    except CertificateError as error:
        abort(400, description=str(error))
    file_path = get_certificate_file_path(certificate)
    if not file_path or not file_path.exists():
        abort(404)
    return send_file(file_path, as_attachment=True, download_name=file_path.name)


@certificate_bp.get("/api/certificates/<certificate_code>/view")
def view_certificate(certificate_code):
    certificate = Certificate.query.filter_by(certificate_code=certificate_code).first_or_404()
    try:
        certificate, _ = generate_certificate(certificate.ma_cbsv, event_id=certificate.event_id, file_type="pdf")
    except CertificateError as error:
        abort(400, description=str(error))
    file_path = get_certificate_file_path(certificate)
    if not file_path or not file_path.exists():
        abort(404)
    return send_file(file_path, as_attachment=False)


@certificate_bp.get("/api/users/<ma_cbsv>/certificates")
def list_by_user(ma_cbsv):
    certificates = Certificate.query.filter_by(ma_cbsv=ma_cbsv).order_by(Certificate.issued_at.desc()).all()
    return jsonify({"success": True, "data": [item.to_dict() for item in certificates]})


@certificate_bp.get("/verify/<certificate_code>")
def verify(certificate_code):
    certificate = Certificate.query.filter_by(certificate_code=certificate_code).first_or_404()
    return render_template("certificates/verify.html", certificate=certificate)
