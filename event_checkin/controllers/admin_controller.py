import csv
from io import StringIO

from flask import Blueprint, Response, jsonify, render_template, request
from sqlalchemy import func

from event_checkin.models import db
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

    rows = []
    for position, registration in enumerate(registrations, start=1):
        checkin_item = today_checkin_map.get(registration.id)
        rows.append({
            "stt": position,
            "ma_cbsv": registration.ma_cbsv,
            "ho_ten": registration.ho_ten,
            "don_vi": registration.don_vi or "",
            "email": registration.email or "",
            "thoi_gian_dang_ky": _format_vn_datetime(registration.thoi_gian_dang_ky),
            "trang_thai": "Đã check-in" if checkin_item else "Chưa check-in",
            "checkin_time": _format_vn_datetime(checkin_item.thoi_gian) if checkin_item else "",
        })

    total_registrations = len(registrations)
    total_checkins_today = len(today_checkins)
    pending = max(total_registrations - total_checkins_today, 0)

    return render_template(
        "admin/index.html",
        stats={
            "total_registrations": total_registrations,
            "total_checkins_today": total_checkins_today,
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
    writer.writerow(["STT", "Mã CB/SV", "Họ tên", "Đơn vị", "Email", "Giờ đăng ký", "Trạng thái check-in"])

    for position, registration in enumerate(registrations, start=1):
        checkin_item = today_checkin_map.get(registration.id)
        writer.writerow([
            position,
            registration.ma_cbsv,
            registration.ho_ten,
            registration.don_vi or "",
            registration.email or "",
            _format_vn_datetime(registration.thoi_gian_dang_ky),
            "Đã check-in" if checkin_item else "Chưa check-in",
        ])

    response = Response(buffer.getvalue(), mimetype="text/csv; charset=utf-8")
    response.headers["Content-Disposition"] = "attachment; filename=checkin_report.csv"
    return response


@admin_bp.post("/admin/reset")
def reset_data():
    payload = request.get_json(silent=True) or request.form
    confirmed = str(payload.get("confirm", "")).lower() in {"1", "true", "yes", "on"}
    if not confirmed:
        return jsonify({"success": False, "message": "Chưa xác nhận xóa dữ liệu."}), 400

    db.session.query(CheckIn).delete()
    db.session.query(Registration).delete()
    db.session.commit()
    return jsonify({"success": True, "message": "Đã xóa toàn bộ dữ liệu đăng ký và check-in."})
