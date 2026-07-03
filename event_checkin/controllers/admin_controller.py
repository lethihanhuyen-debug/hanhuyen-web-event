import csv
import json
import re
from functools import wraps
from io import StringIO
from datetime import datetime
from pathlib import Path

from flask import Blueprint, Response, current_app, jsonify, make_response, redirect, render_template, request, session, url_for
from sqlalchemy import func
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename

from event_checkin.models import db
from event_checkin.models.admin import Admin
from event_checkin.models.certificate import Certificate
from event_checkin.models.checkin import CheckIn
from event_checkin.models.don_vi import DonVi
from event_checkin.models.email_log import EmailLog
from event_checkin.models.event import Event
from event_checkin.models.registration import Registration


admin_bp = Blueprint("admin", __name__)
CERTIFICATE_TEMPLATE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
CERTIFICATE_FONT_EXTENSIONS = {".ttf", ".otf"}
EVENT_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        admin_id = session.get("admin_id")
        admin = Admin.query.get(admin_id) if admin_id else None
        if admin and admin.is_active:
            return view(*args, **kwargs)
        if request.path.startswith("/api/"):
            return jsonify({"success": False, "message": "Vui lòng đăng nhập admin."}), 401
        next_url = request.full_path if request.query_string else request.path
        return redirect(url_for("admin.login_page", next=next_url))

    return wrapped


def _admin_payload(admin):
    return {
        "id": admin.id,
        "username": admin.username,
        "role": admin.role,
    }


def _format_vn_datetime(dt):
    return dt.strftime("%H:%M %d/%m/%Y") if dt else ""


def _parse_datetime(value, field_name):
    value = (value or "").strip()
    if not value:
        raise ValueError(f"Vui lòng nhập {field_name}.")
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} không hợp lệ.") from exc


def _event_payload(event):
    certificate_layout = json.loads(event.certificate_layout) if event.certificate_layout else {}
    for config in certificate_layout.values():
        if isinstance(config, dict) and config.get("font_file"):
            config["font_url"] = url_for("static", filename=config["font_file"])
    return {
        "id": event.id,
        "ten_su_kien": event.ten_su_kien,
        "hinh": event.hinh,
        "hinh_url": url_for("static", filename=event.hinh) if event.hinh else None,
        "mo_ta": event.mo_ta,
        "dia_diem": event.dia_diem,
        "ngay_bat_dau": event.ngay_bat_dau.isoformat() if event.ngay_bat_dau else None,
        "ngay_bat_dau_display": _format_vn_datetime(event.ngay_bat_dau),
        "ngay_ket_thuc": event.ngay_ket_thuc.isoformat() if event.ngay_ket_thuc else None,
        "ngay_ket_thuc_display": _format_vn_datetime(event.ngay_ket_thuc),
        "thang": event.thang,
        "nam": event.nam,
        "thoi_gian_mo_dang_ky": event.thoi_gian_mo_dang_ky.isoformat() if event.thoi_gian_mo_dang_ky else None,
        "thoi_gian_mo_dang_ky_display": _format_vn_datetime(event.thoi_gian_mo_dang_ky),
        "thoi_gian_dong_dang_ky": event.thoi_gian_dong_dang_ky.isoformat() if event.thoi_gian_dong_dang_ky else None,
        "thoi_gian_dong_dang_ky_display": _format_vn_datetime(event.thoi_gian_dong_dang_ky),
        "trang_thai": event.trang_thai,
        "certificate_enabled": event.certificate_enabled,
        "certificate_template": event.certificate_template,
        "certificate_template_url": url_for("static", filename=event.certificate_template) if event.certificate_template else None,
        "certificate_layout": certificate_layout,
    }


