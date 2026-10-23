"""HTTP edge for the Study Trail Builder backend.

A single plain Django view, ``trail_view``, serves ``POST /api/trail``. It is
the thin edge over the pure core: it validates the Topic, orchestrates the
search and the trail builder, and serializes a Study_Trail to JSON. No Django
REST Framework is used; a single endpoint does not justify the dependency
(design: single-endpoint backend).

Responsibilities (design: ``trail/views.py`` and the REST Endpoint Contract):

1. Accept only ``POST`` and parse a JSON body ``{ "topic": str }``. Malformed
   JSON or a missing/non-string topic is rejected as ``400 invalid_topic``.
2. Validate the Topic: it must be a non-whitespace string of 1 to 200
   characters. Empty, whitespace-only, or over-length topics yield
   ``400 invalid_topic`` (Req 6.4, Property 9).
3. Run the video search. A ``search_failed`` result yields ``502 search_failed``
   (Req 2.8); zero candidates yield ``502 no_trail`` (Req 6.5).
4. Build the Study_Trail and serialize it as a ``200`` response ordered
   Basic -> Intermediate -> Advanced (Req 6.1, 6.2, 6.3).

The Learner never sees a stack trace: any unexpected failure degrades to a
clean JSON error response.
"""

from __future__ import annotations

import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .builder import build_trail
from .models_data import LEVEL_ORDER, Trail
from .search import search_videos

# Topic length bound (Req 1.1, 6.4, Property 9). A Topic must contain at least
# one non-whitespace character and at most this many characters.
MAX_TOPIC_LENGTH = 200
MIN_TOPIC_LENGTH = 1

# Human-readable detail messages for the error contract. Kept here so the view
# never leaks internal state to the Learner.
_INVALID_TOPIC_DETAIL = "Topic must be 1-200 non-whitespace characters."
_SEARCH_FAILED_DETAIL = "Could not complete the video search for this topic."
_NO_TRAIL_DETAIL = "No trail could be built for this topic."


def _error(code: str, detail: str, status: int) -> JsonResponse:
    """Build a JSON error response matching the REST error contract."""
    return JsonResponse({"error": code, "detail": detail}, status=status)


def _parse_topic(request) -> tuple[str | None, JsonResponse | None]:
    """Parse and validate the Topic from the request body.

    Returns ``(topic, None)`` on success or ``(None, error_response)`` when the
    body is malformed, the topic is missing/non-string, or the topic fails the
    length/whitespace validation (Req 6.4, Property 9). The returned topic is
    the original string (not stripped) once it is known to carry 1 to 200
    characters with at least one non-whitespace character.
    """
    # Parse the JSON body; malformed JSON is an invalid request (Req 6.4).
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None, _error("invalid_topic", _INVALID_TOPIC_DETAIL, 400)

    if not isinstance(payload, dict):
        return None, _error("invalid_topic", _INVALID_TOPIC_DETAIL, 400)

    topic = payload.get("topic")

    # The topic must be present and a string.
    if not isinstance(topic, str):
        return None, _error("invalid_topic", _INVALID_TOPIC_DETAIL, 400)

    # Reject whitespace-only topics and enforce the 1..200 length bound
    # (Req 6.4, Property 9). Length is measured on the raw topic so a topic of
    # exactly 200 characters is accepted and 201 is rejected.
    if not topic.strip():
        return None, _error("invalid_topic", _INVALID_TOPIC_DETAIL, 400)
    if not (MIN_TOPIC_LENGTH <= len(topic) <= MAX_TOPIC_LENGTH):
        return None, _error("invalid_topic", _INVALID_TOPIC_DETAIL, 400)

    return topic, None


def _serialize_trail(trail: Trail) -> dict:
    """Serialize a :class:`Trail` to the success JSON contract.

    Emits exactly three sections in ``LEVEL_ORDER`` (Basic -> Intermediate ->
    Advanced) regardless of the order the sections happen to appear in the
    Trail, so the response always satisfies Req 6.3. Each video carries its id,
    title, url, and level (Req 6.1, 6.2).
    """
    sections_by_level = {section.level: section for section in trail.sections}

    sections = []
    for level in LEVEL_ORDER:
        section = sections_by_level.get(level)
        videos = section.videos if section is not None else []
        sections.append(
            {
                "level": level.value,
                "videos": [
                    {
                        "id": video.id,
                        "title": video.title,
                        "url": video.url,
                        # A video placed in a section is assigned that level;
                        # fall back to the section's level if it is unset.
                        "level": (
                            video.level.value
                            if video.level is not None
                            else level.value
                        ),
                    }
                    for video in videos
                ],
            }
        )

    return {
        "topic": trail.topic,
        "insufficient": trail.insufficient,
        "sections": sections,
    }


@csrf_exempt
@require_POST
def trail_view(request):
    """Handle ``POST /api/trail``: topic -> grouped Study_Trail.

    ``@require_POST`` rejects any non-POST method with ``405``; ``@csrf_exempt``
    is applied because this is a stateless JSON API with no session or cookies
    (design: CORS / proxy section). The flow is validate -> search -> build ->
    serialize, with every failure mode degrading to a clean JSON error rather
    than a stack trace.
    """
    topic, error = _parse_topic(request)
    if error is not None:
        return error

    # 3. Run the bounded video search (Req 2.1). A failed or timed-out search
    #    degrades to a clean 502 rather than a stack trace (Req 2.8).
    result = search_videos(topic)
    if result.error == "search_failed":
        return _error("search_failed", _SEARCH_FAILED_DETAIL, 502)

    # Zero candidates means no trail can be produced for this valid topic
    # (Req 6.5). One to nine candidates still proceed; the trail is flagged
    # insufficient by the builder (Req 2.7, 4.6).
    if not result.candidates:
        return _error("no_trail", _NO_TRAIL_DETAIL, 502)

    # 5. Build the Study_Trail. ``build_trail`` never raises and always returns
    #    a three-section Trail (Req 4.5, 4.7); the broad guard below is defense
    #    in depth so the Learner never sees a stack trace.
    try:
        trail = build_trail(topic, result.candidates)
    except Exception:  # noqa: BLE001 - the Learner never sees a stack trace.
        return _error("no_trail", _NO_TRAIL_DETAIL, 502)

    if trail is None or not trail.sections:
        return _error("no_trail", _NO_TRAIL_DETAIL, 502)

    # 6. Serialize ordered Basic -> Intermediate -> Advanced (Req 6.1-6.3).
    return JsonResponse(_serialize_trail(trail), status=200)
