"""Tiện ích mật khẩu / token. Chỉ dùng thư viện chuẩn + werkzeug, không phụ thuộc Flask hay DB."""
import hashlib
import secrets
import string

PASSWORD_MIN_LENGTH = 8

PASSWORD_RULE_TEXT = "Mật khẩu tối thiểu 8 ký tự, gồm cả chữ và số."


def password_error(password):
    """None nếu mật khẩu đạt yêu cầu, ngược lại là câu báo lỗi tiếng Việt."""
    password = password or ""
    if len(password) < PASSWORD_MIN_LENGTH or not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        return PASSWORD_RULE_TEXT
    return None


def generate_temp_password():
    """Mật khẩu tạm ngẫu nhiên 10-12 ký tự, luôn có chữ hoa, chữ thường và số; bỏ ký tự dễ nhầm (l, I, O, 0, 1)
    vì super_admin sẽ đọc/chép lại cho người dùng."""
    upper = "".join(c for c in string.ascii_uppercase if c not in "IO")
    lower = "".join(c for c in string.ascii_lowercase if c != "l")
    digits = "".join(c for c in string.digits if c not in "01")
    length = 10 + secrets.randbelow(3)
    chars = [secrets.choice(upper), secrets.choice(lower), secrets.choice(digits)]
    chars += [secrets.choice(upper + lower + digits) for _ in range(length - 3)]
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def new_reset_token():
    """Token ngẫu nhiên gửi trong link email (chỉ người nhận email biết)."""
    return secrets.token_urlsafe(32)


def hash_token(token):
    """Băm sha256 của token -- chỉ lưu băm trong DB, không lưu token gốc."""
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def hash_email_key(email):
    """Khóa ẩn danh theo email (cho giới hạn số lần quên mật khẩu), không lưu email gốc vào nhật ký."""
    return hashlib.sha256((email or "").strip().lower().encode("utf-8")).hexdigest()[:32]
