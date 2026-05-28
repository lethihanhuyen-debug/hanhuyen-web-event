import logging
from pathlib import Path

from flask import current_app
from flask_mail import Message

from event_checkin.extensions import mail


logger = logging.getLogger(__name__)


def _mime_type_for(path):
    suffix = Path(path).suffix.lower()
    if suffix == ".png":
        return "image/png"
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".svg":
        return "image/svg+xml"
    if suffix == ".pdf":
        return "application/pdf"
    return "application/octet-stream"


def send_checkin_email(
    ho_ten,
    email,
    thoi_gian,
    certificate_path=None,
    certificate_code=None,
    verify_url=None,
):
    if not email:
        logger.warning("Bo qua gui email vi nguoi dung khong co dia chi email.")
        return False

    config = current_app.config
    if not config.get("MAIL_USERNAME") or not config.get("MAIL_PASSWORD"):
        logger.warning("Thieu cau hinh SMTP nen khong the gui email.")
        return False

    sender = config.get("MAIL_SENDER") or config.get("MAIL_USERNAME")
    formatted_time = thoi_gian.strftime("%H:%M ngay %d/%m/%Y")

    certificate_text = ""
    certificate_html = ""
    if certificate_code:
        certificate_text = (
            f"\nMa chung nhan: {certificate_code}"
            + (f"\nXac minh: {verify_url}" if verify_url else "")
            + "\nHinh chung nhan duoc dinh kem trong email nay.\n"
        )
        certificate_html = (
            f"<p><b>Ma chung nhan:</b> {certificate_code}</p>"
            + (f'<p><a href="{verify_url}">Xac minh chung nhan</a></p>' if verify_url else "")
            + "<p>Hinh chung nhan duoc dinh kem trong email nay.</p>"
        )

    text_body = (
        f"Cam on {ho_ten} da tham gia su kien hom nay vao luc {formatted_time}.\n"
        "Ban duoc cong 2 diem ren luyen.\n"
        f"{certificate_text}\n"
        "Tran trong."
    )
    html_body = (
        f"<p>Cam on <b>{ho_ten}</b> da tham gia su kien hom nay vao luc <b>{formatted_time}</b>.</p>"
        "<p>Ban duoc cong <b>2 diem ren luyen</b>.</p>"
        f"{certificate_html}"
        "<p>Tran trong.</p>"
    )

    try:
        logger.info(f"Gui email: {sender} -> {email}")
        message = Message(
            subject="Xac nhan tham gia su kien",
            sender=sender,
            recipients=[email],
            body=text_body,
            html=html_body,
        )
        if certificate_path:
            path = Path(certificate_path)
            if path.exists():
                message.attach(path.name, _mime_type_for(path), path.read_bytes())
            else:
                logger.warning(f"Khong tim thay file chung nhan de dinh kem: {path}")
        mail.send(message)
        logger.info(f"Email gui thanh cong toi {email}")
        return True
    except Exception as error:
        logger.error(f"Gui email that bai toi {email}: {error}")
        return False