def _dashboard_payload():
    from datetime import date

    current_day = date.today().isoformat()
    registrations = Registration.query.order_by(Registration.thoi_gian_dang_ky.desc()).all()
    today_checkins = CheckIn.query.filter(func.date(CheckIn.thoi_gian_checkin) == current_day).all()
    today_checkin_map = {(item.ma_cbsv, item.event_id): item for item in today_checkins}
    certificate_map = {
        (item.ma_cbsv, item.event_id): item
        for item in Certificate.query.order_by(Certificate.issued_at.desc()).all()
    }

    rows = []
    for position, registration in enumerate(registrations, start=1):
        user = registration.user
        checkin_item = today_checkin_map.get((registration.ma_cbsv, registration.event_id))
        certificate = certificate_map.get((registration.ma_cbsv, registration.event_id))
        rows.append({
            "stt": position,
            "ma_cbsv": registration.ma_cbsv,
            "event_id": registration.event_id,
            "ho_ten": user.ho_ten if user else "",
            "don_vi": user.ten_don_vi if user else "",
            "email": user.email if user else "",
            "thoi_gian_dang_ky": _format_vn_datetime(registration.thoi_gian_dang_ky),
            "trang_thai": "Đã check-in" if checkin_item else "Chưa check-in",
            "checkin_time": _format_vn_datetime(checkin_item.thoi_gian_checkin) if checkin_item else "",
            "certificate_code": certificate.certificate_code if certificate else "",
            "certificate_url": f"/api/certificates/{certificate.certificate_code}" if certificate else "",
            "verify_url": f"/verify/{certificate.certificate_code}" if certificate else "",
            "can_generate_certificate": bool(checkin_item and not certificate),
        })

    total_registrations = len(registrations)
    total_checkins_today = len(today_checkins)
    total_certificates = Certificate.query.count()
    total_events = Event.query.count()
    pending = max(total_registrations - total_checkins_today, 0)

    return {
        "stats": {
            "total_registrations": total_registrations,
            "total_checkins_today": total_checkins_today,
            "total_certificates": total_certificates,
            "total_events": total_events,
            "pending": pending,
        },
        "rows": rows,
        "events": [_event_payload(event) for event in Event.query.order_by(Event.ngay_bat_dau.desc()).all()],
    }


@admin_bp.get("/admin")
@admin_required
def index():
    events = Event.query.order_by(Event.ngay_bat_dau.desc()).all()
    return render_template(
        "admin/index.html",
        events=[_event_payload(event) for event in events],
    )


@admin_bp.get("/admin/events/<int:event_id>")
@admin_required
def event_detail(event_id):
    event = Event.query.get_or_404(event_id)
    registrations = (
        Registration.query
        .filter_by(event_id=event_id)
        .order_by(Registration.thoi_gian_dang_ky.asc())
        .all()
    )
    checkin_map = {
        item.ma_cbsv: item
        for item in CheckIn.query.filter_by(event_id=event_id).all()
    }
    certificate_map = {
        item.ma_cbsv: item
        for item in Certificate.query.filter_by(event_id=event_id).all()
    }

    rows = []
    for position, registration in enumerate(registrations, start=1):
        user = registration.user
        checkin_item = checkin_map.get(registration.ma_cbsv)
        certificate = certificate_map.get(registration.ma_cbsv)
        rows.append({
            "stt": position,
            "ma_cbsv": registration.ma_cbsv,
            "event_id": registration.event_id,
            "ho_ten": user.ho_ten if user else "",
            "don_vi": user.ten_don_vi if user else "",
            "email": user.email if user else "",
            "thoi_gian_dang_ky": _format_vn_datetime(registration.thoi_gian_dang_ky),
            "checked_in": bool(checkin_item),
            "checkin_time": _format_vn_datetime(checkin_item.thoi_gian_checkin) if checkin_item else "",
            "certificate_code": certificate.certificate_code if certificate else "",
            "certificate_url": f"/api/certificates/{certificate.certificate_code}" if certificate else "",
        })

    return render_template(
        "admin/event_detail.html",
        event=_event_payload(event),
        rows=rows,
        totals={
            "registrations": len(rows),
            "checkins": len(checkin_map),
            "pending": max(len(rows) - len(checkin_map), 0),
        },
    )


