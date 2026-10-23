"""Property and example tests for the deterministic Heuristic_Fallback.

Covers the pure heuristic core (``heuristic_order`` / ``group_into_tiers``) and
the full ``build_trail`` orchestration with the AI stubbed to fail, plus the two
example-based ``trail_view`` checks. Per the design's Testing Strategy these are
the minimal essential tests for Req 8.1 and the Property 9 boundary anchors.

No network is touched: ``ai.rank_and_group`` is monkeypatched to return ``None``
so ``build_trail`` always takes the heuristic path, and the view tests stub the
search and builder edges.
"""

from __future__ import annotations

from dataclasses import replace
from unittest import mock

import pytest
from hypothesis import given
from hypothesis import strategies as st

from trail import ai, views
from trail.builder import build_trail
from trail.heuristic import group_into_tiers, heuristic_order
from trail.models_data import LEVEL_ORDER, Level, SearchResult, Trail, Video


# --------------------------------------------------------------------------- #
# Hypothesis strategies
#
# Build Video instances with small non-negative integer view/like counts, a
# strictly positive duration, and unique string ids. Uniqueness of ids is what
# makes the heuristic order total (the id is the final tie-break), so the
# generators constrain to that input space intentionally.
# --------------------------------------------------------------------------- #

_ID_ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"


def _video(id: str, view_count: int, like_count: int, duration: int) -> Video:
    """Construct a valid candidate Video (non-empty title/url, duration > 0)."""
    return Video(
        id=id,
        title=f"Video {id}",
        url=f"https://www.youtube.com/watch?v={id}",
        duration=duration,
        view_count=view_count,
        like_count=like_count,
    )


def _video_strategy() -> st.SearchStrategy[Video]:
    """A single Video with small counts and a positive duration."""
    return st.builds(
        _video,
        id=st.text(alphabet=_ID_ALPHABET, min_size=1, max_size=8),
        view_count=st.integers(min_value=0, max_value=1000),
        like_count=st.integers(min_value=0, max_value=1000),
        duration=st.integers(min_value=1, max_value=3600),
    )


def _candidates_strategy(min_size: int = 0, max_size: int = 40):
    """A list of Videos with unique ids (unique by the ``id`` key)."""
    return st.lists(
        _video_strategy(),
        min_size=min_size,
        max_size=max_size,
        unique_by=lambda v: v.id,
    )


def _flatten(trail: Trail) -> list[Video]:
    """Flatten a Trail's sections in LEVEL_ORDER into a single video list."""
    videos: list[Video] = []
    for level in LEVEL_ORDER:
        section = next(s for s in trail.sections if s.level == level)
        videos.extend(section.videos)
    return videos


def _build_trail_no_ai(topic: str, candidates: list[Video]) -> Trail:
    """Run ``build_trail`` with the AI forced to fail (heuristic path only).

    ``ai.rank_and_group`` is patched inside the call rather than via a
    function-scoped fixture so Hypothesis resets it cleanly for each generated
    input. The builder imports the ``ai`` module object, so patching
    ``ai.rank_and_group`` is what it actually invokes.
    """
    with mock.patch.object(ai, "rank_and_group", lambda t, c: None):
        return build_trail(topic, candidates)


# --------------------------------------------------------------------------- #
# Property 2
# --------------------------------------------------------------------------- #

# Feature: study-trail-builder, Property 2: heuristic_order is deterministic and
# total - idempotent across repeated calls, invariant under input shuffling, and
# respects the sort-key precedence (-view_count, -like_count, duration, id).
# Validates: Requirements 4.3
@given(candidates=_candidates_strategy(), seed=st.integers(min_value=0, max_value=10_000))
def test_property_2_heuristic_order_deterministic_and_total(candidates, seed):
    import random

    first = heuristic_order(candidates)
    second = heuristic_order(candidates)

    # Idempotent: the same input yields the same ordering every call.
    assert first == second

    # Invariant under input shuffling: order depends only on the videos.
    shuffled = list(candidates)
    random.Random(seed).shuffle(shuffled)
    assert heuristic_order(shuffled) == first

    # Sort-key precedence: each video is <= its successor under the key.
    def key(v: Video):
        return (-v.view_count, -v.like_count, v.duration, v.id)

    keys = [key(v) for v in first]
    assert keys == sorted(keys)


# --------------------------------------------------------------------------- #
# Property 3
# --------------------------------------------------------------------------- #

# Feature: study-trail-builder, Property 3: group_into_tiers partitions the
# ordered set into exactly three tiers whose concatenation in Basic ->
# Intermediate -> Advanced order equals the input, with no video dropped,
# duplicated, or added.
# Validates: Requirements 4.4
@given(candidates=_candidates_strategy())
def test_property_3_group_into_tiers_partitions_input(candidates):
    ordered = heuristic_order(candidates)
    trail = group_into_tiers(ordered)

    # Exactly three sections, one per level in order.
    assert [s.level for s in trail.sections] == LEVEL_ORDER

    # Concatenating the tiers reproduces the input order exactly (ignore the
    # level field the grouping assigns; compare by identity-bearing fields).
    flattened = _flatten(trail)
    assert [replace(v, level=None) for v in flattened] == [
        replace(v, level=None) for v in ordered
    ]

    # No loss or duplication: same multiset of ids, same count.
    assert len(flattened) == len(ordered)
    assert sorted(v.id for v in flattened) == sorted(v.id for v in ordered)


