import logging
import time
import uuid

from flask import Blueprint, jsonify, request, url_for
from flask_limiter.errors import RateLimitExceeded

from event_checkin.chatbot import chat_service, prompts
from event_checkin.chatbot.rate_limit import CHAT_LIMITS, limiter

chat_bp = Blueprint("chat", __name__)
logger = logging.getLogger("chatbot")

MAX_BODY_BYTES = 8 * 1024

# Chỉ các trường này được trả về browser (whitelist -- xem event_search.py).
_PUBLIC_EVENT_FIELDS = ("id", "title", "date", "time", "location", "status", "can_register", "url")


def _error(status, message, request_id):
    return jsonify({"success": False, "message": message, "requestId": request_id}), status


@chat_bp.errorhandler(RateLimitExceeded)
def _rate_limited(_exc):
    return _error(429, prompts.RATE_LIMITED, uuid.uuid4().hex[:12])


@chat_bp.post("/api/chat")
@limiter.limit(CHAT_LIMITS)
def chat():
    request_id = uuid.uuid4().hex[:12]
    started = time.monotonic()

    if request.content_length and request.content_length > MAX_BODY_BYTES:
        return _error(413, "Tin nhắn quá dài.", request_id)

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _error(400, "Yêu cầu không hợp lệ.", request_id)

    message = payload.get("message")
    if not isinstance(message, str) or not message.strip():
        return _error(400, "Vui lòng nhập câu hỏi.", request_id)
    message = message.strip()
    if len(message) > chat_service.MAX_MESSAGE_LEN:
        return _error(400, f"Câu hỏi tối đa {chat_service.MAX_MESSAGE_LEN} ký tự.", request_id)

    history = chat_service.clean_history(payload.get("history"))

    try:
        result, meta = chat_service.answer(
            message, history, lambda event_id: url_for("register.event_register", event_id=event_id)
        )
    except Exception:
        logger.exception("chat failed request_id=%s", request_id)
        return _error(500, prompts.ERROR, request_id)

    logger.info(
        "chat request_id=%s ip_intent=%s events=%s llm=%s ms=%d q=%r",
        request_id, meta["intent"], meta["events"], meta["llm"],
        int((time.monotonic() - started) * 1000), message[:60],
    )
    return jsonify({
        "success": True,
        "message": result["message"],
        "events": [{k: e[k] for k in _PUBLIC_EVENT_FIELDS} for e in result["events"]],
        "requestId": request_id,
    })