@admin_bp.get("/admin/login")
def login_page():
    admin_id = session.get("admin_id")
    admin = Admin.query.get(admin_id) if admin_id else None
    next_url = request.args.get("next") or url_for("admin.index")
    if not next_url.startswith("/") or next_url.startswith("//"):
        next_url = url_for("admin.index")
    if admin and admin.is_active:
        return redirect(next_url)
    return render_template("admin/login.html", next_url=next_url)


@admin_bp.get("/api/admin/me")
def me():
    admin_id = session.get("admin_id")
    admin = Admin.query.get(admin_id) if admin_id else None
    if not admin or not admin.is_active:
        return jsonify({"success": False, "admin": None}), 401
    return jsonify({"success": True, "admin": _admin_payload(admin)})


@admin_bp.post("/api/admin/login")
def login():
    payload = request.get_json(silent=True) or request.form
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    remember = str(payload.get("remember", "")).lower() in {"1", "true", "yes", "on"}

    admin = Admin.query.filter_by(username=username).first()
    if not admin or not admin.is_active or not check_password_hash(admin.password_hash, password):
        return jsonify({"success": False, "message": "Tài khoản hoặc mật khẩu không đúng."}), 401

    session.clear()
    session.permanent = remember
    session["admin_id"] = admin.id
    session["remember_device"] = remember
    return jsonify({"success": True, "admin": _admin_payload(admin), "remember": remember})


@admin_bp.post("/api/admin/logout")
def logout():
    session.clear()
    session.modified = True
    response = make_response(jsonify({"success": True}))
    response.delete_cookie(current_app.config.get("SESSION_COOKIE_NAME", "session"), path="/")
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@admin_bp.get("/api/admin/summary")
@admin_required
def summary():
    payload = _dashboard_payload()
    return jsonify({"success": True, **payload})


@admin_bp.get("/api/admin/events")
@admin_required
def list_events():
    events = Event.query.order_by(Event.ngay_bat_dau.desc()).all()
    return jsonify({"success": True, "data": [_event_payload(event) for event in events]})


@admin_bp.get("/api/admin/don-vi")
@admin_required
def list_don_vi():
    items = DonVi.query.order_by(DonVi.ten_don_vi.asc()).all()
    return jsonify({"success": True, "data": [item.to_dict() for item in items]})


@admin_bp.post("/api/admin/don-vi")
@admin_required
def create_don_vi():
    payload = request.get_json(silent=True) or request.form
    ten_don_vi = (payload.get("ten_don_vi") or "").strip()
    if not ten_don_vi:
        return jsonify({"success": False, "message": "Vui lòng nhập tên đơn vị."}), 400

    existing = DonVi.query.filter_by(ten_don_vi=ten_don_vi).first()
    if existing:
        if not existing.is_active:
            existing.is_active = True
            db.session.commit()
            return jsonify({"success": True, "message": "Đã khôi phục đơn vị.", "data": existing.to_dict()})
        return jsonify({"success": False, "message": "Đơn vị này đã tồn tại."}), 409

    item = DonVi(ten_don_vi=ten_don_vi, is_active=True)
    db.session.add(item)
    db.session.commit()
    return jsonify({"success": True, "message": "Đã thêm đơn vị.", "data": item.to_dict()})


