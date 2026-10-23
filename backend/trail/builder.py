"""Trail orchestration for the Study Trail Builder backend.

This module holds ``build_trail``, the single orchestration entry point that
turns a Candidate_Set into a grouped Study_Trail. It is AI-first and
heuristic-always: the AI_Service is the preferred ranker, but the deterministic
heuristic guarantees a usable result in every case (Req 4.2, 4.5, 4.7).

``build_trail`` is pure orchestration. It reuses the existing building blocks
rather than reimplementing any logic:

- ``heuristic.heuristic_order`` for a stable, deterministic base order (Req 4.3),
- ``ai.rank_and_group`` for the preferred AI assignment of ids to levels,
- ``heuristic.group_into_tiers`` for the deterministic fallback grouping.

Whichever path produces the trail, the result has the same shape: exactly three
Sections in ``LEVEL_ORDER``. The function never raises; the AI call is wrapped
defensively even though ``rank_and_group`` already degrades to ``None`` on any
failure.
"""

from __future__ import annotations

from dataclasses import replace

from . import ai
from .heuristic import group_into_tiers, heuristic_order
from .models_data import LEVEL_ORDER, Level, Section, Trail, Video

# Fewer than this many candidates means the trail is flagged as insufficient
# so the Learner is told that fewer than ten videos were available (Req 4.6).
MIN_TRAIL_SIZE = 10


def build_trail(topic: str, candidates: list[Video]) -> Trail:
    """Build a grouped Study_Trail from a Candidate_Set, AI-first.

    Steps (mirroring the design's ``builder.py`` contract):

    1. Compute a stable heuristic base order over the candidates (Req 4.3). This
       order is used to make the within-level ordering deterministic in the AI
       path and is the input to the fallback grouping.
    2. Ask the AI_Service to map each video id to a difficulty level. The call
       is wrapped defensively so any unexpected error degrades to ``None``
       rather than propagating (Req 4.7).
    3. If the AI returns a usable assignment (``rank_and_group`` already
       guarantees it covers at least ten videos with valid levels), build a
       Trail from it: every candidate is placed into its assigned level, ordered
       Basic -> Intermediate -> Advanced, preserving the heuristic base order
       within each level for determinism (Req 3.4, 3.5).
    4. Otherwise fall back to ``group_into_tiers`` over the heuristic order
       (Req 4.2).
    5. Set ``topic`` and ``insufficient`` on the result in both paths; the
       heuristic helper leaves them at neutral defaults, so they are overridden
       here (Req 4.6).

    The returned Trail always has exactly three ordered Sections and is a
    permutation of a subset of the candidates (no invented videos, Req 3.6,
    Property 4). This function never raises (Req 4.5, 4.7, Property 8).
    """
    candidates = list(candidates or [])

    # 1. Stable, deterministic base order shared by both paths (Req 4.3).
    ordered = heuristic_order(candidates)

    # 2. Preferred AI path, wrapped defensively (Req 4.7). ``rank_and_group``
    #    already never raises, but the belt-and-braces guard keeps build_trail
    #    total even if that ever changes.
    assignment: dict[str, str] | None
    try:
        assignment = ai.rank_and_group(topic, candidates)
    except Exception:  # noqa: BLE001 - orchestration must never raise.
        assignment = None

    if assignment:
        # 3. AI path: place every candidate into its assigned level.
        trail = _build_from_assignment(ordered, assignment)
    else:
        # 4. Heuristic fallback: deterministic three-tier split (Req 4.2).
        trail = group_into_tiers(ordered)

    # 5. Override the neutral defaults with the real topic and the insufficient
    #    flag (fewer than ten candidates available, Req 4.6).
    return replace(
        trail,
        topic=topic,
        insufficient=len(candidates) < MIN_TRAIL_SIZE,
    )


def _build_from_assignment(
    ordered: list[Video],
    assignment: dict[str, str],
) -> Trail:
    """Build a three-Section Trail from an AI ``{video_id: level}`` assignment.

    Every video in ``ordered`` is included (no candidate is dropped and none is
    invented, Req 3.6). A video's level comes from ``assignment`` when present;
    any candidate the AI left unassigned is placed defensively by splitting the
    unassigned videos positionally across the three tiers in heuristic order, so
    the result is still a clean three-tier partition. Within each level the
    heuristic base order of ``ordered`` is preserved for determinism.

    The Sections are emitted in ``LEVEL_ORDER`` (Basic -> Intermediate ->
    Advanced), so flattening the trail yields non-decreasing levels (Req 3.5,
    Property 6). Each video appears in exactly one Section with exactly one valid
    level (Req 3.4, Property 5).
    """
    # Resolve a fallback level for any candidate the assignment omits, derived
    # from the position of the unassigned videos within the heuristic order so
    # the placement stays deterministic.
    unassigned = [v for v in ordered if v.id not in assignment]
    fallback_level = _positional_levels(unassigned)

    # Bucket videos per level, iterating in heuristic order so each level's list
    # preserves the deterministic base order (Property 2 -> Property 6).
    buckets: dict[Level, list[Video]] = {level: [] for level in LEVEL_ORDER}
    for video in ordered:
        name = assignment.get(video.id)
        level = _level_from_name(name) if name is not None else None
        if level is None:
            level = fallback_level.get(video.id, LEVEL_ORDER[0])
        buckets[level].append(replace(video, level=level))

    sections = [Section(level=level, videos=buckets[level]) for level in LEVEL_ORDER]
    # topic / insufficient are set by the caller.
    return Trail(topic="", sections=sections, insufficient=False)


def _positional_levels(videos: list[Video]) -> dict[str, Level]:
    """Map each video id to a tier by splitting the list into three slices.

    Mirrors ``group_into_tiers``' contiguous split so defensively placed,
    AI-unassigned videos follow the same deterministic tiering rule: the list is
    cut into three contiguous slices (Basic / Intermediate / Advanced) with any
    remainder from an uneven division going to the earlier tiers.
    """
    n = len(videos)
    if n == 0:
        return {}

    base, remainder = divmod(n, len(LEVEL_ORDER))
    result: dict[str, Level] = {}
    start = 0
    for index, level in enumerate(LEVEL_ORDER):
        size = base + (1 if index < remainder else 0)
        for video in videos[start:start + size]:
            result[video.id] = level
        start += size
    return result


def _level_from_name(name: str) -> Level | None:
    """Return the ``Level`` for a canonical level name, or ``None`` if unknown.

    The AI parser already normalizes names to the canonical ``Basic`` /
    ``Intermediate`` / ``Advanced`` spelling, so a plain ``Level(name)`` lookup
    suffices; any unexpected value degrades to ``None`` for defensive placement.
    """
    try:
        return Level(name)
    except ValueError:
        return None
