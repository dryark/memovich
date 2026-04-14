"""Load tier YAML presets (default research layout + legacy palace example)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

_CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "configs" / "tiers"


@dataclass
class TierLevel:
    """One tier in the wake-up / retrieval stack."""

    id: str
    role: str
    max_tokens: Optional[int] = None
    max_chunks: Optional[int] = None
    max_chars: Optional[int] = None
    max_scan: Optional[int] = None
    group_by: str = "segment"
    default_limit: int = 10
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TierPreset:
    """Full preset: ordered tiers + optional keyword routing (legacy)."""

    name: str
    tiers: List[TierLevel]
    segment_keywords: Optional[Dict[str, List[str]]] = None


def load_tier_preset(name: str) -> TierPreset:
    """Load ``name``.yaml from ``configs/tiers/``."""
    path = _CONFIG_DIR / f"{name}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"Tier preset not found: {path}")
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    tiers_raw = raw.get("tiers") or []
    tiers = []
    for t in tiers_raw:
        tid = str(t.get("id", ""))
        role = str(t.get("role", "vector_search"))
        known = {
            "id",
            "role",
            "max_tokens",
            "max_chunks",
            "max_chars",
            "max_scan",
            "group_by",
            "default_limit",
        }
        extra = {k: v for k, v in t.items() if k not in known}
        tiers.append(
            TierLevel(
                id=tid,
                role=role,
                max_tokens=t.get("max_tokens"),
                max_chunks=t.get("max_chunks"),
                max_chars=t.get("max_chars"),
                max_scan=t.get("max_scan"),
                group_by=str(t.get("group_by", "segment")),
                default_limit=int(t.get("default_limit", 10)),
                extra=extra,
            )
        )
    return TierPreset(
        name=str(raw.get("preset", name)),
        tiers=tiers,
        segment_keywords=raw.get("segment_keywords"),
    )


def get_preset_for_config(config) -> TierPreset:
    """Resolve preset from ``MemovichConfig.tier_preset``."""
    return load_tier_preset(config.tier_preset)