@admin_bp.put("/api/admin/don-vi/<int:item_id>")
@admin_bp.patch("/api/admin/don-vi/<int:item_id>")
@admin_required
def update_don_vi(item_id):
    item = DonVi.query.get_or_404(item_id)
    payload = request.get_json(silent=True) or request.form
    ten_don_vi = (payload.get("ten_don_vi") or "").strip()
    is_active = payload.get("is_active")
    if not ten_don_vi:
        return jsonify({"success": False, "message": "Vui lòng nhập tên đơn vị."}), 400

    duplicate = DonVi.query.filter(DonVi.id != item_id, DonVi.ten_don_vi == ten_don_vi).first()
    if duplicate:
        return jsonify({"success": False, "message": "Đơn vị này đã tồn tại."}), 409

    item.ten_don_vi = ten_don_vi
    if is_active is not None:
        item.is_active = str(is_active).lower() in {"1", "true", "yes", "on"}
    db.session.commit()
    return jsonify({"success": True, "message": "Đã cập nhật đơn vị.", "data": item.to_dict()})


@admin_bp.delete("/api/admin/don-vi/<int:item_id>")
@admin_required
def delete_don_vi(item_id):
    item = DonVi.query.get_or_404(item_id)
    item.is_active = False
    db.session.commit()
    return jsonify({"success": True, "message": "Đã xóa đơn vị khỏi danh sách hiển thị.", "data": item.to_dict()})


@admin_bp.post("/api/admin/events")
@admin_required
def create_event():
    payload = request.get_json(silent=True) or request.form
    ten_su_kien = (payload.get("ten_su_kien") or "").strip()
    if not ten_su_kien:
        return jsonify({"success": False, "message": "Vui lòng nhập tên sự kiện."}), 400

    try:
        ngay_bat_dau = _parse_datetime(payload.get("ngay_bat_dau"), "ngay bat dau")
        ngay_ket_thuc = _parse_datetime(payload.get("ngay_ket_thuc"), "ngay ket thuc")
        thoi_gian_mo_dang_ky = _parse_datetime(payload.get("thoi_gian_mo_dang_ky"), "thời gian mở đăng ký")
        thoi_gian_dong_dang_ky = _parse_datetime(payload.get("thoi_gian_dong_dang_ky"), "thời gian đóng đăng ký")
    except ValueError as error:
        return jsonify({"success": False, "message": str(error)}), 400

    if ngay_ket_thuc < ngay_bat_dau:
        return jsonify({"success": False, "message": "Ngày kết thúc phải sau ngày bắt đầu."}), 400
    if thoi_gian_dong_dang_ky < thoi_gian_mo_dang_ky:
        return jsonify({"success": False, "message": "Thời gian đóng đăng ký phải sau thời gian mở đăng ký."}), 400

    event = Event(
        ten_su_kien=ten_su_kien,
        hinh=(payload.get("hinh") or "").strip() or None,
        mo_ta=(payload.get("mo_ta") or "").strip() or None,
        dia_diem=(payload.get("dia_diem") or "").strip() or None,
        ngay_bat_dau=ngay_bat_dau,
        ngay_ket_thuc=ngay_ket_thuc,
        thang=ngay_bat_dau.month,
        nam=ngay_bat_dau.year,
        thoi_gian_mo_dang_ky=thoi_gian_mo_dang_ky,
        thoi_gian_dong_dang_ky=thoi_gian_dong_dang_ky,
        trang_thai=(payload.get("trang_thai") or "upcoming").strip(),
        certificate_enabled=True,
        created_by=session["admin_id"],
        created_at=datetime.utcnow(),
    )
    db.session.add(event)
    db.session.commit()
    return jsonify({"success": True, "message": "Đã tạo sự kiện mới.", "data": _event_payload(event)})


