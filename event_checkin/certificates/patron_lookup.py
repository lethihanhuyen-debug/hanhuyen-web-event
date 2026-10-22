"""Tra cứu họ tên + email của người nhận chứng chỉ theo mã SV/CB (patron_code).

Đây là chỗ DUY NHẤT cần sửa khi tích hợp Sierra ILS: lô gửi chứng chỉ
(certificates/mailer.py) và tên in trên chứng chỉ (service.resolve_display_name)
đều đi qua lookup_patron().

HIỆN TẠI (chưa có Sierra): lấy theo dữ liệu đăng ký trên web (bảng users).

KHI TÍCH HỢP SIERRA, lookup_patron() cần:
- Gọi Sierra REST API tìm bạn đọc theo patron_code, lấy họ tên + email.
- Không tìm thấy mã -> raise PatronNotFound (lô gửi đánh 'failed' với lý do rõ ràng).
- Token hết hạn (HTTP 401) -> tự lấy token mới rồi gọi lại 1 lần, KHÔNG được ném
  PatronNotFound trong trường hợp này (spec: không đánh lỗi người đó).
- Lỗi mạng/Sierra tạm thời -> raise PatronLookupError kèm lý do.
"""
from dataclasses import dataclass

from event_checkin.models.user import User


class PatronNotFound(Exception):
    pass


class PatronLookupError(Exception):
    pass


@dataclass
class PatronInfo:
    name: str
    email: str


def lookup_patron(patron_code):
    user = User.query.get(patron_code)
    if not user:
        raise PatronNotFound(f"Không tìm thấy mã {patron_code} trong dữ liệu đăng ký.")
    return PatronInfo(name=(user.ho_ten or "").strip(), email=(user.email or "").strip())
