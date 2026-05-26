import re
from typing import Optional

# Tên thật: chỉ chữ cái (gồm dấu Latin mở rộng), apostrophe, hyphen. 2-30 ký tự.
_NAME_LIKE = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ'\-]{2,30}$")

# Markers cho biết đây là username/handle, không phải tên
_NON_NAME_TOKENS = {
    "seo", "growth", "marketing", "cmo", "ceo", "cto", "coo", "cop",
    "founder", "dev", "agent", "official", "team", "co", "inc", "llc",
    "agency", "consulting", "labs", "studio", "pro", "hq", "the",
    "real", "itsme", "mr", "mrs", "dr",
}

def extract_safe_first_name(
    first_name: Optional[str],
    last_name: Optional[str],
    public_id: Optional[str],
) -> Optional[str]:
    """
    Trả về first name an toàn để greet, hoặc None nếu không tìm thấy gì đáng tin.
    KHÔNG bao giờ trả về string xuất phát từ public_id (LinkedIn username).
    """
    # 1. DB first_name là source of truth
    candidate = _clean_name(first_name)
    if candidate:
        return candidate

    # 2. last_name đôi khi chứa cả họ tên (e.g. profile xuất file lệch)
    if last_name:
        first_part = last_name.strip().split()[0] if last_name.strip() else ""
        candidate = _clean_name(first_part)
        if candidate:
            return candidate

    # 3. KHÔNG fallback về public_id. Return None để prompt biết là không có tên.
    return None

def _clean_name(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    token = raw.strip().split()[0] if raw.strip() else ""
    if not token:
        return None
    if any(ch.isdigit() for ch in token):
        return None
    if not _NAME_LIKE.match(token):
        return None
    if token.lower() in _NON_NAME_TOKENS:
        return None
    # Reject "kristanbauer" (concat firstlast, all lowercase, > 12 chars)
    if token == token.lower() and len(token) > 12 and "-" not in token and "'" not in token:
        return None
    return token[0].upper() + token[1:].lower() if token.islower() else token
