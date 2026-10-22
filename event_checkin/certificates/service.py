from datetime import datetime
from io import BytesIO
import json
from pathlib import Path

from flask import current_app, url_for

from event_checkin.certificates.generator import (
    certificate_values,
    render_certificate_image,
    save_pdf_certificate,
    save_png_certificate,
    save_svg_certificate,
)
from event_checkin.certificates.patron_lookup import PatronLookupError, PatronNotFound, lookup_patron
from event_checkin.certificates.validators import validate_certificate_eligibility
from event_checkin.models import db
from event_checkin.models.certificate import Certificate
from event_checkin.models.checkin_record import CheckinRecord
from event_checkin.models.user import User


DEFAULT_EVENT_ID = 1


class CertificateError(Exception):
    pass


def _storage_root():
    return Path(current_app.static_folder) / "certificates" / "generated"


def _public_url(path):
    relative = path.relative_to(Path(current_app.static_folder)).as_posix()
    return url_for("static", filename=relative, _external=False)


def _stored_file_path(file_url):
    if not file_url:
        return None
    prefix = url_for("static", filename="", _external=False)
    relative = file_url
    if relative.startswith(prefix):
        relative = relative[len(prefix):]
    return Path(current_app.static_folder) / relative


def _next_certificate_code(event_id):
    year = datetime.utcnow().year
    count = Certificate.query.filter_by(event_id=event_id).count() + 1
    return f"USSH-{year}-EVENT{event_id:03d}-{count:06d}"


def resolve_display_name(event_id, ma_cbsv):
    """Họ tên in trên chứng chỉ, theo thứ tự ưu tiên:
    1. Tên admin sửa tay (checkin_records.cert_display_name)
    2. Tên tra từ Sierra (chưa tích hợp) / 3. tên lúc đăng ký -- cả hai qua patron_lookup
    """
    records = (
        CheckinRecord.query.filter_by(event_id=event_id, patron_code=ma_cbsv)
        .order_by(CheckinRecord.checkin_at.asc(), CheckinRecord.id.asc())
        .all()
    )
    # Ưu tiên giá trị trên dòng chính (không phải 'duplicate'), phòng khi lọc trùng/xoá
    # dòng làm giá trị nằm lại ở một dòng trùng.
    for item in sorted(records, key=lambda record: record.cert_status == "duplicate"):
        if item.cert_display_name:
            return item.cert_display_name
    try:
        # Bước 2+3: tra Sierra (khi đã tích hợp), hiện tạm là dữ liệu đăng ký -- xem patron_lookup.py
        return lookup_patron(ma_cbsv).name or ma_cbsv
    except (PatronNotFound, PatronLookupError):
        return ma_cbsv


def event_layout(event, layout=None):
    """(đường dẫn ảnh nền, layout đã gắn đường dẫn font) của sự kiện. Truyền layout
    để dùng cấu hình chưa lưu (xem trước trong trình thiết kế) thay cho bản đã lưu."""
    template_path = None
    if event and event.certificate_enabled and event.certificate_template:
        template_path = Path(current_app.static_folder) / event.certificate_template
    if layout is None and event and event.certificate_layout:
        try:
            layout = json.loads(event.certificate_layout)
        except json.JSONDecodeError:
            layout = None
    if isinstance(layout, dict):
        for config in layout.values():
            if isinstance(config, dict) and config.get("font_file"):
                config["font_path"] = str(Path(current_app.static_folder) / config["font_file"])
    if not template_path or not template_path.exists():
        raise CertificateError("Sự kiện này chưa có mẫu giấy chứng nhận. Vui lòng vào Quản trị > Chứng chỉ để tải mẫu lên.")
    return template_path, layout


PREVIEW_SAMPLE = {"student_name": "Nguyễn Văn A", "ma_cbsv": "2456090063", "don_vi": "Công tác xã hội - Nhân học"}


