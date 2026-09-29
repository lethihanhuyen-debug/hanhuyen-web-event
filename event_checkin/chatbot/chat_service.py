"""Luồng xử lý 1 câu hỏi: intent -> query DB -> đóng session -> (Gemini) -> kết quả."""

import logging
import time

from event_checkin.chatbot import prompts
from event_checkin.chatbot.cache import InMemoryTTLCache
from event_checkin.chatbot.date_parser import normalize
from event_checkin.chatbot.event_search import search_events
from event_checkin.chatbot.intent_parser import (
    KIND_EVENTS, KIND_GREETING, KIND_INJECTION, KIND_OUT_OF_SCOPE, KIND_PERSONAL, parse_intent,
)
from event_checkin.chatbot.llm_provider import LLMError, LLMQuotaError, get_provider
from event_checkin.models import db
from event_checkin.utils.timezone import now_vn_naive

logger = logging.getLogger("chatbot")

MAX_MESSAGE_LEN = 300
MAX_HISTORY_TURNS = 4

_cache = InMemoryTTLCache(ttl_seconds=60)

_FIXED_REPLIES = {
    KIND_GREETING: prompts.GREETING,
    KIND_PERSONAL: prompts.PERSONAL,
    KIND_INJECTION: prompts.INJECTION,
    KIND_OUT_OF_SCOPE: prompts.OUT_OF_SCOPE,
}


def clean_history(raw_history):
    """Chỉ giữ tối đa MAX_HISTORY_TURNS tin gần nhất, đúng định dạng, cắt ngắn.
    Bỏ mọi thứ không phải {role: user|bot, text: str} -- history đến từ browser
    nên không tin cậy."""
    if not isinstance(raw_history, list):
        return []
    turns = []
    for item in raw_history[-MAX_HISTORY_TURNS:]:
        if not isinstance(item, dict) or not isinstance(item.get("text"), str):
            continue
        role = "user" if item.get("role") == "user" else "model" if item.get("role") in ("bot", "model", "assistant") else None
        text = item["text"].strip()[:MAX_MESSAGE_LEN]
        if role and text:
            turns.append({"role": role, "text": text})
    while turns and turns[0]["role"] != "user":  # Gemini yêu cầu bắt đầu bằng lượt user
        turns.pop(0)
    return turns


def _fallback_message(events):
    n = len(events)
    return f"Tôi tìm thấy {n} sự kiện phù hợp. Bạn xem chi tiết ở các thẻ bên dưới nhé."


def answer(message, history, url_builder):
    """Trả (dict kết quả, meta cho log). Không raise -- mọi lỗi LLM được xử lý
    tại đây."""
    started = time.monotonic()
    intent = parse_intent(message)

    if intent.kind == KIND_OUT_OF_SCOPE and history:
        # Câu hỏi nối tiếp không nhắc lại tên sự kiện (vd: "vậy quy mô bao nhiêu
        # người?" sau khi đã hỏi về 1 sự kiện) -- thử ghép với lượt hỏi gần nhất
        # của người dùng để suy ra lại chủ đề, thay vì từ chối luôn.
        last_user_text = next((t["text"] for t in reversed(history) if t["role"] == "user"), None)
        if last_user_text:
            combined_intent = parse_intent(f"{last_user_text} {message}")
            if combined_intent.kind == KIND_EVENTS:
                intent = combined_intent

    meta = {"intent": intent.kind, "events": 0, "llm": "skipped"}

    if intent.kind != KIND_EVENTS:
        return {"message": _FIXED_REPLIES[intent.kind], "events": []}, meta

    cache_key = None
    if not history:
        cache_key = (normalize(message), now_vn_naive().strftime("%Y-%m-%d %H"))
        cached = _cache.get(cache_key)
        if cached is not None:
            meta.update(events=len(cached["events"]), llm="cache")
            return cached, meta

    try:
        events = search_events(intent, url_builder)
    finally:
        db.session.remove()  # trả connection về pool TRƯỚC khi chờ Gemini

    meta["events"] = len(events)
    if not events:
        return {"message": prompts.NOT_FOUND, "events": []}, meta

    text = None
    provider = get_provider()
    if provider is not None:
        try:
            text = provider.generate(message, events, history)
            meta["llm"] = "ok"
        except LLMQuotaError:
            meta["llm"] = "quota"
            logger.warning("Gemini quota/rate limit reached")
        except LLMError as exc:
            meta["llm"] = "error"
            logger.warning("Gemini failed: %s", exc)
    else:
        meta["llm"] = "no_key"

    result = {"message": text or _fallback_message(events), "events": events}
    if cache_key and text:
        _cache.set(cache_key, result)
    meta["elapsed_ms"] = int((time.monotonic() - started) * 1000)
    return result, meta
