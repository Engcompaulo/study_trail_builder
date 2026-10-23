"""AI layer for the Study Trail Builder backend.

This module is the client for the locally hosted Ollama model. It mirrors the
engineering philosophy of the sibling Desafio 3 ``ai.py``: short prompts, a
bounded timeout, and a deterministic heuristic fallback so the backend always
produces a usable Study_Trail and never raises because of the AI service.

This file currently holds the *pure* part of the AI layer:

- ``_build_prompt`` turns a topic and its candidate videos into a short prompt
  (at most ``MAX_PROMPT_CHARS`` characters) asking the model for an id -> level
  mapping.
- ``parse_assignment`` robustly parses the model's reply into ``{id: level}``,
  keeping only known ids and valid levels and returning ``None`` for any
  unusable result so the caller can fall back to the heuristic.

The Ollama HTTP client (``_generate`` and ``rank_and_group``) lives at the end
of this module and reuses the proven request/parse shape from Desafio 3: it
guards timeouts, connection errors, non-200 responses, and malformed JSON, and
returns ``None`` on any failure so the caller can fall back to the heuristic.
"""

from __future__ import annotations

import json
import os
import re

import requests

from .models_data import LEVEL_ORDER, Level, Video

# Maximum length of the prompt sent to the model, in characters (Req 3.3).
MAX_PROMPT_CHARS = 4000

# Minimum number of assigned videos required for an AI assignment to be usable.
# Below this the caller falls back to the heuristic (Req 4.2, 8.3).
MIN_TRAIL_SIZE = 10

# The three valid difficulty levels, keyed by their lowercased name for
# case-insensitive matching of model replies.
_LEVELS_BY_NAME = {level.value.lower(): level.value for level in LEVEL_ORDER}


def _build_prompt(topic: str, candidates: list[Video]) -> str:
    """Build a short prompt asking the model to map each video id to a level.

    The prompt names the Topic and lists one line per candidate carrying the
    fields the model should reason over (id, title, duration, view_count,
    like_count), then asks for a JSON object mapping each id to one of
    ``Basic``, ``Intermediate``, or ``Advanced``.

    The result never exceeds ``MAX_PROMPT_CHARS`` characters: candidate lines
    are appended only while they fit within the budget, so a large
    Candidate_Set is truncated rather than overflowing the prompt (Req 3.3).
    """
    levels = ", ".join(level.value for level in LEVEL_ORDER)

    header = (
        "You order study videos from basic to advanced.\n"
        f"Topic: {topic}\n\n"
        "Candidate videos (one per line):\n"
    )
    footer = (
        "\nAssign every video above to exactly one difficulty level, "
        f"one of: {levels}.\n"
        "Reply with only a JSON object mapping each video id to its level, "
        'for example: {"abc123": "Basic", "def456": "Advanced"}.\n'
    )

    # Reserve room for the footer so the full prompt stays within budget.
    budget = MAX_PROMPT_CHARS - len(header) - len(footer)

    lines: list[str] = []
    for video in candidates:
        # Keep titles bounded so a single long title cannot dominate the prompt.
        title = (video.title or "").strip().replace("\n", " ")
        if len(title) > 100:
            title = title[:100].rstrip()
        line = (
            f"- id={video.id} | title={title} | duration={video.duration} "
            f"| views={video.view_count} | likes={video.like_count}\n"
        )
        if budget - len(line) < 0:
            # No more room for candidate lines without exceeding the budget.
            break
        lines.append(line)
        budget -= len(line)

    prompt = header + "".join(lines) + footer

    # Defensive hard cap: guarantee the contract even if the math above slips.
    if len(prompt) > MAX_PROMPT_CHARS:
        prompt = prompt[:MAX_PROMPT_CHARS]

    return prompt


def _normalize_level(value: object) -> str | None:
    """Return the canonical level name for ``value`` or ``None`` if invalid.

    Matching is case-insensitive and tolerant of surrounding whitespace, so a
    model reply such as ``" basic "`` maps to ``"Basic"``. Any non-string or
    unrecognized value yields ``None``.
    """
    if not isinstance(value, str):
        return None
    return _LEVELS_BY_NAME.get(value.strip().lower())


def _parse_json_object(text: str) -> dict | None:
    """Try to parse a JSON id -> level object, even if wrapped in other text.

    Returns the decoded ``dict`` on success, or ``None`` when no JSON object is
    found or it does not decode. Never raises.
    """
    # First try the whole string as JSON.
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except (ValueError, TypeError):
        pass

    # Otherwise, extract the first {...} block the model may have wrapped in prose.
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, dict):
                return data
        except (ValueError, TypeError):
            pass

    return None


