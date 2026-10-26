import json
import secrets
from io import BytesIO

from flask import Blueprint, jsonify, redirect, render_template, request, url_for
from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from PIL import Image, UnidentifiedImageError
from sqlalchemy.exc import IntegrityError

from event_checkin.controllers.admin_controller import (
    _ascii_filename_component,
    _xlsx_response,
    admin_required,
)
from event_checkin.models import db
from event_checkin.models.checkin_record import CheckinRecord
from event_checkin.models.event import Event
from event_checkin.models.lucky_draw import LuckyConfig, LuckyPrize, LuckyWinner
from event_checkin.models.user import User
from event_checkin.utils.lucky_draw import UPLOAD_SUBDIR, background_path, purge_event_data, remove_files, upload_dir
from event_checkin.utils.timezone import format_local, now_vn_naive


lucky_bp = Blueprint("lucky", __name__)

DEFAULT_BACKGROUND = "lucky/background.jpg"
BACKGROUND_MAX_BYTES = 5 * 1024 * 1024
BACKGROUND_MAX_SIDE = 8000
BACKGROUND_FORMATS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}
MAX_PRIZES = 100
MAX_PRIZE_NAME_LENGTH = 255
MAX_PRIZE_QUANTITY = 1000
DECOY_LIMIT = 100  # số mã "mồi" gửi cho màn hình để chạy hiệu ứng
TIME_FORMAT = "%H:%M:%S %d/%m/%Y"


