"""LED pattern enum (§6.4).

The integer values are the wire values sent to the Firefly device. The two
named lookup tables map between firmware names, public-API names, and the
integer ``LedPattern``.
"""

from __future__ import annotations

from enum import IntEnum

from firefly_api.core.errors import ValidationFailedError


class LedPattern(IntEnum):
    FULL = 0
    SLOT_ENDS = 1
    SLOT_NO_ENDS = 2
    SUBSEGMENTS = 3
    MULTICOLOR = 4


PATTERN_FIRMWARE_NAMES: dict[LedPattern, str] = {
    LedPattern.FULL: "LED_PATTERN_FULL",
    LedPattern.SLOT_ENDS: "LED_PATTERN_SLOT_ENDS",
    LedPattern.SLOT_NO_ENDS: "LED_PATTERN_SLOT_NO_ENDS",
    LedPattern.SUBSEGMENTS: "LED_PATTERN_SUBSEGMENTS",
    LedPattern.MULTICOLOR: "LED_PATTERN_MULTICOLOR",
}

PATTERN_PUBLIC_NAMES: dict[LedPattern, str] = {
    LedPattern.FULL: "full",
    LedPattern.SLOT_ENDS: "slot_ends",
    LedPattern.SLOT_NO_ENDS: "slot_no_ends",
    LedPattern.SUBSEGMENTS: "subsegments",
    LedPattern.MULTICOLOR: "multicolor",
}

_PUBLIC_TO_PATTERN: dict[str, LedPattern] = {
    name: pattern for pattern, name in PATTERN_PUBLIC_NAMES.items()
}


def pattern_from_public_name(name: str) -> LedPattern:
    """Resolve a public-API pattern name (e.g. ``"slot_ends"``) to its ``LedPattern``."""
    try:
        return _PUBLIC_TO_PATTERN[name]
    except KeyError as exc:
        raise ValidationFailedError(
            f"Unknown pattern '{name}'. Supported: "
            f"{sorted(_PUBLIC_TO_PATTERN.keys())}.",
            error_code="invalid_pattern",
        ) from exc


def public_name_for_pattern(pattern: int) -> str:
    """Return the public-API name for an ``LedPattern`` (or raw integer)."""
    try:
        return PATTERN_PUBLIC_NAMES[LedPattern(pattern)]
    except ValueError as exc:
        raise ValidationFailedError(
            f"Pattern {pattern} is not a known LED pattern.",
            error_code="invalid_pattern",
        ) from exc
