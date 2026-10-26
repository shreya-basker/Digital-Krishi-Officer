"""Loads the YAML knowledge base (crop calendars, soil ratings, pest conditions, rules)."""

from functools import cache
from pathlib import Path

import yaml

KNOWLEDGE_DIR = Path(__file__).parent / "knowledge"


def _load(name: str):
    with open(KNOWLEDGE_DIR / name, encoding="utf-8") as f:
        return yaml.safe_load(f)


@cache
def crops() -> dict:
    return _load("crops.yaml")


@cache
def soil_thresholds() -> dict:
    return _load("soil_thresholds.yaml")


@cache
def pests() -> dict:
    return _load("pests.yaml")


@cache
def rules() -> list[dict]:
    return _load("rules.yaml")


def crop(key: str) -> dict:
    try:
        return crops()[key]
    except KeyError:
        raise ValueError(f"Unknown crop '{key}'")
