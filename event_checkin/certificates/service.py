from datetime import datetime
import json
from pathlib import Path

from flask import current_app, url_for

from event_checkin.certificates.generator import (
    save_pdf_certificate,
    save_png_certificate,
    save_svg_certificate,
)
from event_checkin.certificates.validators import validate_certificate_eligibility
from event_checkin.models import db
from event_checkin.models.certificate import Certificate


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


def _render_certificate_file(registration, certificate_code, issued_at, requested_type):
    user = registration.user
    event = registration.event
    student_name = user.ho_ten if user else registration.ma_cbsv
    student_unit = user.ten_don_vi if user else ""
    template_path = None
    layout = None
    if event and event.certificate_enabled and event.certificate_template:
        template_path = Path(current_app.static_folder) / event.certificate_template
        if event.certificate_layout:
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
