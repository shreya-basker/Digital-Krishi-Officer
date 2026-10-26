"""Plain-language explanations of ranked actions, constrained to the engine's own output."""

from app import llm
from app.engine.ranker import RankedAction

DISCLAIMER = (
    "These are decision-support suggestions generated from weather, soil, crop and market data. "
    "They are not validated agronomic prescriptions — confirm doses and treatments with your KVK or Krishi officer."
)


def localise(actions: list[RankedAction], language: str) -> list[RankedAction]:
    """English templates are already plain; other languages are rewritten by the LLM when configured."""
    if language == "en":
        return actions
    items = [{"id": a.rank, "title": a.candidate.title, "rationale": a.candidate.rationale} for a in actions]
    rewritten = llm.rewrite_actions(items, language)
    if not rewritten:
        return actions
    for a in actions:
        if a.rank in rewritten:
            a.candidate.title = rewritten[a.rank]["title"]
            a.candidate.rationale = rewritten[a.rank]["rationale"]
    return actions