class DrawError(Exception):
    def __init__(self, message, status=400, errors=None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.errors = errors


@lucky_bp.errorhandler(DrawError)
def _handle_draw_error(error):
    db.session.rollback()
    body = {"success": False, "message": error.message}
    if error.errors:
        body["errors"] = error.errors  # [{"index": số dòng giải (từ 0), "field": ..., "message": ...}]
    return jsonify(body), error.status


# ---------- Khoá và truy cập thiết lập ----------

def _get_config(event_id):
    """Dòng thiết lập (không khoá), hoặc None nếu sự kiện chưa thiết lập."""
    return db.session.get(LuckyConfig, event_id)


def _require_config(event_id):
    config = _get_config(event_id)
    if not config:
        raise DrawError("Sự kiện này chưa thiết lập quay số.", 404)
    return config


def _lock_config(event_id):
    """Khoá hàng thiết lập của sự kiện đến hết transaction (SELECT ... FOR UPDATE). Mọi thao tác
    quay/lưu/huỷ/sửa/xoá thiết lập đều đi qua đây nên chạy tuần tự theo từng sự kiện.

    MySQL mặc định REPEATABLE READ: ảnh chụp dữ liệu được lấy ở lần đọc đầu tiên của transaction.
    admin_required đã đọc bảng admins từ trước, nên nếu cứ khoá tiếp trong transaction đó thì sau
    khi chờ được khoá, tab thứ hai vẫn thấy dữ liệu CŨ (không thấy kết quả chờ của tab thứ nhất).
    Vì vậy: kết thúc transaction đọc, mở transaction mới ở mức READ COMMITTED rồi mới khoá --
    mọi lần đọc sau khoá đều thấy dữ liệu mới nhất."""
    db.session.commit()
    if db.engine.dialect.name in ("mysql", "mariadb"):
        db.session.connection(execution_options={"isolation_level": "READ COMMITTED"})
    config = (
        LuckyConfig.query.filter_by(event_id=event_id)
        .with_for_update().populate_existing().one_or_none()
    )
    if not config:
        raise DrawError("Sự kiện này chưa thiết lập quay số (hoặc thiết lập vừa bị xoá).", 404)
    return config


# ---------- Danh sách quay ----------

def _valid_code(code):
    return bool(code) and len(code) <= 50 and not any(ch.isspace() for ch in code)


def _participants(event_id):
    """{patron_code: họ tên} của mọi người có ít nhất 1 dòng check-in, gộp trùng theo mã.
    KHÔNG lọc theo cert_status: lỗi gửi email không liên quan đến việc người đó có mặt.
    Tên: cert_display_name -> patron_name -> tên đăng ký (User) -> trống; ưu tiên dòng không 'duplicate'."""
    records = (
        CheckinRecord.query.filter_by(event_id=event_id)
        .order_by(CheckinRecord.checkin_at.asc(), CheckinRecord.id.asc())
        .all()
    )
    by_code = {}
    for item in records:
        code = (item.patron_code or "").strip()
        if _valid_code(code):
            by_code.setdefault(code, []).append(item)
    users = {
        user.ma_cbsv: user
        for user in User.query.filter(User.ma_cbsv.in_(list(by_code))).all()
    } if by_code else {}
    result = {}
    for code, items in by_code.items():
        items = sorted(items, key=lambda record: record.cert_status == "duplicate")
        name = (
            next((i.cert_display_name.strip() for i in items if i.cert_display_name and i.cert_display_name.strip()), "")
            or next((i.patron_name.strip() for i in items if i.patron_name and i.patron_name.strip()), "")
            or (users[code].ho_ten if code in users else "")
        )
        result[code] = name
    return result


def _active_winners(event_id):
    return LuckyWinner.query.filter_by(event_id=event_id, hieu_luc=1).all()


def _eligible_codes(participants, allow_multi, active, prize_id):
    """Mã còn được quay cho giải prize_id: bỏ người đã trúng (mọi giải, hoặc chỉ giải này nếu
    cho phép trúng nhiều giải). Tính cả kết quả đang chờ Lưu."""
    if allow_multi:
        taken = {w.patron_code for w in active if w.prize_id == prize_id}
    else:
        taken = {w.patron_code for w in active}
    return sorted(code for code in participants if code not in taken)


# ---------- Dữ liệu trả về ----------

def _background_url(config):
    path = background_path(config.hinh_nen) if config else None
    if path and path.exists():
        return url_for("static", filename=config.hinh_nen)
    return url_for("static", filename=DEFAULT_BACKGROUND)


def _winner_payload(winner, with_name):
    payload = {
        "id": winner.id,
        "prize_id": winner.prize_id,
        "ten_giai": winner.prize.ten_giai if winner.prize else "",
        "patron_code": winner.patron_code,
        "trang_thai": winner.trang_thai,
        "trung_luc": format_local(winner.trung_luc, TIME_FORMAT),
    }
    if with_name:  # màn hình chiếu chỉ cần mã, không gửi họ tên
        payload["ho_ten"] = winner.ho_ten or ""
        payload["huy_luc"] = format_local(winner.huy_luc, TIME_FORMAT)
    return payload


def _setup_payload(event, config):
    """Dữ liệu cho trang thiết lập (config=None: thiết lập mới)."""
    prizes = []
    if config:
        rows = LuckyPrize.query.filter_by(event_id=event.id).order_by(LuckyPrize.thu_tu, LuckyPrize.id).all()
        history = dict(
            db.session.query(LuckyWinner.prize_id, db.func.count(LuckyWinner.id))
            .filter_by(event_id=event.id).group_by(LuckyWinner.prize_id).all()
        )
        active = dict(
            db.session.query(LuckyWinner.prize_id, db.func.count(LuckyWinner.id))
            .filter_by(event_id=event.id, hieu_luc=1).group_by(LuckyWinner.prize_id).all()
        )
        prizes = [
            {
                "id": prize.id,
                "ten_giai": prize.ten_giai,
                "so_luong": prize.so_luong,
                "da_quay": active.get(prize.id, 0),
                "co_lich_su": history.get(prize.id, 0) > 0,
            }
            for prize in rows
        ]
    return {
        "event_id": event.id,
        "ten_su_kien": event.ten_su_kien,
        "tong_nguoi": len(_participants(event.id)),
        "da_thiet_lap": bool(config),
        "phien_ban": config.phien_ban if config else None,
        "cho_phep_trung_nhieu_giai": bool(config and config.cho_phep_trung_nhieu_giai),
        "hinh_nen_url": _background_url(config),
        "hinh_nen_tuy_chinh": bool(config and config.hinh_nen),
        "prizes": prizes,
    }


def _state(event, config, with_name):
    participants = _participants(event.id)
    prizes = LuckyPrize.query.filter_by(event_id=event.id).order_by(LuckyPrize.thu_tu, LuckyPrize.id).all()
    winners = (
        LuckyWinner.query.filter_by(event_id=event.id)
        .order_by(LuckyWinner.trung_luc.asc(), LuckyWinner.id.asc())
        .all()
    )
    active = [w for w in winners if w.hieu_luc == 1]
    allow_multi = bool(config.cho_phep_trung_nhieu_giai)
    prize_rows = []
    for prize in prizes:
        used = sum(1 for w in active if w.prize_id == prize.id)
        prize_rows.append({
            "id": prize.id,
            "ten_giai": prize.ten_giai,
            "so_luong": prize.so_luong,
            "thu_tu": prize.thu_tu,
            "da_quay": used,
            "con_lai": max(prize.so_luong - used, 0),
            "nguoi_con_lai": len(_eligible_codes(participants, allow_multi, active, prize.id)),
        })
    return {
        "success": True,
        "event": {"id": event.id, "ten_su_kien": event.ten_su_kien},
        "tong_nguoi": len(participants),
        "cho_phep_trung_nhieu_giai": allow_multi,
        "hinh_nen_url": _background_url(config),
        "prizes": prize_rows,
        "pending": [_winner_payload(w, with_name) for w in winners if w.trang_thai == "pending"],
        "winners": [_winner_payload(w, with_name) for w in winners if w.trang_thai == "confirmed"],
        "cancelled": [_winner_payload(w, with_name) for w in winners if w.trang_thai == "cancelled"] if with_name else [],
    }


def _checkin_counts():
    """{event_id: số người (mã khác nhau) đã check-in}."""
    return dict(
        db.session.query(CheckinRecord.event_id, db.func.count(db.distinct(CheckinRecord.patron_code)))
        .group_by(CheckinRecord.event_id).all()
    )


# ---------- Trang ----------

@lucky_bp.get("/admin/lucky-draw")
@admin_required
def lucky_list():
    """Danh sách sự kiện đã thiết lập quay số."""
    configs = LuckyConfig.query.all()
    events = {e.id: e for e in Event.query.filter(Event.id.in_([c.event_id for c in configs])).all()} if configs else {}
    prize_stats = {
        event_id: (count, total or 0)
        for event_id, count, total in db.session.query(
            LuckyPrize.event_id, db.func.count(LuckyPrize.id), db.func.sum(LuckyPrize.so_luong)
        ).group_by(LuckyPrize.event_id).all()
    }
    win_stats = {}
    for event_id, status, count in (
        db.session.query(LuckyWinner.event_id, LuckyWinner.trang_thai, db.func.count(LuckyWinner.id))
        .group_by(LuckyWinner.event_id, LuckyWinner.trang_thai).all()
    ):
        win_stats.setdefault(event_id, {})[status] = count
    checkins = _checkin_counts()
    rows = []
    for config in configs:
        event = events.get(config.event_id)
        if not event:
            continue
        stats = win_stats.get(event.id, {})
        prize_count, slots = prize_stats.get(event.id, (0, 0))
        rows.append({
            "event_id": event.id,
            "ten_su_kien": event.ten_su_kien,
            "ngay": format_local(event.ngay_bat_dau, "%d/%m/%Y"),
            "so_giai": prize_count,
            "so_suat": slots,
            "da_trung": stats.get("confirmed", 0),
            "cho_luu": stats.get("pending", 0),
            "da_huy": stats.get("cancelled", 0),
            "tong_ket_qua": sum(stats.values()),
            "nguoi_checkin": checkins.get(event.id, 0),
            "cap_nhat": format_local(config.updated_at),
        })
    rows.sort(key=lambda row: row["event_id"], reverse=True)
    unset_count = Event.query.count() - len(rows)
    return render_template("admin/lucky_list.html", rows=rows, unset_count=max(unset_count, 0))


@lucky_bp.get("/admin/lucky-draw/setup")
@admin_required
def lucky_setup_new():
    """Thiết lập cho một sự kiện CHƯA có thiết lập (chọn sự kiện ở đây)."""
    configured = {row[0] for row in db.session.query(LuckyConfig.event_id).all()}
    checkins = _checkin_counts()
    events = [
        {"id": e.id, "ten_su_kien": e.ten_su_kien, "ngay": format_local(e.ngay_bat_dau, "%d/%m/%Y"), "nguoi_checkin": checkins.get(e.id, 0)}
        for e in Event.query.order_by(Event.ngay_bat_dau.desc()).all()
        if e.id not in configured
    ]
    return render_template(
        "admin/lucky_setup.html",
        mode="new",
        events=events,
        preselect=request.args.get("event_id", type=int),
        notice="Sự kiện này chưa thiết lập quay số. Hãy thiết lập rồi bấm Lưu." if request.args.get("chua") else "",
        data={
            "event_id": None, "ten_su_kien": "", "tong_nguoi": 0, "da_thiet_lap": False, "phien_ban": None,
            "cho_phep_trung_nhieu_giai": False, "hinh_nen_tuy_chinh": False, "prizes": [],
            "hinh_nen_url": url_for("static", filename=DEFAULT_BACKGROUND),
        },
        default_background_url=url_for("static", filename=DEFAULT_BACKGROUND),
    )


@lucky_bp.get("/admin/lucky-draw/<int:event_id>/setup")
@admin_required
def lucky_setup_edit(event_id):
    event = Event.query.get_or_404(event_id)
    config = _get_config(event_id)
    if not config:
        return redirect(url_for("lucky.lucky_setup_new", event_id=event_id))
    return render_template(
        "admin/lucky_setup.html",
        mode="edit",
        events=[],
        preselect=event_id,
        notice="Đã lưu thiết lập." if request.args.get("da_luu") else "",
        data=_setup_payload(event, config),
        default_background_url=url_for("static", filename=DEFAULT_BACKGROUND),
    )


@lucky_bp.get("/admin/lucky-draw/<int:event_id>/screen")
@admin_required
def lucky_screen(event_id):
    event = Event.query.get_or_404(event_id)
    if not _get_config(event_id):
        return redirect(url_for("lucky.lucky_setup_new", event_id=event_id, chua=1))
    return render_template(
        "admin/lucky_screen.html",
        event=event,
        back_url=url_for("lucky.lucky_list"),
        setup_url=url_for("lucky.lucky_setup_edit", event_id=event_id),
    )


# ---------- Lưu thiết lập (một transaction) ----------

def _parse_setup_form():
    """Đọc multipart: trường JSON `data` + file `hinh_nen` (tuỳ chọn)."""
    try:
        payload = json.loads(request.form.get("data") or "")
    except (TypeError, ValueError):
        raise DrawError("Dữ liệu gửi lên không hợp lệ.")
    if not isinstance(payload, dict):
        raise DrawError("Dữ liệu gửi lên không hợp lệ.")
    if not isinstance(payload.get("cho_phep_trung_nhieu_giai", False), bool):
        raise DrawError("Tuỳ chọn trúng nhiều giải không hợp lệ.")
    prizes = payload.get("prizes")
    if not isinstance(prizes, list) or not prizes:
        raise DrawError("Cần có ít nhất 1 giải thưởng.", errors=[{"index": 0, "field": "ten_giai", "message": "Cần có ít nhất 1 giải."}])
    if len(prizes) > MAX_PRIZES:
        raise DrawError(f"Tối đa {MAX_PRIZES} giải.")
    return payload


def _validate_prizes(prizes):
    """Kiểm tra tên/số lượng từng dòng. Trả về danh sách dòng đã làm sạch + lỗi (nếu có)."""
    cleaned, errors = [], []
    for index, item in enumerate(prizes):
        if not isinstance(item, dict):
            errors.append({"index": index, "field": "ten_giai", "message": "Dòng giải không hợp lệ."})
            cleaned.append(None)
            continue
        name = " ".join(str(item.get("ten_giai") or "").split())
        if not name:
            errors.append({"index": index, "field": "ten_giai", "message": "Tên giải không được để trống."})
        elif len(name) > MAX_PRIZE_NAME_LENGTH:
            errors.append({"index": index, "field": "ten_giai", "message": f"Tên giải tối đa {MAX_PRIZE_NAME_LENGTH} ký tự."})
        quantity = item.get("so_luong")
        if isinstance(quantity, bool) or not isinstance(quantity, int):
            try:
                quantity = int(str(quantity).strip())
            except (TypeError, ValueError):
                quantity = None
        if quantity is None or quantity < 1 or quantity > MAX_PRIZE_QUANTITY:
            errors.append({"index": index, "field": "so_luong", "message": f"Số lượng phải là số nguyên từ 1 đến {MAX_PRIZE_QUANTITY}."})
        prize_id = item.get("id")
        if prize_id is not None and (isinstance(prize_id, bool) or not isinstance(prize_id, int)):
            errors.append({"index": index, "field": "ten_giai", "message": "Mã giải không hợp lệ."})
            prize_id = None
        cleaned.append({"id": prize_id, "ten_giai": name, "so_luong": quantity})
    return cleaned, errors


def _read_background(file):
    """Đọc và kiểm tra file ảnh nền: dung lượng, đúng là ảnh (Pillow), định dạng JPG/PNG/WEBP, kích thước.
    Trả về (bytes, đuôi file). Đuôi lấy theo định dạng thật, không tin tên file người dùng."""
    data = file.stream.read(BACKGROUND_MAX_BYTES + 1)
    if len(data) > BACKGROUND_MAX_BYTES:
        raise DrawError("Hình nền tối đa 5MB.")
    try:
        with Image.open(BytesIO(data)) as image:
            detected = image.format
            width, height = image.size
            image.verify()  # đúng là file ảnh nguyên vẹn, không tin đuôi file
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError):
        raise DrawError("File không phải ảnh hợp lệ. Chỉ nhận JPG, PNG hoặc WEBP.")
    extension = BACKGROUND_FORMATS.get(detected)
    if not extension:
        raise DrawError("Chỉ nhận ảnh JPG, PNG hoặc WEBP.")
    if width > BACKGROUND_MAX_SIDE or height > BACKGROUND_MAX_SIDE:
        raise DrawError(f"Kích thước ảnh tối đa {BACKGROUND_MAX_SIDE}px mỗi cạnh.")
    return data, extension


