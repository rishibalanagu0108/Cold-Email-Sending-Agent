from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

BLOCKED_CONSUMER_DOMAINS = {
    "gmail.com",
    "googlemail.com",
    "outlook.com",
    "hotmail.com",
    "live.com",
    "yahoo.com",
    "icloud.com",
    "proton.me",
    "protonmail.com",
}


@dataclass(frozen=True)
class VerificationEvidence:
    email: str
    company_domain: str
    professional: bool
    public_professional: bool
    method: str
    status: str
    verified_at: datetime
    domain_accepts_mail: bool
    catch_all: bool
    evidence_url: str | None = None
    evidence_excerpt: str | None = None
    provider: str | None = None
    provider_result: str | None = None


def normalize_email(value: str) -> str:
    return value.strip().lower()


def verify_evidence(
    evidence: VerificationEvidence,
    *,
    at: datetime | None = None,
    max_age_days: int = 30,
) -> tuple[bool, str | None]:
    now = _aware(at or datetime.now(UTC))
    verified_at = _aware(evidence.verified_at)
    email = normalize_email(evidence.email)
    email_domain = email.rsplit("@", 1)[-1]

    if evidence.status != "verified":
        return False, "verification_not_valid"
    if not evidence.professional:
        return False, "not_professional"
    if verified_at > now + timedelta(days=1) or now - verified_at > timedelta(days=max_age_days):
        return False, "verification_stale"
    if not evidence.domain_accepts_mail:
        return False, "domain_does_not_accept_mail"
    if evidence.catch_all:
        return False, "catch_all"
    if email_domain in BLOCKED_CONSUMER_DOMAINS and not evidence.public_professional:
        return False, "consumer_address_not_publicly_professional"

    if evidence.method == "official_public":
        if not evidence.evidence_url or not evidence.evidence_excerpt:
            return False, "public_evidence_missing"
        if email not in evidence.evidence_excerpt.lower():
            return False, "address_not_present_in_evidence"
        return True, None

    if evidence.method == "free_provider":
        if not evidence.provider or evidence.provider_result != "valid":
            return False, "provider_did_not_confirm_valid"
        if email_domain != evidence.company_domain and not evidence.public_professional:
            return False, "provider_address_domain_mismatch"
        return True, None

    return False, "unsupported_verification_method"


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
