from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from outreach.mail import OutgoingEmail, send_approved_batch
from outreach.models import OutreachMessage, Reply, Suppression
from outreach.replies import InboundReply, classify_reply, sync_replies
from tests.mail_fixtures import approved_draft


class SuccessfulTransport:
    def send(self, outgoing: OutgoingEmail) -> str:
        return "<sent-message@example>"


def test_reply_is_matched_and_rejection_suppresses_company(
    session: Session, tmp_path: Path
) -> None:
    draft = approved_draft(session, tmp_path)
    send_approved_batch(
        session,
        [draft.id],
        sender="candidate@gmail.com",
        transport=SuccessfulTransport(),
        batch_key="reply-batch-1",
        pace_seconds=0,
    )
    counts = sync_replies(
        session,
        [
            InboundReply(
                gmail_message_id="<reply@example>",
                in_reply_to="<sent-message@example>",
                references=(),
                sender="founder@example.ai",
                subject="Re: AI Engineer",
                body="Thanks, but we are not moving forward.",
                received_at=datetime.now(UTC),
            )
        ],
    )

    assert counts == {"matched": 1, "suppressed": 1, "unmatched": 0, "duplicate": 0}
    assert session.scalar(select(func.count()).select_from(Reply)) == 1
    assert session.scalar(select(func.count()).select_from(Suppression)) == 1
    assert session.scalar(select(OutreachMessage.status)) == "replied"


def test_duplicate_and_unmatched_replies_are_safe(session: Session) -> None:
    inbound = InboundReply(
        gmail_message_id="<unmatched@example>",
        in_reply_to="<missing@example>",
        references=(),
        sender="person@example.ai",
        subject="Hello",
        body="Hello",
        received_at=datetime.now(UTC),
    )
    assert sync_replies(session, [inbound])["unmatched"] == 1
    assert classify_reply("Please remove me from this list") == "opt_out"
    assert classify_reply("Happy to talk next week") == "replied"