@lucky_bp.put("/api/admin/lucky-draw/<int:event_id>/setup")
@admin_required
def lucky_save_setup(event_id):
    """Lưu cả thiết lập (giải, tuỳ chọn, ảnh nền) trong 1 transaction: lỗi thì không đổi gì trong DB."""
    event = Event.query.get_or_404(event_id)
    payload = _parse_setup_form()
    cleaned, errors = _validate_prizes(payload["prizes"])
    file = request.files.get("hinh_nen")
    new_image = _read_background(file) if file and file.filename else None  # ảnh hỏng thì dừng trước khi đụng DB
    reset_image = bool(payload.get("xoa_hinh_nen")) and not new_image
    allow_multi = bool(payload.get("cho_phep_trung_nhieu_giai"))
    if errors:
        raise DrawError("Có dòng giải chưa hợp lệ, hãy sửa rồi Lưu lại.", errors=errors)

    exists = _get_config(event_id) is not None
    new_path = None
    old_path = None
    try:
        if exists:
            config = _lock_config(event_id)
            if payload.get("phien_ban") != config.phien_ban:
                raise DrawError("Thiết lập vừa được thay đổi ở nơi khác (tab hoặc admin khác). Hãy tải lại trang để xem bản mới; dữ liệu bạn đang nhập vẫn còn trên màn hình.", 409)
        else:
            if payload.get("phien_ban") is not None:
                raise DrawError("Thiết lập này vừa bị xoá ở nơi khác. Hãy tải lại trang.", 409)
            db.session.commit()
            config = LuckyConfig(event_id=event_id, cho_phep_trung_nhieu_giai=allow_multi, phien_ban=0)
            db.session.add(config)
            try:
                db.session.flush()
            except IntegrityError:
                db.session.rollback()
                raise DrawError("Sự kiện này vừa được thiết lập ở nơi khác. Hãy tải lại trang.", 409)

        existing = {p.id: p for p in LuckyPrize.query.filter_by(event_id=event_id).all()}
        history = {
            prize_id: count for prize_id, count in db.session.query(LuckyWinner.prize_id, db.func.count(LuckyWinner.id))
            .filter_by(event_id=event_id).group_by(LuckyWinner.prize_id).all()
        }
        active = {
            prize_id: count for prize_id, count in db.session.query(LuckyWinner.prize_id, db.func.count(LuckyWinner.id))
            .filter_by(event_id=event_id, hieu_luc=1).group_by(LuckyWinner.prize_id).all()
        }
        keep_ids = set()
        for index, item in enumerate(cleaned):
            if item["id"] is None:
                continue
            if item["id"] not in existing:
                errors.append({"index": index, "field": "ten_giai", "message": "Giải này không còn tồn tại, hãy tải lại trang."})
            elif item["id"] in keep_ids:
                errors.append({"index": index, "field": "ten_giai", "message": "Giải bị lặp."})
            else:
                keep_ids.add(item["id"])
                used = active.get(item["id"], 0)
                if item["so_luong"] < used:
                    errors.append({"index": index, "field": "so_luong", "message": f"Giải này đã có {used} người trúng, số lượng không được nhỏ hơn {used}."})
        for prize_id, prize in existing.items():
            if prize_id not in keep_ids and history.get(prize_id, 0):
                errors.append({"index": None, "field": "xoa", "message": f"Giải \"{prize.ten_giai}\" đã có lịch sử quay nên không xoá được."})
        if errors:
            blocked = [e for e in errors if e["index"] is None]
            message = blocked[0]["message"] if blocked else "Có dòng giải chưa hợp lệ, hãy sửa rồi Lưu lại."
            raise DrawError(message, errors=[e for e in errors if e["index"] is not None])

        for prize_id, prize in existing.items():
            if prize_id not in keep_ids:
                db.session.delete(prize)
        db.session.flush()
        for position, item in enumerate(cleaned, start=1):
            if item["id"] is None:
                db.session.add(LuckyPrize(event_id=event_id, ten_giai=item["ten_giai"], so_luong=item["so_luong"], thu_tu=position))
            else:
                prize = existing[item["id"]]
                prize.ten_giai, prize.so_luong, prize.thu_tu = item["ten_giai"], item["so_luong"], position

        config.cho_phep_trung_nhieu_giai = allow_multi
        old_path = background_path(config.hinh_nen)
        if new_image:
            data, extension = new_image
            upload_dir().mkdir(parents=True, exist_ok=True)
            filename = f"bg_{event_id}_{secrets.token_hex(12)}.{extension}"  # tên ngẫu nhiên, không dùng tên người dùng
            new_path = upload_dir() / filename
            new_path.write_bytes(data)
            config.hinh_nen = f"{UPLOAD_SUBDIR}/{filename}"
        elif reset_image:
            config.hinh_nen = None
        else:
            old_path = None  # không đổi ảnh thì không xoá gì
        config.phien_ban = (config.phien_ban or 0) + 1
        config.updated_at = now_vn_naive()
        db.session.commit()
    except Exception:
        db.session.rollback()
        if new_path:
            new_path.unlink(missing_ok=True)
        raise
    remove_files([old_path] if old_path else [])  # chỉ xoá ảnh cũ sau khi DB đã commit

    config = _get_config(event_id)
    return jsonify({"success": True, "message": "Đã lưu thiết lập.", "data": _setup_payload(event, config)})