@admin_bp.put("/api/admin/events/<int:event_id>")
@admin_bp.patch("/api/admin/events/<int:event_id>")
@admin_required
def update_event(event_id):
    event = Event.query.get_or_404(event_id)
    payload = request.get_json(silent=True) or request.form
    ten_su_kien = (payload.get("ten_su_kien") or "").strip()
    if not ten_su_kien:
        return jsonify({"success": False, "message": "Vui lòng nhập tên sự kiện."}), 400

    try:
        ngay_bat_dau = _parse_datetime(payload.get("ngay_bat_dau"), "ngay bat dau")
        ngay_ket_thuc = _parse_datetime(payload.get("ngay_ket_thuc"), "ngay ket thuc")
        thoi_gian_mo_dang_ky = _parse_datetime(payload.get("thoi_gian_mo_dang_ky"), "thời gian mở đăng ký")
        thoi_gian_dong_dang_ky = _parse_datetime(payload.get("thoi_gian_dong_dang_ky"), "thời gian đóng đăng ký")
    except ValueError as error:
        return jsonify({"success": False, "message": str(error)}), 400

    if ngay_ket_thuc < ngay_bat_dau:
        return jsonify({"success": False, "message": "Ngày kết thúc phải sau ngày bắt đầu."}), 400
    if thoi_gian_dong_dang_ky < thoi_gian_mo_dang_ky:
        return jsonify({"success": False, "message": "Thời gian đóng đăng ký phải sau thời gian mở đăng ký."}), 400

    event.ten_su_kien = ten_su_kien
    if "hinh" in payload:
        event.hinh = (payload.get("hinh") or "").strip() or None
    event.mo_ta = (payload.get("mo_ta") or "").strip() or None
    event.dia_diem = (payload.get("dia_diem") or "").strip() or None
    event.ngay_bat_dau = ngay_bat_dau
    event.ngay_ket_thuc = ngay_ket_thuc
    event.thang = ngay_bat_dau.month
    event.nam = ngay_bat_dau.year
    event.thoi_gian_mo_dang_ky = thoi_gian_mo_dang_ky
    event.thoi_gian_dong_dang_ky = thoi_gian_dong_dang_ky
    event.trang_thai = (payload.get("trang_thai") or "upcoming").strip()
    event.updated_by = session["admin_id"]
    event.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"success": True, "message": "Đã cập nhật sự kiện.", "data": _event_payload(event)})


@admin_bp.post("/api/admin/events/<int:event_id>/image")
@admin_required
def upload_event_image(event_id):
    event = Event.query.get_or_404(event_id)
    file = request.files.get("event_image")
    if not file or not file.filename:
        return jsonify({"success": False, "message": "Vui lòng chọn hình sự kiện."}), 400

    extension = Path(secure_filename(file.filename)).suffix.lower()
    if extension not in EVENT_IMAGE_EXTENSIONS:
        return jsonify({"success": False, "message": "Chỉ hỗ trợ PNG, JPG, JPEG hoặc WEBP."}), 400

    image_dir = Path(current_app.static_folder) / "events"
    image_dir.mkdir(parents=True, exist_ok=True)
    filename = f"event_{event_id}_image{extension}"
    file_path = image_dir / filename
    file.save(file_path)

    event.hinh = f"events/{filename}"
    event.updated_by = session["admin_id"]
    event.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        "success": True,
        "message": "Đã cập nhật hình sự kiện.",
        "data": _event_payload(event),
    })


@admin_bp.post("/api/admin/events/<int:event_id>/certificate-template")
@admin_required
def upload_certificate_template(event_id):
    event = Event.query.get_or_404(event_id)
    file = request.files.get("certificate_template")
    if not file or not file.filename:
        return jsonify({"success": False, "message": "Vui lòng chọn file mẫu giấy chứng nhận."}), 400

    extension = Path(secure_filename(file.filename)).suffix.lower()
    if extension not in CERTIFICATE_TEMPLATE_EXTENSIONS:
        return jsonify({"success": False, "message": "Chỉ hỗ trợ PNG, JPG, JPEG hoặc WEBP."}), 400

    template_dir = Path(current_app.static_folder) / "certificates" / "templates"
    template_dir.mkdir(parents=True, exist_ok=True)
    filename = f"event_{event_id}_certificate{extension}"
    file_path = template_dir / filename
    file.save(file_path)

    event.certificate_template = f"certificates/templates/{filename}"
    event.certificate_enabled = True
    event.updated_by = session["admin_id"]
    event.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        "success": True,
        "message": "Đã cập nhật mẫu giấy chứng nhận cho sự kiện.",
        "data": _event_payload(event),
    })


