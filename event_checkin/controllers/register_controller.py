import re
from datetime import datetime

from flask import Blueprint, jsonify, render_template, request, url_for
from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError

from event_checkin.models import db
from event_checkin.models.don_vi import DonVi
from event_checkin.models.event import Event
from event_checkin.models.registration import Registration
from event_checkin.models.user import User


register_bp = Blueprint("register", __name__)
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PHONE_PATTERN = re.compile(r"^\d{9,11}$")
MONTH_GROUPS_PER_PAGE = 3


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


def _distinct_month_keys():
    """(nam, thang) pairs that have at least one event, newest month first. Kept as
    its own lightweight query so paging through months never has to load every
    event just to find out which months exist.
    """
    rows = (
        db.session.query(Event.nam, Event.thang)
        .distinct()
        .order_by(Event.nam.desc(), Event.thang.desc())
        .all()
    )
    return [(row[0], row[1]) for row in rows]


def _month_groups_page(offset, limit=MONTH_GROUPS_PER_PAGE):
    """Returns (groups, next_offset, has_more) for the `limit` non-empty months
    starting at `offset` (both counted in "months that actually have events", not
    events or fixed calendar months -- an empty month is never counted or fetched).
    Months are newest-first; events within a month are ordered by ngay_bat_dau
    ascending. Only the events belonging to the requested page of months are
    queried, never the whole table.
    """
    month_keys = _distinct_month_keys()
    page_keys = month_keys[offset:offset + limit]
    next_offset = offset + len(page_keys)
    has_more = next_offset < len(month_keys)

    # Year is only appended to the label when the event list as a whole spans more
    # than one year, so "Tháng 9:" stays short in the common single-year case --
    # based on every known month, not just this page, so labels stay consistent
    # as more pages are appended.
    multi_year = len({nam for nam, _thang in month_keys}) > 1

    events_by_key = {}
    if page_keys:
        conditions = [and_(Event.nam == nam, Event.thang == thang) for nam, thang in page_keys]
        page_events = Event.query.filter(or_(*conditions)).order_by(Event.ngay_bat_dau.asc()).all()
        for event in page_events:
            events_by_key.setdefault((event.nam, event.thang), []).append(event)

    groups = [
        {
            "nam": nam,
            "thang": thang,
            "label": f"Tháng {thang}/{nam}" if multi_year else f"Tháng {thang}",
            "events": events_by_key.get((nam, thang), []),
        }
        for nam, thang in page_keys
    ]
    return groups, next_offset, has_more


@register_bp.get("/")
def index():
    event_groups, next_offset, has_more = _month_groups_page(0)
    don_vi_items = DonVi.query.filter_by(is_active=True).order_by(DonVi.ten_don_vi.asc()).all()
    return render_template(
        "register/index.html",
        event_groups=event_groups,
        next_offset=next_offset,
        has_more=has_more,
        selected_event=None,
        don_vi_items=don_vi_items,
    )


@register_bp.get("/events/<int:event_id>/register")
def event_register(event_id):
    event = Event.query.get_or_404(event_id)
    don_vi_items = DonVi.query.filter_by(is_active=True).order_by(DonVi.ten_don_vi.asc()).all()
    return render_template("register/index.html", selected_event=event, don_vi_items=don_vi_items)


@register_bp.get("/api/events/month-groups")
def events_month_groups():
    try:
        offset = int(request.args.get("offset", 0))
    except (TypeError, ValueError):
        offset = 0
    offset = max(offset, 0)

    groups, next_offset, has_more = _month_groups_page(offset)
    html = render_template("register/_month_groups.html", event_groups=groups)
    return jsonify({
        "success": True,
        "data": {
            "html": html,
            "next_offset": next_offset,
            "has_more": has_more,
        },
    })


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
                "trang_thai": event.computed_status,
                "can_register": event.is_registration_open,
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

    if any(ch.isdigit() for ch in ho_ten):
        return jsonify({"success": False, "message": "Họ tên không được chứa chữ số."}), 400

    so_dien_thoai = (payload.get("so_dien_thoai") or "").strip()
    if so_dien_thoai and not PHONE_PATTERN.match(so_dien_thoai):
        return jsonify({"success": False, "message": "Số điện thoại không hợp lệ (chỉ gồm 9-11 chữ số)."}), 400

    event = Event.query.get(event_id)
    if not event:
        return jsonify({"success": False, "message": "Sự kiện không tồn tại."}), 404

    if not event.is_registration_open:
        return jsonify({"success": False, "message": event.registration_block_reason}), 400

    # Checked before touching User/Registration so a duplicate-registration attempt
    # (which is rejected below) never has the side effect of overwriting the
    # already-registered user's profile fields.
    existed = Registration.query.filter_by(ma_cbsv=ma_cbsv, event_id=event_id).first()
    if existed:
        return jsonify({"success": False, "message": f"Mã {ma_cbsv} đã đăng ký sự kiện này."}), 409

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
            so_dien_thoai=so_dien_thoai or None,
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

    registration = Registration(
        ma_cbsv=ma_cbsv,
        event_id=event_id,
        thoi_gian_dang_ky=now,
    )
    db.session.add(registration)
    try:
        db.session.commit()
    except IntegrityError:
        # Two submits for the same ma_cbsv+event_id landed at (almost) the same
        # time (e.g. a double-tap on the register button) -- the unique
        # constraint rejects the second insert; treat it as already-registered
        # instead of a 500, matching how checkin() handles the same race.
        db.session.rollback()
        return jsonify({"success": False, "message": f"Mã {ma_cbsv} đã đăng ký sự kiện này."}), 409

    return jsonify({
        "success": True,
        "message": f"Đăng ký thành công cho {user.ho_ten}.",
        "data": registration.to_dict(),
    })
