from datetime import date

from flask import Blueprint, jsonify, render_template, request, url_for
from sqlalchemy import func

from event_checkin.certificates.service import (
    CertificateError,
    generate_certificate,
    get_certificate_file_path,
)
from event_checkin.models import db
from event_checkin.models.checkin import CheckIn
from event_checkin.models.registration import Registration
from event_checkin.utils.email_service import send_checkin_email


checkin_bp = Blueprint("checkin", __name__)


def _format_vn_datetime(dt):
    return dt.strftime("%H:%M ngay %d/%m/%Y")


@checkin_bp.get("/checkin")
def index():
    return render_template("checkin/index.html")


@checkin_bp.post("/api/checkin")
def checkin():
    payload = request.get_json(silent=True) or request.form
    ma_cbsv = (payload.get("ma_cbsv") or "").strip()

    if not ma_cbsv:
        return jsonify({"success": False, "message": "Vui long nhap ma CB/SV."}), 400

    registration = Registration.query.filter_by(ma_cbsv=ma_cbsv).first()
    if not registration:
        return jsonify({"success": False, "message": f"Ma {ma_cbsv} chua dang ky tham gia chuong trinh."}), 404

    today_str = date.today().isoformat()
    today_checkin = CheckIn.query.filter(
        CheckIn.registration_id == registration.id,
        func.date(CheckIn.thoi_gian) == today_str,
    ).first()

    if today_checkin:
        return jsonify({
            "success": False,
            "checked_in": True,
            "message": f"{registration.ho_ten} da check-in luc {_format_vn_datetime(today_checkin.thoi_gian)}.",
            "ho_ten": registration.ho_ten,
            "thoi_gian": _format_vn_datetime(today_checkin.thoi_gian),
        }), 200

    checkin_record = CheckIn(
        registration_id=registration.id,
        ma_cbsv=registration.ma_cbsv,
        ho_ten=registration.ho_ten,
        email=registration.email,
    )
    db.session.add(checkin_record)
    db.session.commit()

    certificate = None
    certificate_path = None
    certificate_message = ""
    try:
        certificate, _ = generate_certificate(registration.ma_cbsv, event_id=1, file_type="png")
        certificate_path = get_certificate_file_path(certificate)
    except CertificateError as error:
        certificate_message = f" Khong the tao chung nhan: {error}"

    verify_url = None
    if certificate:
        verify_url = url_for("certificates.verify", certificate_code=certificate.certificate_code, _external=True)

    email_sent = send_checkin_email(
        registration.ho_ten,
        registration.email,
        checkin_record.thoi_gian,
        certificate_path=certificate_path,
        certificate_code=certificate.certificate_code if certificate else None,
        verify_url=verify_url,
    )

    message = f"Cam on {registration.ho_ten} da check-in."
    if certificate:
        message += f" Chung nhan: {certificate.certificate_code}."
    if certificate_message:
        message += certificate_message
    if not email_sent:
        message += " Check-in da luu nhung gui email that bai, vui long kiem tra email dang ky hoac cau hinh SMTP."

    return jsonify({
        "success": True,
        "message": message,
        "ho_ten": registration.ho_ten,
        "thoi_gian": _format_vn_datetime(checkin_record.thoi_gian),
        "email_sent": email_sent,
        "email": registration.email,
        "certificate_code": certificate.certificate_code if certificate else None,
        "certificate_url": f"/api/certificates/{certificate.certificate_code}" if certificate else None,
    })