# ---------- Xoá thiết lập ----------

@lucky_bp.delete("/api/admin/lucky-draw/<int:event_id>")
@admin_required
def lucky_delete_setup(event_id):
    """Xoá thiết lập: giải thưởng, kết quả (kể cả bản huỷ), ảnh nền -- trong 1 transaction.
    KHÔNG xoá sự kiện và dữ liệu check-in. Đã có kết quả thì phải gõ lại đúng tên sự kiện."""
    event = Event.query.get_or_404(event_id)
    payload = request.get_json(silent=True) or {}
    _lock_config(event_id)
    total = LuckyWinner.query.filter_by(event_id=event_id).count()
    if total:
        typed = " ".join(str(payload.get("xac_nhan_ten") or "").split())
        if typed != " ".join(event.ten_su_kien.split()):
            raise DrawError("Tên sự kiện gõ lại chưa đúng nên chưa xoá. Hãy gõ chính xác tên sự kiện để xác nhận.", 400)
    files = purge_event_data(event_id)
    db.session.commit()
    remove_files(files)
    message = f"Đã xoá thiết lập quay số của sự kiện." + (f" Đã xoá {total} kết quả." if total else "")
    return jsonify({"success": True, "message": message, "da_xoa_ket_qua": total})


# ---------- Trạng thái ----------