# --------------------------------------------------------------------------- #
# Property 4
# --------------------------------------------------------------------------- #

# Feature: study-trail-builder, Property 4: the Trail produced by build_trail is
# a permutation of a subset of the candidates (no invented videos); its size is
# at most the candidate count and at least ten when >= 10 candidates exist.
# Validates: Requirements 3.6
@given(candidates=_candidates_strategy())
def test_property_4_trail_is_subset_within_size_bounds(candidates):
    trail = _build_trail_no_ai("topic", candidates)
    flattened = _flatten(trail)

    candidate_ids = {v.id for v in candidates}
    trail_ids = [v.id for v in flattened]

    # No invented videos: every trail id comes from the candidate set.
    assert set(trail_ids) <= candidate_ids

    # Size upper bound: never more than the candidate count.
    assert len(flattened) <= len(candidates)

    # When at least ten candidates are available, the trail holds at least ten.
    if len(candidates) >= 10:
        assert len(flattened) >= 10


# --------------------------------------------------------------------------- #
# Property 5
# --------------------------------------------------------------------------- #

# Feature: study-trail-builder, Property 5: every trail video appears in exactly
# one Section and is assigned exactly one valid level (Basic/Intermediate/
# Advanced).
# Validates: Requirements 3.4, 6.2
@given(candidates=_candidates_strategy())
def test_property_5_each_video_exactly_one_valid_level(candidates):
    trail = _build_trail_no_ai("topic", candidates)

    seen: dict[str, int] = {}
    for section in trail.sections:
        for video in section.videos:
            # The video's level matches the section it sits in and is valid.
            assert video.level == section.level
            assert video.level in LEVEL_ORDER
            seen[video.id] = seen.get(video.id, 0) + 1

    # Each video id appears exactly once across all sections.
    assert all(count == 1 for count in seen.values())


# --------------------------------------------------------------------------- #
# Property 6
# --------------------------------------------------------------------------- #

# Feature: study-trail-builder, Property 6: flattening the Sections in order
# yields non-decreasing levels - all Basic precede all Intermediate, and all
# Intermediate precede all Advanced.
# Validates: Requirements 3.5, 6.3
@given(candidates=_candidates_strategy())
def test_property_6_trail_levels_non_decreasing(candidates):
    trail = _build_trail_no_ai("topic", candidates)
    rank = {level: index for index, level in enumerate(LEVEL_ORDER)}
    ranks = [rank[v.level] for v in _flatten(trail)]
    assert ranks == sorted(ranks)


# --------------------------------------------------------------------------- #
# Example-based view tests (task 8.2) - anchor Property 9's boundary cases.
# --------------------------------------------------------------------------- #

def _ten_candidates() -> list[Video]:
    """Ten valid candidates so build_trail yields a full three-tier trail."""
    return [
        _video(id=f"vid{n:02d}", view_count=100 - n, like_count=50 - n, duration=60 + n)
        for n in range(10)
    ]


def test_view_valid_topic_returns_200_with_three_ordered_sections(monkeypatch):
    """A valid topic -> 200 with exactly three sections ordered Basic..Advanced.

    Both the search and the builder edges are stubbed: no network and no AI are
    involved. (Req 6.1, 6.2, 6.3)
    """
    from django.test import Client

    candidates = _ten_candidates()
    monkeypatch.setattr(
        views, "search_videos", lambda topic: SearchResult(candidates, None)
    )
    monkeypatch.setattr(
        views,
        "build_trail",
        lambda topic, cands: group_into_tiers(heuristic_order(list(cands))),
    )

    client = Client()
    response = client.post(
        "/api/trail",
        data='{"topic": "limits in calculus"}',
        content_type="application/json",
    )

    assert response.status_code == 200
    body = response.json()
    assert [section["level"] for section in body["sections"]] == [
        level.value for level in LEVEL_ORDER
    ]
    total = sum(len(section["videos"]) for section in body["sections"])
    assert total == len(candidates)


@pytest.mark.parametrize(
    "topic",
    [
        "",             # empty
        "   ",          # whitespace only
        "x" * 201,      # exceeds 200 characters
    ],
)
def test_view_invalid_topic_returns_400_invalid_topic(topic):
    """Empty, whitespace-only, and over-length topics -> 400 invalid_topic.

    No stubbing needed: validation rejects these before any search. (Req 6.4,
    Property 9 boundary cases.)
    """
    import json as _json

    from django.test import Client

    client = Client()
    response = client.post(
        "/api/trail",
        data=_json.dumps({"topic": topic}),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["error"] == "invalid_topic"
