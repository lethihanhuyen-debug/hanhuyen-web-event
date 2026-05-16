from datetime import date

from flask import Blueprint, jsonify, render_template, request
from sqlalchemy import func

from event_checkin.models import db
from event_checkin.models.checkin import CheckIn
from event_checkin.models.registration import Registration
from event_checkin.utils.email_service import send_checkin_email


checkin_bp = Blueprint("checkin", __name__)


def _format_vn_datetime(dt):
    return dt.strftime("%H:%M ngày %d/%m/%Y")


@checkin_bp.get("/checkin")
def index():
    return render_template("checkin/index.html")


@checkin_bp.post("/api/checkin")
def checkin():
    payload = request.get_json(silent=True) or request.form
    ma_cbsv = (payload.get("ma_cbsv") or "").strip()

    if not ma_cbsv:
        return jsonify({"success": False, "message": "Vui lòng nhập mã CB/SV."}), 400

    registration = Registration.query.filter_by(ma_cbsv=ma_cbsv).first()
    if not registration:
        return jsonify({"success": False, "message": f"Mã {ma_cbsv} chưa đăng ký tham gia chương trình."}), 404

    today_str = date.today().isoformat()
    today_checkin = CheckIn.query.filter(
        CheckIn.registration_id == registration.id,
        func.date(CheckIn.thoi_gian) == today_str,
    ).first()

    if today_checkin:
        return jsonify({
            "success": False,
            "checked_in": True,
            "message": f"{registration.ho_ten} đã check-in lúc {_format_vn_datetime(today_checkin.thoi_gian)}.",
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

    email_sent = send_checkin_email(registration.ho_ten, registration.email, checkin_record.thoi_gian)

    return jsonify({
        "success": True,
        "message": f"Cảm ơn {registration.ho_ten} đã check-in.",
        "ho_ten": registration.ho_ten,
        "thoi_gian": _format_vn_datetime(checkin_record.thoi_gian),
        "email_sent": email_sent,
    })
