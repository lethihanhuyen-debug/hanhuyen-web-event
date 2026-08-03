import logging
from pathlib import Path

from flask import current_app
from flask_mail import Message

from event_checkin.extensions import mail
from event_checkin.utils.timezone import format_utc_as_vn


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
    ten_su_kien=None,
    certificate_path=None,
    certificate_code=None,
    verify_url=None,
    return_error=False,
):
    if not email:
        error = "Người dùng không có địa chỉ email."
        logger.warning(f"Bỏ qua gửi email vì {error}")
        return (False, error) if return_error else False

    config = current_app.config
    if not config.get("MAIL_USERNAME") or not config.get("MAIL_PASSWORD"):
        error = "Thiếu cấu hình SMTP."
        logger.warning(f"{error} Không thể gửi email.")
        return (False, error) if return_error else False

    sender = config.get("MAIL_SENDER") or config.get("MAIL_USERNAME")
    # thoi_gian is the check-in timestamp, stored via datetime.utcnow() -- convert to
    # Vietnam local time before formatting, or the email shows the UTC hour instead.
    formatted_time = format_utc_as_vn(thoi_gian, "%H:%M ngay %d/%m/%Y")
    # Quoted event name for the opening line; falls back to no event name (rather than a
    # dangling pair of quotes) if the caller couldn't resolve one.
    su_kien_text = f' "{ten_su_kien}"' if ten_su_kien else ""
    su_kien_html = f' "<b>{ten_su_kien}</b>"' if ten_su_kien else ""

    certificate_text = ""
    certificate_html = ""
    if certificate_code:
        certificate_text = (
            f"\nMã chứng nhận: {certificate_code}"
            + (f"\nXác minh: {verify_url}" if verify_url else "")
            + "\nFile chứng nhận được đính kèm trong email này.\n"
        )
        certificate_html = (
            f"<p><b>Mã chứng nhận:</b> {certificate_code}</p>"
            + (f'<p><a href="{verify_url}">Xác minh chứng nhận</a></p>' if verify_url else "")
            + "<p>File chứng nhận được đính kèm trong email này.</p>"
        )

    text_body = (
        f"Cảm ơn {ho_ten} đã tham gia sự kiện{su_kien_text} vào lúc {formatted_time}.\n"
        "Bạn được cộng 2 điểm rèn luyện.\n"
        f"{certificate_text}\n"
        "Trân trọng."
    )
    html_body = (
        f"<p>Cảm ơn <b>{ho_ten}</b> đã tham gia sự kiện{su_kien_html} vào lúc <b>{formatted_time}</b>.</p>"
        "<p>Bạn được cộng <b>2 điểm rèn luyện</b>.</p>"
        f"{certificate_html}"
        "<p>Trân trọng.</p>"
    )

    try:
        logger.info(f"Gửi email: {sender} -> {email}")
        message = Message(
            subject="Xác nhận tham gia sự kiện",
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
                logger.warning(f"Không tìm thấy file chứng nhận để đính kèm: {path}")
        mail.send(message)
        logger.info(f"Email gửi thành công tới {email}")
        return (True, None) if return_error else True
    except Exception as error:
        logger.error(f"Gửi email thất bại tới {email}: {error}")
        return (False, str(error)) if return_error else False