@admin_bp.get("/api/admin/events/<int:event_id>/certificate-layout")
@admin_required
def get_certificate_layout(event_id):
    event = Event.query.get_or_404(event_id)
    return jsonify({"success": True, "data": _event_payload(event)})


def _validate_hex_color(value):
    if not isinstance(value, str):
        return False
    return re.fullmatch(r"#[0-9a-fA-F]{6}", value.strip()) is not None


def _normalize_align(value):
    if not isinstance(value, str):
        return "left"
    value = value.strip().lower()
    return value if value in {"left", "center", "right"} else "left"


def _validate_layout_field(field, config):
    if not isinstance(config, dict):
        return False, f"Trường {field} phải là object." 
    errors = []
    try:
        x = int(config.get("x", config.get("X", 0)))
    except (TypeError, ValueError):
        errors.append("x phải là số nguyên.")
    try:
        y = int(config.get("y", config.get("Y", 0)))
    except (TypeError, ValueError):
        errors.append("y phải là số nguyên.")
    try:
        size = int(config.get("size", 0))
        if size < 10 or size > 200:
            errors.append("size phải trong khoảng 10-200.")
    except (TypeError, ValueError):
        errors.append("size phải là số nguyên.")
    if not _validate_hex_color(config.get("color", "")):
        errors.append("color phải là mã màu hex, ví dụ #ff0000.")
    if not isinstance(config.get("bold", False), bool):
        errors.append("bold phải là true hoặc false.")
    if _normalize_align(config.get("align")) not in {"left", "center", "right"}:
        errors.append("align phải là left, center, hoặc right.")
    if errors:
        return False, f"{field}: {' '.join(errors)}"
    return True, None


@admin_bp.post("/api/admin/events/<int:event_id>/certificate-layout")
@admin_required
def save_certificate_layout(event_id):
    event = Event.query.get_or_404(event_id)
    payload = request.get_json(silent=True) or {}
    layout_payload = payload.get("layout")
    if not isinstance(layout_payload, dict):
        return jsonify({"success": False, "message": "Payload layout phải là object."}), 400

    allowed_fields = {"student_name", "ma_cbsv", "don_vi", "issue_date", "certificate_code"}
    layout = json.loads(event.certificate_layout) if event.certificate_layout else {}
    if not isinstance(layout, dict):
        layout = {}

    errors = []
    meta = layout_payload.get("_meta")
    if meta is None:
        meta = {
            "width": payload.get("base_width"),
            "height": payload.get("base_height"),
        }
    if meta is not None:
        if not isinstance(meta, dict):
            return jsonify({"success": False, "message": "_meta phải là object."}), 400
        try:
            width = int(meta.get("width"))
            height = int(meta.get("height"))
            if width <= 0 or height <= 0:
                raise ValueError()
            layout["_meta"] = {"width": width, "height": height}
        except (TypeError, ValueError):
            return jsonify({"success": False, "message": "_meta.width và _meta.height phải là số nguyên dương."}), 400

    for field in allowed_fields:
        if field not in layout_payload:
            continue
        valid, error_message = _validate_layout_field(field, layout_payload[field])
        if not valid:
            errors.append(error_message)
            continue
        config = layout_payload[field]
        field_layout = {
            "x": int(config.get("x")),
            "y": int(config.get("y")),
            "align": _normalize_align(config.get("align")),
            "size": int(config.get("size")),
            "color": config.get("color").strip(),
            "bold": bool(config.get("bold")),
        }
        if "font_file" in config and config["font_file"] is not None:
            field_layout["font_file"] = str(config.get("font_file"))
        if "font_name" in config and config["font_name"] is not None:
            field_layout["font_name"] = str(config.get("font_name"))
        # merge field partial updates without removing missing optional font props
        existing_config = layout.get(field, {}) if isinstance(layout.get(field), dict) else {}
        existing_config.update(field_layout)
        if "font_file" in config and config.get("font_file") is None:
            existing_config.pop("font_file", None)
        if "font_name" in config and config.get("font_name") is None:
            existing_config.pop("font_name", None)
        layout[field] = existing_config

    if errors:
        return jsonify({"success": False, "message": "Lỗi dữ liệu layout.", "errors": errors}), 400

    event.certificate_layout = json.dumps(layout, ensure_ascii=False)
    event.updated_by = session["admin_id"]
    event.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"success": True, "message": "Đã lưu layout chứng chỉ.", "data": _event_payload(event)})


