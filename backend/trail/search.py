"""Video_Searcher for the Study Trail Builder backend.

This module wraps ``yt-dlp`` to search YouTube for videos related to a Topic
without any API key. It follows the design's "pure core, thin edges" principle:

- ``_normalize`` is a *pure* function that maps a single raw ``yt-dlp`` entry to
  a :class:`Video`, dropping entries that are missing a title, a URL, or a
  positive duration (Req 2.3, 2.6). It is the subject of Correctness Property 1.
- ``search_videos`` is the thin network edge. It runs ``yt-dlp`` with a
  ``ytsearchN:`` query, normalizes the raw entries, drops the invalid ones, and
  returns a :class:`SearchResult`. All network and ``yt-dlp`` behavior is
  isolated here; any failure or timeout yields ``SearchResult([], "search_failed")``
  (Req 2.1, 2.8) so the caller never has to handle an exception.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

from .models_data import SearchResult, Video

# Request more than ten results so that dropping invalid entries during
# normalization still leaves at least ten candidates (Req 2.6).
SEARCH_COUNT = 15

# Hard upper bound on the search, in seconds (Req 2.1). The search must never
# exceed this; it is enforced both as a yt-dlp socket timeout and as a
# wall-clock guard around the extraction call.
SEARCH_TIMEOUT = 30


def _normalize(entry: dict) -> Video | None:
    """Map a raw ``yt-dlp`` entry to a :class:`Video`, or ``None`` if invalid.

    An entry is considered valid only when it carries a non-empty title, a
    resolvable non-empty URL, and a duration greater than zero seconds. Any
    entry missing one of these is excluded from the Candidate_Set by returning
    ``None`` (Req 2.3, 2.6).

    The view count and like count are optional: when absent they default to
    ``0`` (Req 2.4, 2.5). The video ``id`` is taken from the stable ``yt-dlp``
    ``id`` field; the URL is read from ``webpage_url`` or ``url`` and, failing
    that, is constructed from the id as a canonical YouTube watch URL.

    This function is pure: it performs no I/O and never raises on malformed
    input.
    """
    if not isinstance(entry, dict):
        return None

    # Title must be present and non-empty after trimming.
    title = entry.get("title")
    if not isinstance(title, str):
        return None
    title = title.strip()
    if not title:
        return None

    # A stable id is used as the final tie-break in heuristic ordering (Req 4.3)
    # and to construct a URL when yt-dlp does not expose one directly.
    raw_id = entry.get("id")
    video_id = str(raw_id).strip() if raw_id is not None else ""

    # Resolve the URL from webpage_url, then url, then construct it from the id.
    url = _resolve_url(entry, video_id)
    if not url:
        return None

    # Duration must be a positive number of seconds (Req 2.6).
    duration = _coerce_positive_int(entry.get("duration"))
    if duration is None:
        return None

    view_count = _coerce_non_negative_int(entry.get("view_count"))
    like_count = _coerce_non_negative_int(entry.get("like_count"))

    return Video(
        id=video_id,
        title=title,
        url=url,
        duration=duration,
        view_count=view_count,
        like_count=like_count,
    )


def _resolve_url(entry: dict, video_id: str) -> str:
    """Return a usable URL for the entry, or an empty string if none can be formed.

    Prefers ``webpage_url``, then a non-empty ``url`` field. When neither is a
    usable string but a video id is available, a canonical YouTube watch URL is
    constructed from the id.
    """
    for key in ("webpage_url", "url"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    if video_id:
        return f"https://www.youtube.com/watch?v={video_id}"

    return ""


def _coerce_positive_int(value: object) -> int | None:
    """Coerce ``value`` to a positive ``int``, or ``None`` if not possible.

    Accepts ints and floats (and numeric strings). Returns ``None`` for missing,
    non-numeric, zero, or negative values so the caller can drop the entry.
    """
    number = _coerce_number(value)
    if number is None:
        return None
    result = int(number)
    return result if result > 0 else None


def _coerce_non_negative_int(value: object) -> int:
    """Coerce ``value`` to a non-negative ``int``, defaulting to ``0``.

    Used for the optional ``view_count`` and ``like_count`` fields: absent,
    non-numeric, or negative values all collapse to ``0`` (Req 2.4, 2.5).
    """
    number = _coerce_number(value)
    if number is None:
        return 0
    result = int(number)
    return result if result > 0 else 0


def _coerce_number(value: object) -> float | None:
    """Return ``value`` as a ``float``, or ``None`` when it is not numeric."""
    if isinstance(value, bool):
        # bool is a subclass of int; treat it as non-numeric for our purposes.
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _extract_entries(topic: str) -> list[dict]:
    """Run ``yt-dlp`` for the Topic and return the raw search entries.

    This is the only place that imports and drives ``yt-dlp``. It uses a flat
    extraction (``extract_flat=True``) so entries are returned quickly with
    their lightweight metadata and without downloading or fully resolving each
    video, keeping the search well within its time bound (Req 2.1).
    """
    # Imported lazily so that the pure helpers in this module (and their tests)
    # do not require yt-dlp to be installed.
    from yt_dlp import YoutubeDL

    options = {
        "extract_flat": True,
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "ignoreerrors": True,
        "socket_timeout": SEARCH_TIMEOUT,
    }

    query = f"ytsearch{SEARCH_COUNT}:{topic}"
    with YoutubeDL(options) as ydl:
        info = ydl.extract_info(query, download=False)

    if not isinstance(info, dict):
        return []
    entries = info.get("entries")
    if not entries:
        return []
    return [entry for entry in entries if isinstance(entry, dict)]


def search_videos(topic: str) -> SearchResult:
    """Search YouTube for the Topic and return a :class:`SearchResult`.

    Runs ``yt-dlp`` with a ``ytsearch{SEARCH_COUNT}:<topic>`` query, normalizes
    each raw entry with :func:`_normalize`, and drops the invalid ones so every
    returned :class:`Video` has a non-empty title, a non-empty URL, and a
    positive duration (Req 2.2, 2.3, 2.6).

    The whole operation is bounded by :data:`SEARCH_TIMEOUT` using both a
    ``yt-dlp`` socket timeout and a wall-clock guard, so it cannot hang. On any
    ``yt-dlp`` failure, exception, or timeout it returns
    ``SearchResult([], "search_failed")`` instead of raising (Req 2.1, 2.8).
    """
    try:
        # Wall-clock guard: enforce the search bound even if yt-dlp's own
        # socket timeout does not fire (for example, a slow in-process loop).
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_extract_entries, topic)
            entries = future.result(timeout=SEARCH_TIMEOUT)
    except FutureTimeoutError:
        return SearchResult(candidates=[], error="search_failed")
    except Exception:
        # Any yt-dlp / network failure degrades to a clean search-failure
        # result so the view can return a 502 without a stack trace (Req 2.8).
        return SearchResult(candidates=[], error="search_failed")

    candidates: list[Video] = []
    for entry in entries:
        video = _normalize(entry)
        if video is not None:
            candidates.append(video)

    return SearchResult(candidates=candidates, error=None)
