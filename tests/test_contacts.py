from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from outreach.bundles import import_bundle
from outreach.contacts import ContactInput, contact_role_matches, store_verified_contact
from outreach.foundation import get_or_create_company
from outreach.models import Contact, ContactVerification, ResumeVersion
from outreach.verification import VerificationEvidence
from tests.factories import make_bundle


@pytest.mark.parametrize(
    ("stage", "role", "expected"),
    [
        ("early", "Co-Founder", True),
        ("early", "Recruiter", False),
        ("medium", "CTO", True),
        ("medium", "Engineering Manager", True),
        ("large", "Senior Technical Recruiter", True),
        ("large", "Sales Manager", False),
    ],
)
def test_contact_role_follows_company_stage(stage: str, role: str, expected: bool) -> None:
    assert contact_role_matches(stage, role) is expected


def test_store_verified_professional_contact(session: Session) -> None:
    company = get_or_create_company(session, "Example AI", "example.ai")
    company.stage = "early"
    now = datetime.now(UTC)
    contact = store_verified_contact(
        session,
        company,
        ContactInput(
            name="Ada Founder",
            role="Founder",
            email="ADA@example.ai",
            source_url="https://example.ai/team",
            verification=VerificationEvidence(
                email="ADA@example.ai",
                company_domain="example.ai",
                professional=True,
                public_professional=False,
                method="official_public",
                status="verified",
                verified_at=now,
                domain_accepts_mail=True,
                catch_all=False,
                evidence_url="https://example.ai/team",
                evidence_excerpt="Email Ada at ada@example.ai",
            ),
        ),
    )
    session.commit()

    assert contact.normalized_email == "ada@example.ai"
    assert session.scalar(select(func.count()).select_from(ContactVerification)) == 1


def test_bundle_import_persists_only_verified_contact(session: Session) -> None:
    resume = ResumeVersion(
        sha256="e" * 64,
        original_filename="resume.pdf",
        local_path="/private/resume.pdf",
        confirmed=True,
    )
    session.add(resume)
    session.commit()

    result = import_bundle(session, make_bundle(resume.id))

    assert result.imported == 1
    assert session.scalar(select(func.count()).select_from(Contact)) == 1
    assert session.scalar(select(ContactVerification.status)) == "verified"


def test_wrong_stage_contact_rolls_back_import(session: Session) -> None:
    resume = ResumeVersion(
        sha256="f" * 64,
        original_filename="resume.pdf",
        local_path="/private/resume.pdf",
        confirmed=True,
    )
    session.add(resume)
    session.commit()
    bundle = make_bundle(resume.id)
    bundle.candidates[0].contact.role = "Sales Manager"  # type: ignore[union-attr]

    with pytest.raises(ValueError, match="company-stage priority"):
        import_bundle(session, bundle)
    assert session.scalar(select(func.count()).select_from(Contact)) == 0