@lucky_bp.get("/api/admin/lucky-draw/<int:event_id>")
@admin_required
def lucky_state(event_id):
    event = Event.query.get_or_404(event_id)
    config = _require_config(event_id)
    with_name = request.args.get("screen") != "1"
    return jsonify(_state(event, config, with_name))


# ---------- Quay / Lưu / Quay lại / Huỷ ----------

def _get_prize(event_id, prize_id):
    prize = db.session.get(LuckyPrize, prize_id)
    if not prize or prize.event_id != event_id:
        raise DrawError("Không tìm thấy giải thưởng.", 404)
    return prize


@lucky_bp.post("/api/admin/lucky-draw/<int:event_id>/draw")
@admin_required
def lucky_draw(event_id):
    """Quay 1 người cho giải prize_id. Kết quả ở trạng thái chờ (pending) đến khi Lưu hoặc Quay lại."""
    Event.query.get_or_404(event_id)
    payload = request.get_json(silent=True) or {}
    prize_id = payload.get("prize_id")
    if isinstance(prize_id, bool) or not isinstance(prize_id, int):
        raise DrawError("Giải không hợp lệ.")

    config = _lock_config(event_id)  # từ đây các lượt quay của sự kiện này chạy lần lượt
    if LuckyWinner.query.filter_by(event_id=event_id, trang_thai="pending").count():
        raise DrawError("Đang có kết quả chờ Lưu hoặc Quay lại (có thể ở tab khác). Hãy xử lý kết quả đó trước.", 409)
    prize = _get_prize(event_id, prize_id)

    active = _active_winners(event_id)
    if sum(1 for w in active if w.prize_id == prize.id) >= prize.so_luong:
        raise DrawError(f"{prize.ten_giai} đã quay đủ {prize.so_luong} người.", 409)

    participants = _participants(event_id)
    if not participants:
        raise DrawError("Sự kiện này chưa có ai check-in nên chưa có danh sách để quay.", 409)
    pool = _eligible_codes(participants, config.cho_phep_trung_nhieu_giai, active, prize.id)
    if not pool:
        raise DrawError("Đã hết người trong danh sách quay.", 409)

    chooser = secrets.SystemRandom()
    code = chooser.choice(pool)
    winner = LuckyWinner(
        event_id=event_id, prize_id=prize.id, patron_code=code, ho_ten=participants[code] or None,
        trang_thai="pending", trung_luc=now_vn_naive(), hieu_luc=1,
    )
    db.session.add(winner)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise DrawError("Kết quả vừa bị trùng với một lượt quay khác, vui lòng thử lại.", 409)

    decoys = chooser.sample(sorted(participants), min(DECOY_LIMIT, len(participants)))
    return jsonify({
        "success": True,
        "winners": [{"id": winner.id, "patron_code": code}],
        "decoys": decoys,
        "prize": {"id": prize.id, "ten_giai": prize.ten_giai},
    })


