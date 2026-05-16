import logging

from flask import current_app
from flask_mail import Message

from event_checkin.extensions import mail


logger = logging.getLogger(__name__)


def send_checkin_email(ho_ten, email, thoi_gian):
    if not email:
        logger.warning("Bỏ qua gửi email vì người dùng không có địa chỉ email.")
        return False

    config = current_app.config
    if not config.get("MAIL_USERNAME") or not config.get("MAIL_PASSWORD"):
        logger.warning("Thiếu cấu hình SMTP nên không thể gửi email.")
        return False

    sender = config.get("MAIL_SENDER") or config.get("MAIL_USERNAME")

    formatted_time = thoi_gian.strftime("%H:%M ngày %d/%m/%Y")
    text_body = (
        f"Cảm ơn {ho_ten} đã tham gia sự kiện hôm nay vào lúc {formatted_time}.\n"
        "Bạn được cộng 2 điểm rèn luyện.\n\n"
        "Trân trọng."
    )
    html_body = (
        f"<p>Cảm ơn <b>{ho_ten}</b> đã tham gia sự kiện hôm nay vào lúc <b>{formatted_time}</b>.</p>"
        "<p>Bạn được cộng <b>2 điểm rèn luyện</b>.</p>"
        "<p>Trân trọng.</p>"
    )

    try:
        logger.info(f"📧 Gửi email: {sender} -> {email}")
        message = Message(
            subject="Xác nhận tham gia sự kiện",
            sender=sender,
            recipients=[email],
            body=text_body,
            html=html_body,
        )
        mail.send(message)
        logger.info(f"✅ Email gửi thành công tới {email}")
        return True
    except Exception as error:
        logger.error(f"❌ Gửi email thất bại tới {email}: {error}")
        return False
