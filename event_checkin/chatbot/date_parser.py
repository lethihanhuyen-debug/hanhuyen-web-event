"""Nhận diện cụm ngày/tháng trong câu hỏi tiếng Việt (có dấu hoặc không dấu),
thuần rule-based -- không gọi LLM, để tiết kiệm token và phản hồi tức thì.

Mọi so sánh đều dựa trên `now_vn_naive()` (giờ VN, naive) vì lịch trình sự
kiện (ngay_bat_dau, ngay_ket_thuc...) được lưu thẳng dạng naive-VN, không
phải UTC -- xem event_checkin/utils/timezone.py.
"""

import re
import unicodedata
from datetime import timedelta

from event_checkin.utils.timezone import now_vn_naive


def strip_accents(text):
    """Bỏ dấu tiếng Việt để so khớp không phân biệt dấu/hoa-thường. NFD tách
    được hầu hết dấu thanh/dấu phụ, riêng đ/Đ phải thay tay vì Unicode không
    coi đó là "a + dấu phụ" mà là 1 ký tự độc lập."""
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return text.replace("đ", "d").replace("Đ", "D")


def normalize(text):
    return strip_accents(text or "").lower().strip()


def _day_range(day_start):
    return day_start, day_start + timedelta(days=1)


def _month_range(year, month):
    start = _first_of_month(year, month)
    end = _first_of_month(year + 1, 1) if month == 12 else _first_of_month(year, month + 1)
    return start, end


def _first_of_month(year, month):
    return now_vn_naive().replace(year=year, month=month, day=1, hour=0, minute=0, second=0, microsecond=0)


def parse_date_range(message):
    """Trả về (start, end) -- end không bao gồm (exclusive), theo giờ VN naive
    -- hoặc None nếu không nhận diện được cụm ngày/tháng nào trong câu hỏi."""
    text = normalize(message)
    now = now_vn_naive()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if "hom nay" in text:
        return _day_range(today)
    if "ngay mai" in text:
        return _day_range(today + timedelta(days=1))
    if "hom qua" in text:
        return _day_range(today - timedelta(days=1))

    if re.search(r"\btuan\b", text):
        monday = today - timedelta(days=today.weekday())
        if "sau" in text or "toi" in text:
            monday += timedelta(days=7)
        return monday, monday + timedelta(days=7)

    # ngày dd/mm hoặc dd/mm/yyyy -- ưu tiên trước "tháng M" vì cụ thể hơn
    match = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", text)
    if match:
        day, month = int(match.group(1)), int(match.group(2))
        year = int(match.group(3)) if match.group(3) else today.year
        if year < 100:
            year += 2000
        if 1 <= month <= 12:
            try:
                day_start = today.replace(year=year, month=month, day=day)
                return _day_range(day_start)
            except ValueError:
                pass  # ngày không hợp lệ (vd 31/2) -- bỏ qua, coi như không nhận diện được

    if "thang nay" in text:
        return _month_range(today.year, today.month)

    if "thang sau" in text or "thang toi" in text:
        if today.month == 12:
            return _month_range(today.year + 1, 1)
        return _month_range(today.year, today.month + 1)

    match = re.search(r"\bthang\s+(\d{1,2})\b", text)
    if match:
        month = int(match.group(1))
        if 1 <= month <= 12:
            return _month_range(today.year, month)

    return None