@admin_bp.post("/api/admin/events/<int:event_id>/certificate-font")
@admin_required
def upload_certificate_font(event_id):
    event = Event.query.get_or_404(event_id)
    field = (request.form.get("field") or "").strip()
    allowed_fields = {"student_name", "ma_cbsv", "don_vi", "issue_date", "certificate_code"}
    if field not in allowed_fields:
        return jsonify({"success": False, "message": "Trường font không hợp lệ."}), 400

    file = request.files.get("certificate_font")
    if not file or not file.filename:
        return jsonify({"success": False, "message": "Vui lòng chọn file font."}), 400

    original_name = secure_filename(file.filename)
    extension = Path(original_name).suffix.lower()
    if extension not in CERTIFICATE_FONT_EXTENSIONS:
        return jsonify({"success": False, "message": "Chỉ hỗ trợ font .ttf hoặc .otf."}), 400

    font_dir = Path(current_app.static_folder) / "certificates" / "fonts"
    font_dir.mkdir(parents=True, exist_ok=True)
    filename = f"event_{event_id}_{field}_font{extension}"
    file_path = font_dir / filename
    file.save(file_path)

    layout = json.loads(event.certificate_layout) if event.certificate_layout else {}
    if not isinstance(layout, dict):
        layout = {}
    field_config = layout.get(field) if isinstance(layout.get(field), dict) else {}
    font_family = f"event_{event_id}_{field}_font"
    field_config["font_file"] = f"certificates/fonts/{filename}"
    field_config["font_name"] = original_name
    field_config["font_family"] = font_family
    layout[field] = field_config

    event.certificate_layout = json.dumps(layout, ensure_ascii=False)
    event.updated_by = session["admin_id"]
    event.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"success": True, "message": "Đã cập nhật font cho trường.", "data": _event_payload(event)})


@admin_bp.delete("/api/admin/events/<int:event_id>/certificate-font/<field>")
@admin_required
def delete_certificate_font(event_id, field):
    event = Event.query.get_or_404(event_id)
    allowed_fields = {"student_name", "ma_cbsv", "don_vi", "issue_date", "certificate_code"}
    if field not in allowed_fields:
        return jsonify({"success": False, "message": "Trường font không hợp lệ."}), 400

    layout = json.loads(event.certificate_layout) if event.certificate_layout else {}
    if not isinstance(layout, dict):
        layout = {}
    field_config = layout.get(field) if isinstance(layout.get(field), dict) else {}
    font_file = field_config.get("font_file")
    if font_file:
        file_path = Path(current_app.static_folder) / font_file
        if file_path.exists():
            file_path.unlink()
    field_config.pop("font_file", None)
    field_config.pop("font_name", None)
    layout[field] = field_config

    event.certificate_layout = json.dumps(layout, ensure_ascii=False)
    event.updated_by = session["admin_id"]
    event.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"success": True, "message": "Đã xóa font của trường.", "data": _event_payload(event)})


