from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from outreach.bundles import PreparationBundle, import_bundle
from outreach.drafts import approve_draft
from outreach.models import Draft, ResumeVersion
from tests.factories import bundle_payload


def approved_draft(session: Session, tmp_path: Path, *, run_key: str = "mail-run-0001") -> Draft:
    resume_path = tmp_path / f"{run_key}.pdf"
    resume_path.write_bytes(b"%PDF fixture")
    resume = ResumeVersion(
        sha256=(run_key.encode().hex() + "0" * 64)[:64],
        original_filename="resume.pdf",
        local_path=str(resume_path),
        confirmed=True,
    )
    session.add(resume)
    session.commit()
    payload = bundle_payload(resume.id)
    payload["run_idempotency_key"] = run_key
    bundle = PreparationBundle.model_validate(payload)
    import_bundle(session, bundle)
    draft = session.scalar(select(Draft).where(Draft.resume_version_id == resume.id))
    assert draft is not None
    approve_draft(session, draft.id)
    return draft
