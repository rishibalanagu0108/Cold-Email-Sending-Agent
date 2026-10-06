from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True)
class ScoreBreakdown:
    role_alignment: int
    demonstrated_skills: int
    experience_seniority: int
    location_eligibility: int
    evidence_quality: int

    LIMITS: ClassVar[dict[str, int]] = {
        "role_alignment": 35,
        "demonstrated_skills": 30,
        "experience_seniority": 20,
        "location_eligibility": 10,
        "evidence_quality": 5,
    }

    def validate(self) -> None:
        for name, maximum in self.LIMITS.items():
            value = getattr(self, name)
            if not 0 <= value <= maximum:
                raise ValueError(f"{name} must be between 0 and {maximum}")

    @property
    def total(self) -> int:
        self.validate()
        return sum(getattr(self, name) for name in self.LIMITS)

    def as_dict(self) -> dict[str, int]:
        self.validate()
        return {name: getattr(self, name) for name in self.LIMITS}


AI_ROLE_FAMILIES = {
    "ai_engineer",
    "machine_learning_engineer",
    "applied_ai_engineer",
    "generative_ai_engineer",
    "llm_engineer",
    "agentic_ai_engineer",
    "nlp_engineer",
    "computer_vision_engineer",
    "ai_research_engineer",
    "mlops_engineer",
    "ml_platform_engineer",
}
