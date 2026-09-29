"""Lớp trừu tượng LLM + Gemini. Muốn đổi provider (Groq/OpenRouter...): thêm 1
class con của LLMProvider và sửa `get_provider()`."""

import json
import logging
import os
from abc import ABC, abstractmethod

from event_checkin.chatbot.prompts import SYSTEM_PROMPT
from event_checkin.utils.timezone import now_vn_naive

logger = logging.getLogger("chatbot")

# Chỉ các trường này được gửi cho LLM -- không có url/image_url (LLM không được
# tự tạo/lặp lại link) và không có id nội bộ.
_LLM_FIELDS = (
    "title", "description", "date", "time", "location", "registration_window",
    "status", "can_register", "has_certificate", "capacity_text",
)


class LLMError(Exception):
    pass


class LLMQuotaError(LLMError):
    pass


class LLMProvider(ABC):
    @abstractmethod
    def generate(self, question, events, history):
        """Trả về câu trả lời (str). Raise LLMError/LLMQuotaError khi lỗi."""


def build_user_prompt(question, events):
    compact = [{k: e[k] for k in _LLM_FIELDS} for e in events]
    data = json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
    now = now_vn_naive()
    weekday = ("Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật")[now.weekday()]
    today = f"Hôm nay là {weekday}, {now.strftime('%d/%m/%Y')} (giờ Việt Nam)."
    return (
        f"{today} Các sự kiện trong <EVENT_DATA> đã được hệ thống lọc sẵn theo câu hỏi.\n"
        f"<EVENT_DATA>\n{data}\n</EVENT_DATA>\n\nCâu hỏi của người dùng: {question}"
    )


class GeminiProvider(LLMProvider):
    def __init__(self, api_key, model, timeout_seconds=12):
        from google import genai
        from google.genai import types

        self._types = types
        self._model = model
        client_args = {}
        try:
            # Dùng kho chứng chỉ của hệ điều hành (chỉ cho kết nối Gemini): trên Windows
            # có antivirus/proxy chặn HTTPS thì certifi mặc định của Python sẽ lỗi
            # CERTIFICATE_VERIFY_FAILED.
            import ssl

            import truststore

            client_args["verify"] = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        except ImportError:
            pass
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=int(timeout_seconds * 1000),
                client_args=client_args or None,
                retry_options=types.HttpRetryOptions(attempts=1),  # không retry dồn dập khi lỗi/429
            ),
        )

    def generate(self, question, events, history):
        from google.genai import errors

        types = self._types
        contents = [
            types.Content(role=turn["role"], parts=[types.Part(text=turn["text"])]) for turn in history
        ]
        contents.append(types.Content(role="user", parts=[types.Part(text=build_user_prompt(question, events))]))
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    temperature=0.2,
                    max_output_tokens=500,
                ),
            )
        except errors.APIError as exc:
            if getattr(exc, "code", None) == 429:
                raise LLMQuotaError("Gemini quota/rate limit") from exc
            raise LLMError(f"Gemini API error {getattr(exc, 'code', '?')}") from exc
        except Exception as exc:  # timeout, lỗi mạng...
            raise LLMError(f"Gemini call failed: {type(exc).__name__}") from exc

        text = (response.text or "").strip()
        if not text:
            raise LLMError("Gemini returned empty text")
        return text


_provider = None
_provider_key = None


def get_provider():
    """Trả về provider, hoặc None nếu chưa cấu hình GEMINI_API_KEY (khi đó chat
    service trả lời bằng bản tóm tắt dựng sẵn, không dùng LLM)."""
    global _provider, _provider_key
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None
    model = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite").strip()
    cache_key = (api_key, model)
    if _provider is None or _provider_key != cache_key:
        timeout = float(os.getenv("GEMINI_TIMEOUT_SECONDS", "12"))
        _provider = GeminiProvider(api_key, model, timeout)
        _provider_key = cache_key
    return _provider
