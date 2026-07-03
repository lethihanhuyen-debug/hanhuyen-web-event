import re
from datetime import datetime

from flask import Blueprint, jsonify, render_template, request, url_for

from event_checkin.models import db
from event_checkin.models.don_vi import DonVi
from event_checkin.models.event import Event
from event_checkin.models.registration import Registration
from event_checkin.models.user import User


register_bp = Blueprint("register", __name__)
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _get_or_create_don_vi(ten_don_vi):
    ten_don_vi = (ten_don_vi or "").strip()
    if not ten_don_vi:
        return None
    don_vi = DonVi.query.filter_by(ten_don_vi=ten_don_vi).first()
    if not don_vi:
        don_vi = DonVi(ten_don_vi=ten_don_vi, is_active=True)
        db.session.add(don_vi)
        db.session.flush()
    return don_vi


@register_bp.get("/")
def index():
    events = Event.query.order_by(Event.ngay_bat_dau.desc()).all()
    don_vi_items = DonVi.query.filter_by(is_active=True).order_by(DonVi.ten_don_vi.asc()).all()
    return render_template("register/index.html", events=events, selected_event=None, don_vi_items=don_vi_items)


@register_bp.get("/events/<int:event_id>/register")
def event_register(event_id):
    event = Event.query.get_or_404(event_id)
    events = Event.query.order_by(Event.ngay_bat_dau.desc()).all()
    don_vi_items = DonVi.query.filter_by(is_active=True).order_by(DonVi.ten_don_vi.asc()).all()
    return render_template("register/index.html", events=events, selected_event=event, don_vi_items=don_vi_items)


@register_bp.get("/api/lookup/<ma_cbsv>")
def lookup(ma_cbsv):
    ma_cbsv = (ma_cbsv or "").strip()
    user = User.query.filter_by(ma_cbsv=ma_cbsv).first()
    if not user:
        return jsonify({"success": False, "message": f"Không tìm thấy mã {ma_cbsv}."}), 404
    return jsonify({"success": True, "data": user.to_dict()})


@register_bp.get("/api/events")
def public_events():
    events = Event.query.order_by(Event.ngay_bat_dau.desc()).all()
    return jsonify({
        "success": True,
        "data": [
            {
                "id": event.id,
                "ten_su_kien": event.ten_su_kien,
                "hinh": event.hinh,
                "hinh_url": url_for("static", filename=event.hinh) if event.hinh else None,
                "dia_diem": event.dia_diem,
                "trang_thai": event.trang_thai,
                "ngay_bat_dau": event.ngay_bat_dau.isoformat() if event.ngay_bat_dau else None,
                "ngay_ket_thuc": event.ngay_ket_thuc.isoformat() if event.ngay_ket_thuc else None,
                "thoi_gian_mo_dang_ky": event.thoi_gian_mo_dang_ky.isoformat() if event.thoi_gian_mo_dang_ky else None,
                "thoi_gian_dong_dang_ky": event.thoi_gian_dong_dang_ky.isoformat() if event.thoi_gian_dong_dang_ky else None,
            }
            for event in events
        ],
    })


@register_bp.get("/api/don-vi")
def public_don_vi():
    items = DonVi.query.filter_by(is_active=True).order_by(DonVi.ten_don_vi.asc()).all()
    return jsonify({"success": True, "data": [item.to_dict() for item in items]})


@register_bp.post("/register")
@register_bp.post("/api/register")
def register():
    payload = request.get_json(silent=True) or request.form
    ma_cbsv = (payload.get("ma_cbsv") or "").strip()
    ho_ten = (payload.get("ho_ten") or "").strip()
    don_vi_id = payload.get("don_vi_id")
    don_vi_text = (payload.get("don_vi") or "").strip()
    email = (payload.get("email") or "").strip().lower()
    event_id = int(payload.get("event_id") or 1)

    if not ma_cbsv or not ho_ten or not email:
        return jsonify({"success": False, "message": "Vui lòng nhập đầy đủ mã, họ tên và email."}), 400

    if not EMAIL_PATTERN.match(email):
        return jsonify({"success": False, "message": "Email không hợp lệ."}), 400

    event = Event.query.get(event_id)
    if not event:
        return jsonify({"success": False, "message": "Sự kiện không tồn tại."}), 404

    don_vi = None
    if don_vi_id:
        try:
            don_vi = DonVi.query.filter_by(id=int(don_vi_id), is_active=True).first()
        except (TypeError, ValueError):
            don_vi = None
        if not don_vi:
            return jsonify({"success": False, "message": "Đơn vị không hợp lệ."}), 400
    elif don_vi_text:
        don_vi = _get_or_create_don_vi(don_vi_text)
    user = User.query.filter_by(ma_cbsv=ma_cbsv).first()
    now = datetime.utcnow()

    if not user:
        user = User(
            ma_cbsv=ma_cbsv,
            ho_ten=ho_ten,
            don_vi_id=don_vi.id if don_vi else None,
            chuc_vu=(payload.get("chuc_vu") or None),
            so_dien_thoai=(payload.get("so_dien_thoai") or None),
            email=email,
            created_at=now,
        )
        db.session.add(user)
    else:
        user.ho_ten = ho_ten or user.ho_ten
        user.email = email
        if don_vi:
            user.don_vi_id = don_vi.id
        user.updated_at = now

    existed = Registration.query.filter_by(ma_cbsv=ma_cbsv, event_id=event_id).first()
    if existed:
        db.session.commit()
        return jsonify({"success": False, "message": f"Mã {ma_cbsv} đã đăng ký sự kiện này."}), 409

    registration = Registration(
        ma_cbsv=ma_cbsv,
        event_id=event_id,
        thoi_gian_dang_ky=now,
    )
    db.session.add(registration)
    db.session.commit()

    return jsonify({
        "success": True,
        "message": f"Đăng ký thành công cho {user.ho_ten}.",
        "data": registration.to_dict(),
    })
