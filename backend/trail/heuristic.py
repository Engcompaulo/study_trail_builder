"""Deterministic Heuristic_Fallback for the Study Trail Builder backend.

This module holds the pure, deterministic ordering and grouping logic used
whenever the AI_Service is unavailable, slow, or returns unusable output
(Req 4.2, 4.3, 4.4). Both functions are pure: they depend only on their inputs,
never mutate the input videos, and produce the same output on repeated calls.

- ``heuristic_order`` imposes a total, deterministic order on a Candidate_Set.
- ``group_into_tiers`` splits an ordered list into exactly three contiguous
  difficulty tiers that partition the input.
"""

from __future__ import annotations

from dataclasses import replace

from .models_data import LEVEL_ORDER, Section, Trail, Video


def heuristic_order(candidates: list[Video]) -> list[Video]:
    """Order a Candidate_Set deterministically from most to least prominent.

    The sort key is ``(-view_count, -like_count, duration, id)`` (Req 4.3):

    1. descending view count,
    2. then descending like count,
    3. then ascending duration,
    4. then ascending video id as the final tie-break.

    Including the video id as the last key makes the order *total*: any two
    distinct videos have a well-defined relative position, so the result is
    deterministic and independent of the input ordering (Property 2).

    The input list is not mutated; a new ordered list is returned.
    """
    return sorted(
        candidates,
        key=lambda v: (-v.view_count, -v.like_count, v.duration, v.id),
    )


def group_into_tiers(ordered: list[Video]) -> Trail:
    """Split an ordered list into exactly three contiguous difficulty tiers.

    The ordered list is cut into three contiguous slices mapped to Basic,
    Intermediate, and Advanced in ``LEVEL_ORDER``. Order is preserved and the
    three tiers *partition* the input: concatenating them in
    Basic -> Intermediate -> Advanced order reproduces ``ordered`` exactly, with
    no video dropped, duplicated, or added (Req 4.4, Property 3).

    Tier sizes come from an even division; any remainder from an uneven division
    is distributed to the earlier tiers (Basic first, then Intermediate), so the
    earlier tiers are never smaller than the later ones.

    Each video is assigned its tier's ``Level`` via ``dataclasses.replace`` (the
    ``Video`` dataclass is frozen), giving every trail video exactly one valid
    level (Req 3.4, Property 5) with levels non-decreasing across the flattened
    trail (Req 3.5, Property 6).

    ``topic`` and ``insufficient`` are left at neutral defaults (``""`` and
    ``False``); the orchestrator/view fills in the real values, matching the
    design's ``group_into_tiers(ordered) -> Trail`` signature.
    """
    n = len(ordered)
    base, remainder = divmod(n, len(LEVEL_ORDER))

    sections: list[Section] = []
    start = 0
    for index, level in enumerate(LEVEL_ORDER):
        # Earlier tiers absorb the remainder, one extra video each.
        size = base + (1 if index < remainder else 0)
        tier = ordered[start:start + size]
        start += size
        videos = [replace(video, level=level) for video in tier]
        sections.append(Section(level=level, videos=videos))

    return Trail(topic="", sections=sections, insufficient=False)
