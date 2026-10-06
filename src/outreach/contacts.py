from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from outreach.models import Company, Contact, ContactVerification
from outreach.verification import VerificationEvidence, normalize_email, verify_evidence

ROLE_PATTERNS = {
    "early": (r"\bfounder\b", r"\bco[- ]?founder\b"),
    "medium": (
        r"\bcto\b",
        r"chief technology officer",
        r"\bvp\b.*engineering",
        r"head of engineering",
        r"director of engineering",
        r"engineering manager",
    ),
    "large": (
        r"recruit",
        r"talent",
        r"hiring manager",
        r"human resources",
        r"\bhr\b",
        r"engineering manager",
        r"director of engineering",
        r"\bvp\b.*engineering",
    ),
}


@dataclass(frozen=True)
class ContactInput:
    name: str
    role: str
    email: str
    source_url: str
    verification: VerificationEvidence


def contact_role_matches(company_stage: str, role: str) -> bool:
    patterns = ROLE_PATTERNS.get(company_stage)
    if not patterns:
        patterns = tuple(pattern for group in ROLE_PATTERNS.values() for pattern in group)
    normalized_role = " ".join(role.lower().split())
    return any(re.search(pattern, normalized_role) for pattern in patterns)


def store_verified_contact(session: Session, company: Company, candidate: ContactInput) -> Contact:
    if not contact_role_matches(company.stage or "unknown", candidate.role):
        raise ValueError("Contact role does not match company-stage priority")
    valid, reason = verify_evidence(candidate.verification)
    if not valid:
        raise ValueError(f"Contact is not verified: {reason}")

    normalized = normalize_email(candidate.email)
    existing = session.scalar(select(Contact).where(Contact.normalized_email == normalized))
    if existing:
        if existing.company_id != company.id:
            raise ValueError("Email is already associated with another company")
        contact = existing
    else:
        contact = Contact(
            company_id=company.id,
            name=candidate.name.strip(),
            role=candidate.role.strip(),
            email=candidate.email.strip(),
            normalized_email=normalized,
            source_url=candidate.source_url,
            professional=True,
        )
        session.add(contact)
        session.flush()

    session.add(
        ContactVerification(
            contact_id=contact.id,
            status="verified",
            method=candidate.verification.method,
            provider=candidate.verification.provider,
            evidence_url=candidate.verification.evidence_url,
            verified_at=candidate.verification.verified_at,
        )
    )
    session.flush()
    return contact
