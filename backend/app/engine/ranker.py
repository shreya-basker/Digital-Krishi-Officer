"""Ranks fused candidates. The feedback prior closes the loop: rules farmers keep
accepting are nudged up, rules they keep rejecting are nudged down."""

from dataclasses import dataclass

from app.engine.fusion import Candidate

# Beta(2, 2)-style smoothing: with no feedback the prior factor is exactly 1.0
PRIOR_PSEUDO_ACCEPTS = 2
PRIOR_PSEUDO_TOTAL = 4


@dataclass
class RankedAction:
    candidate: Candidate
    score: float
    rank: int


def feedback_prior(accepted: int, total: int) -> float:
    """Maps a smoothed acceptance rate in (0, 1) to a factor in (0.5, 1.5)."""
    rate = (accepted + PRIOR_PSEUDO_ACCEPTS) / (total + PRIOR_PSEUDO_TOTAL)
    return 0.5 + rate


def rank(
    candidates: list[Candidate], feedback_counts: dict[str, tuple[int, int]] | None = None, top_n: int | None = None
) -> list[RankedAction]:
    feedback_counts = feedback_counts or {}
    scored = []
    for c in candidates:
        accepted, total = feedback_counts.get(c.rule_id, (0, 0))
        score = c.urgency * c.impact * c.confidence * feedback_prior(accepted, total)
        scored.append((round(score, 4), c))
    scored.sort(key=lambda sc: sc[0], reverse=True)
    if top_n is not None:
        scored = scored[:top_n]
    return [RankedAction(candidate=c, score=s, rank=i + 1) for i, (s, c) in enumerate(scored)]