@lucky_bp.post("/api/admin/lucky-draw/<int:event_id>/confirm")
@admin_required
def lucky_confirm(event_id):
    """Lưu: chốt kết quả đang chờ."""
    Event.query.get_or_404(event_id)
    _lock_config(event_id)
    pending = LuckyWinner.query.filter_by(event_id=event_id, trang_thai="pending").all()
    if not pending:
        raise DrawError("Không có kết quả nào đang chờ Lưu.", 409)
    for winner in pending:
        winner.trang_thai = "confirmed"
    db.session.commit()
    return jsonify({"success": True, "message": f"Đã lưu: {pending[0].patron_code}."})


@lucky_bp.post("/api/admin/lucky-draw/<int:event_id>/reject")
@admin_required
def lucky_reject(event_id):
    """Quay lại: bỏ kết quả đang chờ (chưa Lưu nên xoá hẳn, người đó quay lại danh sách quay)."""
    Event.query.get_or_404(event_id)
    _lock_config(event_id)
    count = LuckyWinner.query.filter_by(event_id=event_id, trang_thai="pending").delete()
    if not count:
        raise DrawError("Không có kết quả nào đang chờ để bỏ.", 409)
    db.session.commit()
    return jsonify({"success": True, "message": "Đã bỏ kết quả, có thể quay lại."})


