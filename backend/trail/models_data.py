"""Plain data models for the Study Trail Builder backend.

These are plain Python dataclasses and a string Enum only. There is no Django
ORM here: trails are computed per request and never persisted. The shapes below
mirror the "Data Models" section of the design document and form the contract
shared by the search, heuristic, AI, builder, and view modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Level(str, Enum):
    """The three ordered difficulty tiers a Video can be assigned to."""

    BASIC = "Basic"
    INTERMEDIATE = "Intermediate"
    ADVANCED = "Advanced"


# Ascending difficulty order: Basic -> Intermediate -> Advanced (Req 3.5).
LEVEL_ORDER = [Level.BASIC, Level.INTERMEDIATE, Level.ADVANCED]


@dataclass(frozen=True)
class Video:
    """A single candidate video record extracted from the search results."""

    id: str            # stable identifier from yt-dlp (used for tie-break, Req 4.3)
    title: str         # non-empty, 1-300 chars in output (Req 2.6, 6.2)
    url: str           # non-empty YouTube URL (Req 2.6, 6.2)
    duration: int      # seconds, > 0 (Req 2.6)
    view_count: int    # non-negative; 0 when absent (Req 2.4)
    like_count: int    # non-negative; 0 when absent (Req 2.5)
    level: Level | None = None  # assigned during trail building (Req 3.4)


@dataclass
class SearchResult:
    """The outcome of a video search: the Candidate_Set plus an optional error."""

    candidates: list[Video]  # the Candidate_Set
    error: str | None        # "search_failed" when the search could not complete


@dataclass
class Section:
    """One difficulty tier of a Trail. Its video list may be empty (Req 5.5)."""

    level: Level
    videos: list[Video]


@dataclass
class Trail:
    """A grouped Study_Trail: exactly three Sections in LEVEL_ORDER (Req 5.1, 6.3)."""

    topic: str
    sections: list[Section]  # exactly 3, in LEVEL_ORDER
    insufficient: bool       # True when fewer than 10 videos available (Req 4.6)
