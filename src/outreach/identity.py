from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING_KEYS = {"fbclid", "gclid", "ref", "source"}


def normalize_domain(value: str) -> str:
    candidate = value.strip().lower()
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    host = (urlsplit(candidate).hostname or "").strip(".")
    host = host.removeprefix("www.")
    if not host or "." not in host or not re.fullmatch(r"[a-z0-9.-]+", host):
        raise ValueError("A valid company domain is required")
    return host


def canonicalize_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only absolute HTTP(S) URLs are accepted")
    host = parsed.hostname.lower()
    port = f":{parsed.port}" if parsed.port else ""
    path = re.sub(r"/{2,}", "/", parsed.path).rstrip("/") or "/"
    query = urlencode(
        sorted(
            (key, val)
            for key, val in parse_qsl(parsed.query, keep_blank_values=True)
            if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_KEYS
        )
    )
    return urlunsplit((parsed.scheme.lower(), f"{host}{port}", path, query, ""))


def normalize_text(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9+#.]+", " ", value.lower()).split())


def job_fingerprint(title: str, location: str, description: str) -> str:
    normalized = "\x1f".join(
        (normalize_text(title), normalize_text(location), normalize_text(description))
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
