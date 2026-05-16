from flask import Blueprint, jsonify, render_template, request

from event_checkin.models import db
from event_checkin.models.registration import Registration
from event_checkin.models.user import User


register_bp = Blueprint("register", __name__)


@register_bp.get("/")
def index():
    return render_template("register/index.html")


@register_bp.get("/api/lookup/<ma_cbsv>")
def lookup(ma_cbsv):
    ma_cbsv = (ma_cbsv or "").strip()
    user = User.query.filter_by(ma_cbsv=ma_cbsv).first()
    if not user:
        return jsonify({"success": False, "message": f"Không tìm thấy mã {ma_cbsv}."}), 404
    return jsonify({"success": True, "data": user.to_dict()})


@register_bp.post("/register")
def register():
    payload = request.get_json(silent=True) or request.form
    ma_cbsv = (payload.get("ma_cbsv") or "").strip()
    ho_ten = (payload.get("ho_ten") or "").strip()
    don_vi = (payload.get("don_vi") or "").strip()
    email = (payload.get("email") or "").strip()

    if not ma_cbsv or not ho_ten or not email:
        return jsonify({"success": False, "message": "Vui lòng nhập đầy đủ mã, họ tên và email."}), 400

    user = User.query.filter_by(ma_cbsv=ma_cbsv).first()

    # Nếu mã chưa có trong bảng users thì tự tạo một record User mới
    # (đảm bảo người dùng vẫn có thể đăng ký tại chỗ)
    if not user:
        user = User(
            ma_cbsv=ma_cbsv,
            ho_ten=ho_ten,
            don_vi=don_vi or None,
            chuc_vu=(payload.get("chuc_vu") or None),
            so_dien_thoai=(payload.get("so_dien_thoai") or None),
            email=email,
        )
        db.session.add(user)
        db.session.commit()
    else:
        # Luôn ưu tiên email vừa nhập trong form đăng ký
        if email != user.email:
            user.email = email
            db.session.commit()

    existed = Registration.query.filter_by(ma_cbsv=ma_cbsv).first()
    if existed:
        return jsonify({"success": False, "message": f"Mã {ma_cbsv} đã đăng ký trước đó."}), 409

    registration = Registration(
        ma_cbsv=ma_cbsv,
        ho_ten=ho_ten,
        don_vi=don_vi or user.don_vi,
        email=email,
    )
    db.session.add(registration)
    db.session.commit()

    return jsonify({
        "success": True,
        "message": f"Đăng ký thành công cho {registration.ho_ten}.",
        "data": registration.to_dict(),
    })