@admin_bp.delete("/api/admin/events/<int:event_id>")
@admin_required
def delete_event(event_id):
    event = Event.query.get_or_404(event_id)
    has_data = (
        Registration.query.filter_by(event_id=event_id).first()
        or CheckIn.query.filter_by(event_id=event_id).first()
        or Certificate.query.filter_by(event_id=event_id).first()
        or EmailLog.query.filter_by(event_id=event_id).first()
    )
    if has_data:
        return jsonify({
            "success": False,
            "message": "Không thể xóa sự kiện đã có đăng ký, check-in, chứng chỉ hoặc email log.",
        }), 409

    db.session.delete(event)
    db.session.commit()
    return jsonify({"success": True, "message": "Đã xóa sự kiện."})


@admin_bp.delete("/api/admin/events/<int:event_id>/checkins/<ma_cbsv>")
@admin_required
def delete_event_checkin(event_id, ma_cbsv):
    Event.query.get_or_404(event_id)
    checkin = CheckIn.query.filter_by(event_id=event_id, ma_cbsv=ma_cbsv).first()
    if not checkin:
        return jsonify({"success": False, "message": "Người dùng này chưa check-in sự kiện."}), 404

    certificate = Certificate.query.filter_by(event_id=event_id, ma_cbsv=ma_cbsv).first()
    certificate_path = None
    if certificate and certificate.file_url:
        static_prefix = url_for("static", filename="", _external=False)
        relative_path = certificate.file_url
        if relative_path.startswith(static_prefix):
            relative_path = relative_path[len(static_prefix):]
        certificate_path = Path(current_app.static_folder) / relative_path

        EmailLog.query.filter_by(
            event_id=event_id,
            ma_cbsv=ma_cbsv,
            certificate_code=certificate.certificate_code,
        ).update({
            "certificate_code": None,
            "attachment_path": None,
        })
        db.session.delete(certificate)

    db.session.delete(checkin)
    db.session.commit()

    if certificate_path and certificate_path.exists():
        certificate_path.unlink(missing_ok=True)

    return jsonify({"success": True, "message": f"Đã xóa check-in của mã {ma_cbsv}."})


@admin_bp.get("/admin/export/csv")
@admin_required
def export_csv():
    from datetime import date

    current_day = date.today().isoformat()
    registrations = Registration.query.order_by(Registration.thoi_gian_dang_ky.asc()).all()
    today_checkins = CheckIn.query.filter(func.date(CheckIn.thoi_gian_checkin) == current_day).all()
    today_checkin_map = {(item.ma_cbsv, item.event_id): item for item in today_checkins}

    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["STT", "Mã CB/SV", "Họ tên", "Đơn vị", "Email", "Giờ đăng ký", "Trạng thái check-in"])

    for position, registration in enumerate(registrations, start=1):
        user = registration.user
        checkin_item = today_checkin_map.get((registration.ma_cbsv, registration.event_id))
        writer.writerow([
            position,
            registration.ma_cbsv,
            user.ho_ten if user else "",
            user.ten_don_vi if user else "",
            user.email if user else "",
            _format_vn_datetime(registration.thoi_gian_dang_ky),
            "Đã check-in" if checkin_item else "Chưa check-in",
        ])

    response = Response(buffer.getvalue(), mimetype="text/csv; charset=utf-8")
    response.headers["Content-Disposition"] = "attachment; filename=checkin_report.csv"
    return response


@admin_bp.post("/admin/reset")
@admin_required
def reset_data():
    payload = request.get_json(silent=True) or request.form
    confirmed = str(payload.get("confirm", "")).lower() in {"1", "true", "yes", "on"}
    if not confirmed:
        return jsonify({"success": False, "message": "Chưa xác nhận xóa dữ liệu."}), 400

    db.session.query(EmailLog).delete()
    db.session.query(Certificate).delete()
    db.session.query(CheckIn).delete()
    db.session.query(Registration).delete()
    db.session.commit()
    return jsonify({"success": True, "message": "Đã xóa toàn bộ dữ liệu đăng ký, check-in và chứng nhận."})
