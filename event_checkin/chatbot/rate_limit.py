import os

from flask import request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


def client_ip():
    """Sau IIS/ARR, remote_addr luôn là 127.0.0.1 nên mọi người dùng sẽ chung 1
    hạn mức. Bật CHATBOT_TRUST_PROXY=true để lấy IP thật từ X-Forwarded-For --
    lấy phần tử CUỐI (do ARR thêm vào), vì các phần tử đầu client có thể tự giả."""
    if os.getenv("CHATBOT_TRUST_PROXY", "false").lower() == "true":
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[-1].strip()
    return get_remote_address()


limiter = Limiter(key_func=client_ip, storage_uri="memory://", default_limits=[])

CHAT_LIMITS = os.getenv("CHATBOT_RATE_LIMIT", "8 per minute;100 per hour")
