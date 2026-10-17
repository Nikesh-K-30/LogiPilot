from __future__ import annotations

import hashlib
import hmac
import time

from app.config import get_settings


def issue_approval_token(*, actor: str, action: str, entity_id: str, ttl_seconds: int = 3600) -> str:
    """Issue a short-lived HMAC approval token for consequential writes."""
    settings = get_settings()
    expires = int(time.time()) + ttl_seconds
    payload = f"{actor}|{action}|{entity_id}|{expires}"
    sig = hmac.new(
        settings.approval_secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload}|{sig}"


def verify_approval_token(
    token: str,
    *,
    actor: str,
    action: str,
    entity_id: str,
) -> bool:
    settings = get_settings()
    parts = token.split("|")
    if len(parts) != 5:
        return False
    tok_actor, tok_action, tok_entity, expires_s, sig = parts
    if tok_actor != actor or tok_action != action or tok_entity != entity_id:
        return False
    try:
        expires = int(expires_s)
    except ValueError:
        return False
    if expires < int(time.time()):
        return False
    payload = f"{tok_actor}|{tok_action}|{tok_entity}|{expires_s}"
    expected = hmac.new(
        settings.approval_secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, sig)