@lucky_bp.post("/api/admin/lucky-draw/<int:event_id>/winners/<int:winner_id>/cancel")
@admin_required
def lucky_cancel(event_id, winner_id):
    """Huỷ người vắng mặt: giữ bản ghi để đối chiếu, người này quay lại danh sách quay."""
    Event.query.get_or_404(event_id)
    _lock_config(event_id)
    winner = db.session.get(LuckyWinner, winner_id)
    if not winner or winner.event_id != event_id:
        raise DrawError("Không tìm thấy kết quả.", 404)
    if winner.trang_thai != "confirmed":
        raise DrawError("Chỉ huỷ được kết quả đã lưu. Kết quả đang chờ hãy bấm Quay lại.", 409)
    winner.trang_thai = "cancelled"
    winner.huy_luc = now_vn_naive()
    winner.hieu_luc = None
    db.session.commit()
    return jsonify({"success": True, "message": f"Đã huỷ kết quả của {winner.patron_code}. Người này được đưa lại vào danh sách quay."})


# ---------- Xuất Excel ----------

@lucky_bp.get("/api/admin/lucky-draw/<int:event_id>/export")
@admin_required
def lucky_export(event_id):
    event = Event.query.get_or_404(event_id)
    _require_config(event_id)
    winners = LuckyWinner.query.filter(LuckyWinner.event_id == event_id, LuckyWinner.trang_thai != "pending").all()
    confirmed = sorted(
        (w for w in winners if w.trang_thai == "confirmed"),
        key=lambda w: (w.prize.thu_tu, w.prize_id, w.trung_luc, w.id),
    )
    if not confirmed:
        return jsonify({"success": False, "message": "Chưa có kết quả trúng thưởng để xuất."}), 400
    cancelled = sorted((w for w in winners if w.trang_thai == "cancelled"), key=lambda w: (w.huy_luc or w.trung_luc, w.id))

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Trung thuong"
    sheet.append(["STT", "Giải", "Mã CB/SV", "Họ tên", "Giờ trúng"])
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for position, w in enumerate(confirmed, start=1):
        sheet.append([position, w.prize.ten_giai, w.patron_code, w.ho_ten or "", format_local(w.trung_luc, TIME_FORMAT)])
    for index, width in enumerate([6, 24, 16, 28, 22], start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width

    if cancelled:
        sheet2 = workbook.create_sheet("Da huy (vang mat)")
        sheet2.append(["STT", "Giải", "Mã CB/SV", "Họ tên", "Giờ trúng", "Giờ huỷ"])
        for cell in sheet2[1]:
            cell.font = Font(bold=True)
        for position, w in enumerate(cancelled, start=1):
            sheet2.append([
                position, w.prize.ten_giai, w.patron_code, w.ho_ten or "",
                format_local(w.trung_luc, TIME_FORMAT), format_local(w.huy_luc, TIME_FORMAT),
            ])
        for index, width in enumerate([6, 24, 16, 28, 22, 22], start=1):
            sheet2.column_dimensions[get_column_letter(index)].width = width

    today = now_vn_naive().strftime("%d-%m-%Y")
    return _xlsx_response(
        workbook,
        f"{event.ten_su_kien}_quayso_{today}.xlsx",
        f"{_ascii_filename_component(event.ten_su_kien)}_quayso_{today}.xlsx",
    )