def _parse_loose_lines(text: str) -> dict[str, str]:
    """Parse loose ``id: level`` / ``id -> level`` lines into a raw mapping.

    This is the lenient fallback for replies that are not valid JSON. Each line
    is scanned for an id token followed by a separator and a word; later
    occurrences of the same id overwrite earlier ones. Values are returned
    as-is (unvalidated) for the caller to filter.
    """
    result: dict[str, str] = {}
    # id can be alphanumeric with -/_ (YouTube-style ids); level is a word.
    pattern = re.compile(
        r"[\"']?([A-Za-z0-9_-]+)[\"']?\s*(?:[:=]|->|=>)\s*[\"']?([A-Za-z]+)[\"']?"
    )
    for raw_line in text.splitlines():
        for match in pattern.finditer(raw_line):
            result[match.group(1)] = match.group(2)
    return result


def parse_assignment(text: str, valid_ids: set[str]) -> dict[str, str] | None:
    """Parse a model reply into a usable ``{video_id: level}`` assignment.

    Accepts either a JSON object mapping ids to levels or loose
    ``id: level`` / ``id -> level`` lines. Only ids present in ``valid_ids``
    and only the three valid levels (Basic / Intermediate / Advanced) are kept;
    unknown ids and invalid levels are discarded (Property 7).

    Returns ``None`` when the input is unusable — not a string, empty after
    filtering, or covering fewer than ten videos — so the caller falls back to
    the heuristic (Req 8.3, Property 8). This function is pure and never raises
    on malformed input.
    """
    if not isinstance(text, str) or not text.strip():
        return None

    # Prefer a JSON object; fall back to loose line parsing.
    raw = _parse_json_object(text)
    if raw is None:
        raw = _parse_loose_lines(text)

    if not isinstance(raw, dict):
        return None

    assignment: dict[str, str] = {}
    for raw_id, raw_level in raw.items():
        if not isinstance(raw_id, str):
            continue
        video_id = raw_id.strip()
        if video_id not in valid_ids:
            continue
        level = _normalize_level(raw_level)
        if level is None:
            continue
        assignment[video_id] = level

    # Unusable if empty or if it does not cover at least ten videos (Req 4.2).
    if len(assignment) < MIN_TRAIL_SIZE:
        return None

    return assignment


# --------------------------------------------------------------------------- #
# Ollama HTTP client (task 7.2)
#
# Everything below is the network edge of the AI layer. It mirrors the proven
# request/parse structure of the sibling Desafio 3 ``ai.py``: a single bounded
# POST to the Ollama generate endpoint, every failure mode caught and turned
# into ``None`` so the orchestrator can fall back to the heuristic. These
# functions never raise (Req 4.1, 4.7).
# --------------------------------------------------------------------------- #

# Configuration via environment variables (see design / docker-compose).
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://ollama:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:1b")

# Bounded per-call timeout for a single generate request, in seconds (Req 4.1).
AI_TIMEOUT = 10

# Maximum number of retries on unusable AI output; up to 1 + MAX_RETRIES
# attempts are made in total before falling back to the heuristic (Req 3.2).
MAX_RETRIES = 1


def _generate(prompt: str) -> str | None:
    """POST a prompt to the Ollama generate endpoint and return its text.

    Returns the model's ``response`` string on success, or ``None`` on any
    failure (timeout, connection error, other request error, non-200 status,
    or malformed/missing JSON, or a non-string ``response`` field). This helper
    never raises (Req 4.1, 4.7). Mirrors Desafio 3's proven ``_generate``.
    """
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=AI_TIMEOUT,
        )
    except requests.exceptions.Timeout:
        return None
    except requests.exceptions.ConnectionError:
        return None
    except requests.exceptions.RequestException:
        return None

    if resp.status_code != 200:
        return None

    try:
        data = resp.json()
    except ValueError:
        # Malformed or missing JSON body.
        return None

    if not isinstance(data, dict):
        return None

    text = data.get("response")
    if not isinstance(text, str):
        return None

    return text


def rank_and_group(topic: str, candidates: list[Video]) -> dict[str, str] | None:
    """Ask the model to map each candidate video id to a difficulty level.

    Builds a short prompt from the Topic and Candidate_Set, calls the Ollama
    generate endpoint, and parses the reply into a ``{video_id: level}``
    assignment covering only known ids and valid levels. On unusable output
    (``None``) the call is retried up to ``MAX_RETRIES`` times, for up to
    ``1 + MAX_RETRIES`` attempts in total (Req 3.2).

    Returns the usable assignment ``dict`` or ``None`` when every attempt
    yields nothing, so the caller falls back to the heuristic. Never raises
    (Req 3.1, 4.7).
    """
    candidates = list(candidates or [])
    if not candidates:
        return None

    prompt = _build_prompt(topic, candidates)
    valid_ids = {video.id for video in candidates}

    for _ in range(1 + MAX_RETRIES):
        text = _generate(prompt)
        if text is not None:
            assignment = parse_assignment(text, valid_ids)
            if assignment is not None:
                return assignment

    return None
