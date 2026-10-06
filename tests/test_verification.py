from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from outreach.verification import VerificationEvidence, normalize_email, verify_evidence


def _official(**changes: object) -> VerificationEvidence:
    base = VerificationEvidence(
        email="founder@example.ai",
        company_domain="example.ai",
        professional=True,
        public_professional=False,
        method="official_public",
        status="verified",
        verified_at=datetime.now(UTC),
        domain_accepts_mail=True,
        catch_all=False,
        evidence_url="https://example.ai/team",
        evidence_excerpt="Write to founder@example.ai for professional inquiries.",
    )
    return replace(base, **changes)


def test_publicly_listed_company_email_is_verified() -> None:
    assert verify_evidence(_official()) == (True, None)
    assert normalize_email(" Founder@Example.AI ") == "founder@example.ai"


@pytest.mark.parametrize(
    ("evidence", "reason"),
    [
        (_official(status="unknown"), "verification_not_valid"),
        (_official(professional=False), "not_professional"),
        (
            _official(verified_at=datetime.now(UTC) - timedelta(days=31)),
            "verification_stale",
        ),
        (_official(domain_accepts_mail=False), "domain_does_not_accept_mail"),
        (_official(catch_all=True), "catch_all"),
        (_official(evidence_excerpt="No address here"), "address_not_present_in_evidence"),
    ],
)
def test_unsafe_verification_fails_closed(evidence: VerificationEvidence, reason: str) -> None:
    assert verify_evidence(evidence) == (False, reason)


def test_consumer_email_requires_explicit_professional_publication() -> None:
    blocked = _official(
        email="founder@gmail.com",
        evidence_excerpt="founder@gmail.com",
    )
    assert verify_evidence(blocked)[1] == "consumer_address_not_publicly_professional"
    assert verify_evidence(replace(blocked, public_professional=True)) == (True, None)


def test_free_provider_must_return_valid_and_match_company() -> None:
    verified = _official(
        method="free_provider",
        evidence_url=None,
        evidence_excerpt=None,
        provider="ExampleVerifier free tier",
        provider_result="valid",
    )
    assert verify_evidence(verified) == (True, None)
    assert verify_evidence(replace(verified, provider_result="accept_all"))[1] == (
        "provider_did_not_confirm_valid"
    )
    assert verify_evidence(replace(verified, email="person@other.ai"))[1] == (
        "provider_address_domain_mismatch"
    )
