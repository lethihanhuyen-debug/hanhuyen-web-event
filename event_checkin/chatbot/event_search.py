"""Truy vấn sự kiện cho chatbot. CHỈ đọc, có limit, CHỈ lấy các cột công khai
trong whitelist -- không bao giờ đụng tới User/Registration/CheckIn/EmailLog,
certificate_template/layout, created_by/updated_by hay cột trang_thai thô."""

import re

from sqlalchemy import func
from sqlalchemy.orm import load_only

from event_checkin.chatbot.date_parser import normalize
from event_checkin.models import db
from event_checkin.models.event import Event
from event_checkin.models.registration import Registration
from event_checkin.utils.timezone import format_local, now_vn_naive

MAX_RESULTS = 6
_CANDIDATE_LIMIT = 300  # trần số dòng đọc khi phải lọc từ khoá không dấu bằng Python

_STATUS_TEXT = {"upcoming": "Sắp diễn ra", "ongoing": "Đang diễn ra", "ended": "Đã kết thúc"}

_PUBLIC_COLUMNS = (
    Event.id, Event.ten_su_kien, Event.mo_ta, Event.hinh, Event.dia_diem, Event.co_so,
    Event.so_luong_toi_da, Event.ngay_bat_dau, Event.ngay_ket_thuc,
    Event.thoi_gian_mo_dang_ky, Event.thoi_gian_dong_dang_ky, Event.certificate_enabled,
)


def _format_date(start, end):
    if start.date() == end.date():
        return format_local(start, "%d/%m/%Y")
    return f"{format_local(start, '%d/%m/%Y')} - {format_local(end, '%d/%m/%Y')}"


def _format_time(start, end):
    return f"{format_local(start, '%H:%M')} - {format_local(end, '%H:%M')}"


def _score(event, keywords):
    title = normalize(event.ten_su_kien)
    haystack = f"{title} {normalize(event.mo_ta or '')}"
    words = set(re.findall(r"[a-z0-9]+", haystack))
    title_words = set(re.findall(r"[a-z0-9]+", title))

    def hit(k, text, word_set):
        return k in word_set if len(k) <= 3 else k in text  # từ ngắn ("ai") phải khớp nguyên từ

    return sum((2 if hit(k, title, title_words) else 1) for k in keywords if hit(k, haystack, words))


def _registration_counts(event_ids):
    if not event_ids:
        return {}
    rows = (
        db.session.query(Registration.event_id, func.count(Registration.id))
        .filter(Registration.event_id.in_(event_ids))
        .group_by(Registration.event_id)
        .all()
    )
    return dict(rows)


def search_events(intent, url_builder):
    """Trả về list dict thuần (whitelist) -- đã tách khỏi SQLAlchemy session để
    caller đóng session trước khi gọi LLM. `url_builder(event_id)` trả link
    trang sự kiện."""
    now = now_vn_naive()
    query = Event.query.options(load_only(*_PUBLIC_COLUMNS))

    if intent.co_so:
        query = query.filter(Event.co_so == intent.co_so)

    if intent.date_range:
        start, end = intent.date_range
        query = query.filter(Event.ngay_bat_dau < end, Event.ngay_ket_thuc >= start)
    elif not intent.keywords:
        query = query.filter(Event.ngay_ket_thuc >= now)  # không nêu ngày/tên: chỉ sự kiện còn liên quan

    if intent.open_only:
        query = query.filter(
            Event.ngay_ket_thuc >= now,
            Event.thoi_gian_mo_dang_ky <= now,
            Event.thoi_gian_dong_dang_ky >= now,
        )

    if intent.keywords:
        events = query.order_by(Event.ngay_bat_dau.desc()).limit(_CANDIDATE_LIMIT).all()
        scored = [(_score(e, intent.keywords), e) for e in events]
        scored = [(s, e) for s, e in scored if s > 0]
        scored.sort(key=lambda p: (-p[0], p[1].ngay_bat_dau))
        events = [e for _, e in scored[:MAX_RESULTS * 2]]
    else:
        events = query.order_by(Event.ngay_bat_dau.asc()).limit(MAX_RESULTS * 2).all()

    counts = _registration_counts([e.id for e in events])
    results = []
    for event in events:
        can_register = event.is_registration_open  # dùng đúng logic của website
        if intent.open_only and not can_register:
            continue
        registered = counts.get(event.id, 0)
        capacity_text = (
            f"{registered}/{event.so_luong_toi_da} đã đăng ký" if event.so_luong_toi_da else f"{registered} đã đăng ký (không giới hạn)"
        )
        location = ", ".join(p for p in (event.dia_diem, event.co_so) if p)
        results.append({
            "id": event.id,
            "title": event.ten_su_kien,
            "description": (event.mo_ta or "")[:300],
            "date": _format_date(event.ngay_bat_dau, event.ngay_ket_thuc),
            "time": _format_time(event.ngay_bat_dau, event.ngay_ket_thuc),
            "location": location,
            "registration_window": (
                f"{format_local(event.thoi_gian_mo_dang_ky)} - {format_local(event.thoi_gian_dong_dang_ky)}"
            ),
            "status": _STATUS_TEXT[event.computed_status],
            "can_register": bool(can_register),
            "has_certificate": bool(event.certificate_enabled),
            "capacity_text": capacity_text,
            "image_url": event.hinh or None,
            "url": url_builder(event.id),
        })
        if len(results) >= MAX_RESULTS:
            break
    return results
