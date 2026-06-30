#!/usr/bin/env python3
"""Build a cold-start, clean-lane product-matching fixture from the billiger scrape.

Reads the committed raw scrape (pilot-data/billiger-pilot-offers.csv), drops
confident label noise (clean lane), splits clusters cold-start (train/test
disjoint by product), anonymises ids, samples eval pairs, and writes the fixture
plus verifier-owned hidden labels and a build report. Deterministic given SEED.

See docs/superpowers/specs/2026-06-30-billiger-fixture-builder-design.md.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import re
import statistics
from collections import defaultdict
from pathlib import Path

SEED = 20260630

_MODEL_RE = re.compile(
    r"\b(galaxy s\d{2}|galaxy a\d{2}|iphone ?\d{1,2}e?|redmi note \d+|pixel \d+|rtx ?\d{4}|rx ?\d{4})\b"
)
_UNIT_RE = re.compile(r"\b(\d+ ?tb|\d+ ?gb)\b")


def read_offers(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def model_tokens(text: str) -> set[str]:
    return {re.sub(r"\s+", "", m) for m in _MODEL_RE.findall(text.lower())}


def unit_tokens(text: str) -> set[str]:
    return {re.sub(r"\s+", "", m) for m in _UNIT_RE.findall(text.lower())}
