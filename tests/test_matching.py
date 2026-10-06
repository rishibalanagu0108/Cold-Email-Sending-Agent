from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from outreach.bundles import PreparationBundle
from outreach.matching import ScoreBreakdown
from tests.factories import bundle_payload, candidate_payload


def test_score_weights_are_bounded_and_totalled() -> None:
    score = ScoreBreakdown(35, 30, 20, 10, 5)
    assert score.total == 100
    assert score.as_dict()["role_alignment"] == 35

    with pytest.raises(ValueError, match="role_alignment"):
        ScoreBreakdown(36, 30, 20, 10, 5).validate()


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"role_family": "backend_engineer"}, "unsupported AI role family"),
        ({"is_open": False}, "job is closed"),
        ({"is_paid": False}, "job is unpaid"),
        ({"location_eligible": False}, "location is ineligible"),
        ({"seniority_eligible": False}, "seniority is ineligible"),
    ],
)
def test_ineligible_claim_cannot_be_marked_eligible(change: dict, message: str) -> None:
    candidate = candidate_payload()
    candidate.update(change)
    with pytest.raises(ValidationError, match=message):
        PreparationBundle.model_validate(bundle_payload("resume-1", [candidate]))


def test_stale_job_and_low_score_are_rejected() -> None:
    stale = candidate_payload(posted_at=datetime.now(UTC) - timedelta(days=8))
    with pytest.raises(ValidationError, match="older than seven days"):
        PreparationBundle.model_validate(bundle_payload("resume-1", [stale]))

    low = candidate_payload()
    low["score"]["role_alignment"] = 10
    with pytest.raises(ValidationError, match="below 70"):
        PreparationBundle.model_validate(bundle_payload("resume-1", [low]))


def test_eligible_candidate_requires_job_and_company_evidence() -> None:
    candidate = candidate_payload()
    candidate["evidence"] = [candidate["evidence"][-1]]
    with pytest.raises(ValidationError, match="job and company evidence"):
        PreparationBundle.model_validate(bundle_payload("resume-1", [candidate]))
