import csv
from io import StringIO

from flask import Blueprint, Response, jsonify, render_template, request
from sqlalchemy import func

from event_checkin.models import db
from event_checkin.models.certificate import Certificate
from event_checkin.models.checkin import CheckIn
from event_checkin.models.registration import Registration


admin_bp = Blueprint("admin", __name__)


def _format_vn_datetime(dt):
    return dt.strftime("%H:%M %d/%m/%Y") if dt else ""


@admin_bp.get("/admin")
def index():
    from datetime import date

    current_day = date.today().isoformat()
    registrations = Registration.query.order_by(Registration.thoi_gian_dang_ky.desc()).all()
    today_checkins = CheckIn.query.filter(func.date(CheckIn.thoi_gian) == current_day).all()
    today_checkin_map = {item.registration_id: item for item in today_checkins}
    certificate_map = {
        item.ma_cbsv: item
        for item in Certificate.query.order_by(Certificate.issued_at.desc()).all()
    }

    rows = []
    for position, registration in enumerate(registrations, start=1):
        checkin_item = today_checkin_map.get(registration.id)
        certificate = certificate_map.get(registration.ma_cbsv)
        rows.append({
            "stt": position,
            "ma_cbsv": registration.ma_cbsv,
            "ho_ten": registration.ho_ten,
            "don_vi": registration.don_vi or "",
            "email": registration.email or "",
            "thoi_gian_dang_ky": _format_vn_datetime(registration.thoi_gian_dang_ky),
            "trang_thai": "Da check-in" if checkin_item else "Chua check-in",
            "checkin_time": _format_vn_datetime(checkin_item.thoi_gian) if checkin_item else "",
            "certificate_code": certificate.certificate_code if certificate else "",
            "certificate_url": f"/api/certificates/{certificate.certificate_code}" if certificate else "",
            "can_generate_certificate": bool(checkin_item and not certificate),
        })

    total_registrations = len(registrations)
    total_checkins_today = len(today_checkins)
    total_certificates = Certificate.query.count()
    pending = max(total_registrations - total_checkins_today, 0)

    return render_template(
        "admin/index.html",
        stats={
            "total_registrations": total_registrations,
            "total_checkins_today": total_checkins_today,
            "total_certificates": total_certificates,
            "pending": pending,
        },
        rows=rows,
    )


@admin_bp.get("/admin/export/csv")
def export_csv():
    from datetime import date

    current_day = date.today().isoformat()
    registrations = Registration.query.order_by(Registration.thoi_gian_dang_ky.asc()).all()
    today_checkins = CheckIn.query.filter(func.date(CheckIn.thoi_gian) == current_day).all()
    today_checkin_map = {item.registration_id: item for item in today_checkins}

    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["STT", "Ma CB/SV", "Ho ten", "Don vi", "Email", "Gio dang ky", "Trang thai check-in"])

    for position, registration in enumerate(registrations, start=1):
        checkin_item = today_checkin_map.get(registration.id)
        writer.writerow([
            position,
            registration.ma_cbsv,
            registration.ho_ten,
            registration.don_vi or "",
            registration.email or "",
            _format_vn_datetime(registration.thoi_gian_dang_ky),
            "Da check-in" if checkin_item else "Chua check-in",
        ])

    response = Response(buffer.getvalue(), mimetype="text/csv; charset=utf-8")
    response.headers["Content-Disposition"] = "attachment; filename=checkin_report.csv"
    return response


@admin_bp.post("/admin/reset")
def reset_data():
    payload = request.get_json(silent=True) or request.form
    confirmed = str(payload.get("confirm", "")).lower() in {"1", "true", "yes", "on"}
    if not confirmed:
        return jsonify({"success": False, "message": "Chua xac nhan xoa du lieu."}), 400

    db.session.query(CheckIn).delete()
    db.session.query(Certificate).delete()
    db.session.query(Registration).delete()
    db.session.commit()
    return jsonify({"success": True, "message": "Da xoa toan bo du lieu dang ky, check-in va chung nhan."})
