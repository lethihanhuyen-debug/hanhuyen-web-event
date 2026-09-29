"""Phân loại ý định câu hỏi bằng rule-based (không gọi LLM). Thuần Python, dễ
unit test: chỉ phụ thuộc date_parser (và qua đó là now_vn_naive)."""

import re
from dataclasses import dataclass, field

from event_checkin.chatbot.date_parser import normalize, parse_date_range

KIND_EVENTS = "events"
KIND_PERSONAL = "personal"
KIND_INJECTION = "injection"
KIND_GREETING = "greeting"
KIND_OUT_OF_SCOPE = "out_of_scope"

CO_SO_MAP = {"linh xuan": "Linh Xuân", "sai gon": "Sài Gòn"}

_INJECTION_PHRASES = (
    "bo qua moi", "bo qua cac", "bo qua quy tac", "bo qua huong dan", "ignore previous",
    "ignore all", "system prompt", "prompt he thong", "api key", "apikey", "gemini_api",
    "in ra prompt", "tiet lo prompt", "developer mode", "jailbreak", "dong vai",
)

_PERSONAL_PATTERNS = (
    r"\btoi da (dang ky|check ?in|diem danh)",
    r"\b(minh|em) da (dang ky|check ?in|diem danh)",
    r"\bda (dang ky|check ?in|diem danh) chua",
    r"(danh sach|ds) (nguoi |sinh vien |can bo )?(dang ky|check ?in|tham du|diem danh)",
    r"\b(chung nhan|chung chi|giay chung nhan) cua (toi|minh|em)",
    r"\btai (chung nhan|chung chi)",
    r"\b(so dien thoai|sdt|email|ma sinh vien|ma can bo|mssv)\b",
    r"\bthong tin (cua )?(toi|minh|em|nguoi dang ky)",
)

_EVENT_WORDS = (
    "su kien", "hoat dong", "hoi thao", "workshop", "tap huan", "toa dam", "hoi nghi",
    "chuong trinh", "khoa hoc", "lich", "dang ky", "chung nhan", "chung chi", "check in",
    "checkin", "dia diem", "o dau", "may gio", "khi nao", "co so", "tham gia", "tham du",
    "mien phi", "le phi", "phi tham", "event", "co gi", "co nhung gi", "co chuong",
)

_GREETING_RE = re.compile(r"^(xin )?(chao|hello|hi|hey|alo)\b[^a-z0-9]*(ban|bot|ad|admin|chatbot)?[^a-z0-9]*$")

_STOPWORDS = frozenset("""
co khong nao gi la the nay cac nhung nhu va o tai cho toi minh ban cua mot hay xem biet tim
hom mai qua tuan thang sau truoc ngay dang mo dau gio may khi su kien hoat dong dien ra
to chuc duoc voi de hoi ve thi sap se den tu trong nam nhi a oi nha vay chi nhieu bao
lich chuong trinh dang ky check in checkin chung nhan chung chi dia diem co so tham gia tham du
phi cap phat lam sao the nao bao nhieu muon can em anh chi thay nhung con hien nay
""".split())

_SHORT_KEEP = frozenset({"ai"})  # "AI" là từ khoá chủ đề hợp lệ dù chỉ 2 ký tự


@dataclass
class Intent:
    kind: str
    date_range: tuple = None
    co_so: str = None
    open_only: bool = False
    keywords: list = field(default_factory=list)


def _has_event_word(text):
    padded = f" {text} "
    return any(f" {w} " in padded or w in text for w in _EVENT_WORDS)


def parse_intent(message):
    text = normalize(message)
    text = re.sub(r"\s+", " ", text.replace("-", " "))

    if any(p in text for p in _INJECTION_PHRASES):
        return Intent(KIND_INJECTION)

    if any(re.search(p, text) for p in _PERSONAL_PATTERNS):
        return Intent(KIND_PERSONAL)

    if _GREETING_RE.match(text):
        return Intent(KIND_GREETING)

    date_range = parse_date_range(message)

    co_so = None
    for phrase, name in CO_SO_MAP.items():
        if phrase in text:
            co_so = name
            text_wo_coso = text.replace(phrase, " ")
            break
    else:
        text_wo_coso = text

    open_only = bool(re.search(r"\b(dang )?mo dang ky\b", text)) or "con cho" in text or "dang ky duoc" in text

    if not (_has_event_word(text) or co_so):
        return Intent(KIND_OUT_OF_SCOPE)

    tokens = re.findall(r"[a-z0-9]+", text_wo_coso)
    keywords = []
    for tok in tokens:
        if tok in _STOPWORDS or any(ch.isdigit() for ch in tok):
            continue
        if len(tok) < 3 and tok not in _SHORT_KEEP:
            continue
        if tok not in keywords:
            keywords.append(tok)

    return Intent(KIND_EVENTS, date_range=date_range, co_so=co_so, open_only=open_only, keywords=keywords[:6])
