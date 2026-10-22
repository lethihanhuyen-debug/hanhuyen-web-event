import logging
import smtplib
import socket
import ssl
from pathlib import Path

from flask import current_app
from flask_mail import Message

from event_checkin.extensions import mail
from event_checkin.utils.timezone import format_local


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


def describe_mail_error(error, email=None):
    """Đổi lỗi kỹ thuật của SMTP thành câu tiếng Việt dễ hiểu cho admin (người không
    phải lập trình viên): nói rõ chuyện gì xảy ra và cần làm gì. Chi tiết kỹ thuật
    vẫn được ghi ở file log, không hiện cho admin."""
    config = current_app.config
    host = config.get("MAIL_SERVER") or "(chưa đặt)"

    if isinstance(error, smtplib.SMTPAuthenticationError):
        return (
            "Đăng nhập tài khoản gửi thư thất bại: sai email hoặc mật khẩu. "
            "Với Gmail phải dùng \"Mật khẩu ứng dụng\" 16 ký tự, không dùng mật khẩu đăng nhập thường. "
            "Hãy nhờ người quản trị kỹ thuật kiểm tra MAIL_USERNAME và MAIL_PASSWORD."
        )
    if isinstance(error, socket.gaierror):
        return (
            f"Không tìm thấy máy chủ gửi thư \"{host}\" (tên máy chủ sai hoặc máy chủ web đang không có mạng). "
            "Hãy nhờ người quản trị kỹ thuật kiểm tra MAIL_SERVER, ví dụ smtp.gmail.com."
        )
    if isinstance(error, UnicodeError):
        return (
            "Email hoặc mật khẩu gửi thư trong file .env có ký tự có dấu hoặc không hợp lệ "
            "(thường do còn chữ mẫu chưa thay bằng email thật). Hãy nhờ người quản trị kỹ thuật "
            "kiểm tra MAIL_USERNAME và MAIL_PASSWORD, chỉ dùng chữ không dấu."
        )
    if isinstance(error, (socket.timeout, TimeoutError)):
        return (
            f"Máy chủ gửi thư \"{host}\" không phản hồi (hết thời gian chờ). "
            "Có thể mạng chậm hoặc cổng gửi thư bị chặn. Hãy thử gửi lại sau ít phút."
        )
    if isinstance(error, (ConnectionRefusedError, ConnectionResetError)):
        return (
            f"Máy chủ gửi thư \"{host}\" từ chối kết nối. "
            "Hãy nhờ người quản trị kỹ thuật kiểm tra MAIL_PORT và tường lửa."
        )
    if isinstance(error, (ssl.SSLError, smtplib.SMTPNotSupportedError)):
        return (
            "Không thiết lập được kết nối bảo mật với máy chủ gửi thư. "
            "Hãy nhờ người quản trị kỹ thuật kiểm tra MAIL_PORT, MAIL_USE_TLS, MAIL_USE_SSL "
            "(thường là cổng 587 với TLS bật)."
        )
    if isinstance(error, smtplib.SMTPServerDisconnected):
        return "Máy chủ gửi thư ngắt kết nối giữa chừng. Hãy thử gửi lại sau ít phút."
    if isinstance(error, smtplib.SMTPRecipientsRefused):
        return f"Máy chủ từ chối địa chỉ nhận{(' ' + email) if email else ''}. Hãy kiểm tra email có đúng và còn dùng được không."
    if isinstance(error, smtplib.SMTPSenderRefused):
        return "Máy chủ không cho phép gửi từ địa chỉ này. Hãy nhờ người quản trị kỹ thuật kiểm tra MAIL_SENDER."
    if isinstance(error, smtplib.SMTPResponseException):
        detail = (error.smtp_error.decode("utf-8", "replace") if isinstance(error.smtp_error, bytes) else str(error.smtp_error)).lower()
        if any(word in detail for word in ("limit", "quota", "too many", "rate")) or error.smtp_code in (421, 450, 451, 452, 454):
            return (
                "Đã gửi quá nhiều thư trong thời gian ngắn hoặc vượt giới hạn gửi trong ngày. "
                "Hãy chờ vài giờ (hoặc sang ngày hôm sau) rồi bấm Gửi lại."
            )
        return f"Máy chủ gửi thư từ chối thư này (mã {error.smtp_code}). Hãy thử gửi lại, nếu vẫn lỗi hãy báo người quản trị kỹ thuật."
    if isinstance(error, OSError):
        return (
            "Không kết nối được tới máy chủ gửi thư. "
            "Hãy kiểm tra máy chủ web có đang kết nối mạng không, rồi thử gửi lại."
        )
    return "Không gửi được email vì một lỗi chưa xác định. Hãy thử gửi lại, nếu vẫn lỗi hãy báo người quản trị kỹ thuật."


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
        error = (
            "Chưa cài đặt tài khoản gửi thư (thiếu MAIL_USERNAME hoặc MAIL_PASSWORD trong file .env). "
            "Hãy nhờ người quản trị kỹ thuật điền rồi khởi động lại web."
        )
        logger.warning("Thiếu cấu hình SMTP. Không thể gửi email.")
        return (False, error) if return_error else False

    sender = config.get("MAIL_SENDER") or config.get("MAIL_USERNAME")
    # thoi_gian là checkin_records.checkin_at -- đã lưu sẵn giờ Việt Nam (UTC+7),
    # nên chỉ định dạng, KHÔNG đổi múi giờ (đổi thêm lần nữa sẽ lệch +7 tiếng).
    formatted_time = format_local(thoi_gian, "%d/%m/%Y %H:%M")
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
        logger.error(f"Gửi email thất bại tới {email}: {type(error).__name__}: {error}")
        friendly = describe_mail_error(error, email)
        return (False, friendly) if return_error else False
