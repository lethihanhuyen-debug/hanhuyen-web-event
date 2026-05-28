from datetime import datetime
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


def _next_certificate_code(event_id):
    year = datetime.utcnow().year
    count = Certificate.query.filter_by(event_id=event_id).count() + 1
    return f"USSH-{year}-EVENT{event_id:03d}-{count:06d}"


def _render_certificate_file(registration, certificate_code, issued_at, requested_type):
    year_dir = _storage_root() / str(issued_at.year)
    if requested_type == "pdf":
        output_path = year_dir / f"{certificate_code}.pdf"
        save_pdf_certificate(output_path, registration.ho_ten, registration.ma_cbsv, registration.don_vi, certificate_code, issued_at)
        return output_path, "pdf"

    output_path = year_dir / f"{certificate_code}.png"
    rendered_path = save_png_certificate(
        output_path,
        registration.ho_ten,
        registration.ma_cbsv,
        registration.don_vi,
        certificate_code,
        issued_at,
    )
    if rendered_path is None:
        output_path = year_dir / f"{certificate_code}.svg"
        save_svg_certificate(output_path, registration.ho_ten, registration.ma_cbsv, registration.don_vi, certificate_code, issued_at)
        return output_path, "svg"
    return output_path, "png"


def generate_certificate(ma_cbsv, event_id=DEFAULT_EVENT_ID, file_type="png"):
    event_id = int(event_id or DEFAULT_EVENT_ID)
    requested_type = (file_type or "png").lower()

    existing = Certificate.query.filter_by(ma_cbsv=ma_cbsv, event_id=event_id).first()
    if existing:
        eligible, _, registration = validate_certificate_eligibility(ma_cbsv)
        if eligible:
            output_path, actual_type = _render_certificate_file(
                registration,
                existing.certificate_code,
                existing.issued_at or datetime.utcnow(),
                requested_type,
            )
            existing.file_url = _public_url(output_path)
            existing.file_type = actual_type
            db.session.commit()
        return existing, False

    eligible, message, registration = validate_certificate_eligibility(ma_cbsv)
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
    if not certificate.file_url:
        return None
    prefix = url_for("static", filename="", _external=False)
    relative = certificate.file_url
    if relative.startswith(prefix):
        relative = relative[len(prefix):]
    return Path(current_app.static_folder) / relative
