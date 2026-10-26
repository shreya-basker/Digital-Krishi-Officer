"""Decision Fusion Engine: evaluates the rule base against one FarmContext and resolves conflicts."""

import string
from dataclasses import dataclass, field

from app.engine import kb
from app.engine.features import FarmContext


@dataclass
class Candidate:
    rule_id: str
    action_type: str
    title: str
    rationale: str
    signals: dict
    urgency: float
    impact: float
    confidence: float
    suppresses: list[str] = field(default_factory=list)


def _holds(value, cond) -> bool:
    if isinstance(cond, dict):
        if "missing" in cond:
            return (value is None) == cond["missing"]
        if value is None:
            return False
        if "gte" in cond and not value >= cond["gte"]:
            return False
        if "lte" in cond and not value <= cond["lte"]:
            return False
        if "not_in" in cond and value in cond["not_in"]:
            return False
        return True
    if value is None:
        return False
    if isinstance(cond, list):
        return value in cond
    return value == cond


def _applies_to(rule: dict, crop: str) -> bool:
    return rule["crop"] == "*" or crop in rule["crop"]


class _Formatter(string.Formatter):
    def format_field(self, value, format_spec):
        # a rule can fire while an unrelated field it mentions is missing
        return "—" if value is None else super().format_field(value, format_spec)


def _render(template: str, values: dict) -> str:
    return _Formatter().vformat(template, (), values)


def evaluate(ctx: FarmContext, rules: list[dict] | None = None) -> list[Candidate]:
    rules = kb.rules() if rules is None else rules
    values = ctx.as_dict()
    values["threats"] = ", ".join(ctx.pest_threats) or "common diseases"
    fired = []
    for rule in rules:
        if not _applies_to(rule, ctx.crop):
            continue
        if not all(_holds(values.get(k), cond) for k, cond in rule["when"].items()):
            continue
        fired.append(
            Candidate(
                rule_id=rule["id"],
                action_type=rule["action_type"],
                title=_render(rule["title"], values),
                rationale=_render(rule["rationale"], values),
                # the context values that triggered this rule, shown as "why" chips
                signals={k: values.get(k) for k in rule["when"]},
                urgency=rule["urgency"],
                impact=rule["impact"],
                confidence=rule["confidence"],
                suppresses=rule.get("suppresses", []),
            )
        )
    return resolve_conflicts(fired)


def resolve_conflicts(candidates: list[Candidate]) -> list[Candidate]:
    suppressed = {rid for c in candidates for rid in c.suppresses}
    return [c for c in candidates if c.rule_id not in suppressed]
