from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from outreach.config import Settings
from outreach.db import Base, create_database_engine
from outreach.models import Company


def test_all_required_foundation_tables_exist() -> None:
    engine = create_database_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    assert {
        "resume_versions",
        "profile_facts",
        "discovery_runs",
        "companies",
        "company_aliases",
        "jobs",
        "job_sources",
        "job_matches",
        "match_evidence",
        "contacts",
        "contact_verifications",
        "drafts",
        "draft_claims",
        "approvals",
        "send_batches",
        "outreach_messages",
        "replies",
        "suppressions",
        "audit_events",
    } <= set(inspect(engine).get_table_names())


def test_database_enforces_unique_company_domain(session: Session) -> None:
    session.add_all(
        [
            Company(name="One", canonical_domain="example.com"),
            Company(name="Two", canonical_domain="example.com"),
        ]
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_configuration_normalizes_neon_driver_and_rejects_public_bind(tmp_path: Path) -> None:
    settings = Settings(
        database_url="postgresql://user:pass@example.neon.tech/db?sslmode=require",
        local_data_dir=tmp_path,
    )
    assert settings.database_url.startswith("postgresql+psycopg://")
    assert "pass" not in repr(settings)

    with pytest.raises(ValueError, match="loopback"):
        Settings(app_host="0.0.0.0")
