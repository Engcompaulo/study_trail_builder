"""Property tests for AI-reply parsing and graceful degradation.

Covers the pure ``parse_assignment`` function (Property 7) and the full
``build_trail`` orchestration under every AI outcome (Property 8). Per the
design's Testing Strategy these are the minimal essential tests for Req 8.2 and
Req 8.3. No network is touched: ``parse_assignment`` is exercised directly and
the AI network edge is driven by stubbing ``ai._generate`` so ``rank_and_group``
runs its real parse-and-retry logic against synthetic replies.
"""

from __future__ import annotations

import json
from unittest import mock

import pytest
from hypothesis import given
from hypothesis import strategies as st

from trail import ai
from trail.ai import parse_assignment
from trail.builder import build_trail
from trail.models_data import LEVEL_ORDER, Video

_VALID_LEVELS = [level.value for level in LEVEL_ORDER]
_ID_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"


def _video(id: str) -> Video:
    """A valid candidate Video with the given id."""
    return Video(
        id=id,
        title=f"Video {id}",
        url=f"https://www.youtube.com/watch?v={id}",
        duration=120,
        view_count=10,
        like_count=5,
    )


# --------------------------------------------------------------------------- #
# Property 7
# --------------------------------------------------------------------------- #

@st.composite
def _ids_and_reply(draw):
    """Generate a valid-id set plus a JSON reply mixing valid/invalid entries.

    The reply is a JSON object whose keys are a mix of known ids (from the valid
    set) and unknown ids, and whose values are a mix of valid levels and invalid
    level strings. This exercises the discard rules of ``parse_assignment``.
    """
    valid_ids = draw(
        st.lists(
            st.text(alphabet=_ID_ALPHABET, min_size=1, max_size=6),
            min_size=10,
            max_size=20,
            unique=True,
        )
    )
    valid_id_set = set(valid_ids)

    unknown_ids = draw(
        st.lists(
            st.text(alphabet=_ID_ALPHABET, min_size=1, max_size=6),
            min_size=0,
            max_size=10,
        ).filter(lambda ids: all(i not in valid_id_set for i in ids))
    )

    invalid_levels = st.sampled_from(["Expert", "easy", "", "123", "null"])

    reply: dict[str, str] = {}
    # Give most known ids a valid level so a usable (>=10) mapping can form.
    for vid in valid_ids:
        reply[vid] = draw(st.sampled_from(_VALID_LEVELS))
    # Sprinkle in unknown ids with arbitrary (valid or invalid) levels.
    for vid in unknown_ids:
        reply[vid] = draw(st.one_of(st.sampled_from(_VALID_LEVELS), invalid_levels))
    # Overwrite a few known ids with invalid levels to test level filtering.
    corrupt_count = draw(st.integers(min_value=0, max_value=min(3, len(valid_ids))))
    for vid in valid_ids[:corrupt_count]:
        reply[vid] = draw(invalid_levels)

    return valid_id_set, reply


# Feature: study-trail-builder, Property 7: parse_assignment keeps only known
# ids and valid levels; unknown ids and invalid levels are discarded.
# Validates: Requirements 8.2
@given(data=_ids_and_reply())
def test_property_7_parse_keeps_only_known_ids_and_valid_levels(data):
    valid_ids, reply = data
    result = parse_assignment(json.dumps(reply), valid_ids)

    # The result may be None when fewer than ten valid entries survive; in that
    # case there is nothing more to assert about its contents.
    if result is None:
        return

    for vid, level in result.items():
        # Only ids from the candidate set survive.
        assert vid in valid_ids
        # Only the three valid levels survive.
        assert level in _VALID_LEVELS


# --------------------------------------------------------------------------- #
# Property 8
# --------------------------------------------------------------------------- #

def _candidates(n: int) -> list[Video]:
    """A list of ``n`` valid candidates with unique ids."""
    return [_video(f"id{i:03d}") for i in range(n)]


def _valid_assignment_reply(candidates: list[Video]) -> str:
    """A JSON reply assigning every candidate a valid level (usable AI output)."""
    reply = {
        v.id: _VALID_LEVELS[i % len(_VALID_LEVELS)]
        for i, v in enumerate(candidates)
    }
    return json.dumps(reply)


def _missing_videos_reply(candidates: list[Video]) -> str:
    """A reply covering fewer than ten videos -> unusable, forces fallback."""
    reply = {v.id: "Basic" for v in candidates[:3]}
    return json.dumps(reply)


def _invalid_level_reply(candidates: list[Video]) -> str:
    """A reply using an invalid level for every video -> unusable."""
    reply = {v.id: "Expert" for v in candidates}
    return json.dumps(reply)


# AI outcome kinds exercised by Property 8. Each maps to a stub for
# ``ai._generate`` (the network edge) that ``rank_and_group`` will consume.
_OUTCOME_KINDS = [
    "valid",
    "none",
    "empty",
    "malformed",
    "missing_videos",
    "invalid_level",
]


def _reply_text(kind: str, candidates: list[Video]):
    """Return the synthetic ``_generate`` reply for the given AI outcome kind."""
    if kind == "valid":
        return _valid_assignment_reply(candidates)
    if kind == "none":
        return None
    if kind == "empty":
        return ""
    if kind == "malformed":
        return "{ this is not: valid json ]]"
    if kind == "missing_videos":
        return _missing_videos_reply(candidates)
    if kind == "invalid_level":
        return _invalid_level_reply(candidates)
    raise AssertionError(f"unknown outcome kind: {kind}")  # pragma: no cover


# Feature: study-trail-builder, Property 8: for any AI outcome (valid
# assignment, None, empty, malformed JSON, missing-videos, invalid-level),
# build_trail returns a three-section trail of >= 10 videos when >= 10
# candidates exist and never raises.
# Validates: Requirements 4.2, 4.5, 4.7, 8.3
@pytest.mark.parametrize("kind", _OUTCOME_KINDS)
@given(count=st.integers(min_value=10, max_value=30))
def test_property_8_graceful_degradation_always_yields_usable_trail(kind, count):
    candidates = _candidates(count)
    text = _reply_text(kind, candidates)

    # Patch the AI network edge inside the test body (not via a function-scoped
    # fixture) so Hypothesis resets it cleanly for every generated input. The
    # builder imports the ``ai`` module object, so patching ``ai._generate`` is
    # what ``rank_and_group`` actually calls.
    with mock.patch.object(ai, "_generate", lambda prompt: text):
        # Must never raise for any outcome.
        trail = build_trail("topic", candidates)

    # Exactly three sections in Basic -> Intermediate -> Advanced order.
    assert [section.level for section in trail.sections] == LEVEL_ORDER

    # At least ten videos total when at least ten candidates are available,
    # and no invented videos.
    total = sum(len(section.videos) for section in trail.sections)
    assert total >= 10
    assert total <= count

    candidate_ids = {v.id for v in candidates}
    trail_ids = {v.id for section in trail.sections for v in section.videos}
    assert trail_ids <= candidate_ids