def render_preview_png(event, patron_code=None, display_name=None, layout=None):
    """Ảnh PNG xem trước, vẽ trong bộ nhớ bằng CÙNG hàm vẽ với chứng chỉ gửi thật.
    Không lưu file, không tạo/tốn mã chứng chỉ. Không có patron_code -> dữ liệu mẫu."""
    template_path, layout = event_layout(event, layout)
    issued_at = datetime.utcnow()
    certificate_code = f"USSH-{issued_at.year}-EVENT{event.id:03d}-XXXXXX"
    if patron_code:
        user = User.query.get(patron_code)
        if not user:
            raise CertificateError(f"Không tìm thấy thông tin của mã {patron_code}.")
        existing = Certificate.query.filter_by(ma_cbsv=patron_code, event_id=event.id).first()
        if existing:
            certificate_code = existing.certificate_code
            issued_at = existing.issued_at or issued_at
        name = display_name or resolve_display_name(event.id, patron_code)
        unit = user.ten_don_vi
    else:
        name = display_name or PREVIEW_SAMPLE["student_name"]
        patron_code = PREVIEW_SAMPLE["ma_cbsv"]
        unit = PREVIEW_SAMPLE["don_vi"]

    values = certificate_values(name, patron_code, unit, certificate_code, issued_at, event.ten_su_kien)
    image = render_certificate_image(template_path, values, layout)
    if image is None:
        raise CertificateError("Không thể vẽ chứng chỉ. Vui lòng kiểm tra file mẫu và font chữ.")
    buffer = BytesIO()
    image.save(buffer, "PNG", optimize=False)
    return buffer.getvalue()


def _render_certificate_file(registration, certificate_code, issued_at, requested_type):
    user = registration.user
    event = registration.event
    student_name = resolve_display_name(registration.event_id, registration.ma_cbsv)
    student_unit = user.ten_don_vi if user else ""
    event_name = event.ten_su_kien if event else ""
    template_path, layout = event_layout(event)
    year_dir = _storage_root() / str(issued_at.year)
    if requested_type == "pdf":
        output_path = year_dir / f"{certificate_code}.pdf"
        rendered_path = save_pdf_certificate(
            output_path,
            student_name,
            registration.ma_cbsv,
            student_unit,
            certificate_code,
            issued_at,
            template_path=template_path,
            layout=layout,
            event_name=event_name,
        )
        if rendered_path is None:
            raise CertificateError("Không thể tạo PDF chứng nhận. Vui lòng kiểm tra Pillow và file mẫu chứng nhận.")
        return output_path, "pdf"

    output_path = year_dir / f"{certificate_code}.png"
    rendered_path = save_png_certificate(
        output_path,
        student_name,
        registration.ma_cbsv,
        student_unit,
        certificate_code,
        issued_at,
        template_path=template_path,
        layout=layout,
        event_name=event_name,
    )
    if rendered_path is None:
        output_path = year_dir / f"{certificate_code}.svg"
        save_svg_certificate(output_path, student_name, registration.ma_cbsv, student_unit, certificate_code, issued_at)
        return output_path, "svg"
    return output_path, "png"


def generate_certificate(ma_cbsv, event_id=DEFAULT_EVENT_ID, file_type="pdf"):
    event_id = int(event_id or DEFAULT_EVENT_ID)
    requested_type = (file_type or "png").lower()

    existing = Certificate.query.filter_by(ma_cbsv=ma_cbsv, event_id=event_id).first()
    if existing:
        eligible, _, registration = validate_certificate_eligibility(ma_cbsv, event_id)
        if eligible:
            previous_path = _stored_file_path(existing.file_url)
            output_path, actual_type = _render_certificate_file(
                registration,
                existing.certificate_code,
                existing.issued_at or datetime.utcnow(),
                requested_type,
            )
            existing.file_url = _public_url(output_path)
            existing.file_type = actual_type
            db.session.commit()
            if previous_path and previous_path != output_path and previous_path.exists():
                previous_path.unlink(missing_ok=True)
        return existing, False

    eligible, message, registration = validate_certificate_eligibility(ma_cbsv, event_id)
    if not eligible:
        raise CertificateError(message)

    issued_at = datetime.utcnow()
    certificate_code = _next_certificate_code(event_id)
    output_path, actual_type = _render_certificate_file(registration, certificate_code, issued_at, requested_type)

    certificate = Certificate(
        ma_cbsv=registration.ma_cbsv,
        event_id=event_id,
        certificate_code=certificate_code,
        file_url=_public_url(output_path),
        file_type=actual_type,
        status="generated",
        issued_at=issued_at,
        created_at=issued_at,
    )
    db.session.add(certificate)
    db.session.commit()
    return certificate, True


def get_certificate_file_path(certificate):
    return _stored_file_path(certificate.file_url)
