# Study Trail Builder

Turn any study topic into an ordered, beginner-to-advanced learning trail of
YouTube videos. Type a topic (for example, `limits in calculus`) and get back at
least ten videos, sequenced and grouped into **Basic**, **Intermediate**, and
**Advanced**, each shown as a title next to its link.

Built for the Hacktoberfest "Slow and Steady" open-source AI challenge. See
[`SUBMISSION.md`](./SUBMISSION.md) for the full write-up.

## Stack

- **Backend:** Django + gunicorn, a single `POST /api/trail` endpoint.
- **Video search:** `yt-dlp` — keyless YouTube search, no API key required.
- **AI core:** Ollama running the open-weight `llama3.2:1b` model locally. It
  orders the candidate videos and assigns each a difficulty level. Every AI call
  is bounded by a 10-second timeout with a deterministic heuristic fallback, so
  the app never fails just because the model is slow or down.
- **Frontend:** Angular (standalone) served by nginx, which reverse-proxies
  `/api/*` to the backend (same-origin, no CORS).
- **Orchestration:** Docker Compose, three services, developed under WSL.

## Prerequisites

- Docker and Docker Compose (run under WSL on Windows).

## Run it with Docker

From the `desafio4/` directory:

```bash
# 1. Build and start all three services (frontend, backend, ollama)
docker compose up --build

# 2. In a second terminal, pull the model into the ollama service
#    (one time only; cached on the ollama_data volume afterwards)
docker compose exec ollama ollama pull llama3.2:1b

# 3. Open the app
#    http://localhost:8080
```

The model download in step 2 is a **one-time** operation. It is cached on the
`ollama_data` named volume and survives restarts, so you only pull it once.

To stop the stack:

```bash
docker compose down          # stop and remove the containers
docker compose down -v       # also remove the ollama_data volume (re-pull needed)
```

## Services and ports

| Port    | Service            | Notes                                               |
| ------- | ------------------ | --------------------------------------------------- |
| `8080`  | frontend (nginx)   | Open this in a browser: `http://localhost:8080`.    |
| `8000`  | backend (gunicorn) | Published for debugging; nginx proxies it internally.|
| `11434` | ollama             | The AI service; the backend talks to it internally. |

## Configuration

The defaults work for a standard local run; none of these need to change. They
are set on the `backend` service in `docker-compose.yml`.

| Setting        | Default                 | Purpose                                          |
| -------------- | ----------------------- | ------------------------------------------------ |
| `OLLAMA_URL`   | `http://ollama:11434`   | URL of the Ollama service in the compose network.|
| `OLLAMA_MODEL` | `llama3.2:1b`           | The open-weight model used to order and group.   |

## Local development (without Docker)

Backend (Django):

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py runserver 0.0.0.0:8000
```

Frontend (Angular):

```bash
cd frontend
npm install
npm start            # ng serve on http://localhost:4200
```

For local cross-origin development, the backend allows `http://localhost:4200`
via `CORS_ALLOWED_ORIGINS`. Point the frontend at the backend accordingly, and
make sure an Ollama instance is reachable at `OLLAMA_URL` (or rely on the
heuristic fallback).

## Tests

Minimal, essential tests only (property tests for the heuristic fallback and the
AI-reply parsing, plus two example-based view tests):

```bash
cd backend
pip install -r requirements.txt
pytest -q
```
