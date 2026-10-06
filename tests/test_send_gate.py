from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from outreach.mail import AmbiguousDeliveryError, OutgoingEmail, send_approved_batch
from outreach.models import ContactVerification, Draft, OutreachMessage
from tests.mail_fixtures import approved_draft


class FakeTransport:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.sent: list[OutgoingEmail] = []

    def send(self, outgoing: OutgoingEmail) -> str:
        self.sent.append(outgoing)
        if self.error:
            raise self.error
        return f"<message-{len(self.sent)}@test>"


def test_only_approved_current_revision_is_sent(session: Session, tmp_path: Path) -> None:
    draft = approved_draft(session, tmp_path)
    transport = FakeTransport()

    result = send_approved_batch(
        session,
        [draft.id],
        sender="candidate@gmail.com",
        transport=transport,
        batch_key="batch-safe-1",
        pace_seconds=0,
    )

    assert result.sent == 1
    assert len(transport.sent) == 1
    assert transport.sent[0].attachment_path.is_file()
    assert session.get_one(Draft, draft.id).status == "sent"


def test_unapproved_or_unverified_draft_never_calls_transport(
    session: Session, tmp_path: Path
) -> None:
    draft = approved_draft(session, tmp_path)
    draft.status = "pending_review"
    verification = session.scalar(select(ContactVerification))
    assert verification is not None
    verification.status = "unknown"
    session.commit()
    transport = FakeTransport()

    result = send_approved_batch(
        session,
        [draft.id],
        sender="candidate@gmail.com",
        transport=transport,
        batch_key="batch-blocked-1",
        pace_seconds=0,
    )

    assert result.blocked == 1
    assert transport.sent == []


def test_same_batch_and_revision_are_idempotent(session: Session, tmp_path: Path) -> None:
    draft = approved_draft(session, tmp_path)
    transport = FakeTransport()
    first = send_approved_batch(
        session,
        [draft.id],
        sender="candidate@gmail.com",
        transport=transport,
        batch_key="batch-repeat-1",
        pace_seconds=0,
    )
    second = send_approved_batch(
        session,
        [draft.id],
        sender="candidate@gmail.com",
        transport=transport,
        batch_key="batch-repeat-1",
        pace_seconds=0,
    )

    assert first.sent == second.sent == 1
    assert len(transport.sent) == 1
    assert len(session.scalars(select(OutreachMessage)).all()) == 1


def test_ambiguous_delivery_is_never_retried(session: Session, tmp_path: Path) -> None:
    draft = approved_draft(session, tmp_path)
    transport = FakeTransport(AmbiguousDeliveryError("timeout"))
    result = send_approved_batch(
        session,
        [draft.id],
        sender="candidate@gmail.com",
        transport=transport,
        batch_key="batch-unknown-1",
        pace_seconds=0,
    )
    second = send_approved_batch(
        session,
        [draft.id],
        sender="candidate@gmail.com",
        transport=transport,
        batch_key="batch-unknown-2",
        pace_seconds=0,
    )

    assert result.delivery_unknown == 1
    assert second.blocked == 1
    assert len(transport.sent) == 1


def test_send_batch_rejects_more_than_twenty(session: Session) -> None:
    with pytest.raises(ValueError, match="between 1 and 20"):
        send_approved_batch(
            session,
            [str(index) for index in range(21)],
            sender="candidate@gmail.com",
            transport=FakeTransport(),
            batch_key="too-many",
            pace_seconds=0,
        )
