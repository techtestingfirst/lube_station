"""Shared adapter helpers: no credentials in logs."""

import hashlib
import hmac


def verify_signature(secret: str, payload: bytes, signature: str) -> bool:
    digest = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, signature)


def idempotency_key(*parts: str) -> str:
    return ":".join(p or "" for p in parts)


def redact(payload: dict) -> dict:
    banned = {"api_key", "api_secret", "card", "cvv", "pan", "secret", "token"}
    return {k: ("***" if k.lower() in banned else v) for k, v in payload.items()}
