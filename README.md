# Clinic Booking System (CBS)

Implementation Engineer take-home — Savannah Informatics.

**Stack:** Python · FastAPI · PostgreSQL · SQLAlchemy 2 · Alembic · Pytest · GitHub Actions

---

## SECTION 1 — SYSTEM DESIGN

### Scenario

> We run a small clinic with 5 doctors. Patients need to book appointments online. Each doctor has set working hours and works in 30-minute slots. A patient should see which slots are free for a given doctor on a given day, pick one, and book it. Once booked, that slot must not be available to others. Patients should also be able to cancel. We're starting small but want to grow.

### Models and components identified

```mermaid
flowchart TB
  Client["Client / API consumer"]
  API["FastAPI<br/>routes · Pydantic schemas · validation"]
  Service["Booking service<br/>working hours · slots · lifecycle"]
  DB["PostgreSQL + SQLAlchemy<br/>transactions · partial unique index"]

  Client -->|"HTTP + JSON"| API
  API --> Service
  Service --> DB
```

| Component | Role |
| --- | --- |
| `app/api/` | HTTP only — status codes and request/response |
| `app/schemas/` | Pydantic validation and serialization |
| `app/services/booking.py` | Business rules |
| `app/models/` | Tables, FKs, partial unique index |
| `tests/` | Booking behaviour against PostgreSQL |

**Growth:** the schema is not hard-capped at 5 doctors (`is_active`, seeded hours per doctor). Scaling later means more instances behind a load balancer and the same Postgres constraints — not a rewrite of booking rules.

### Models

| Model | Fields (essentials) | Notes |
| --- | --- | --- |
| **Doctor** | `id`, `full_name`, `specialty`, `is_active` | Supports more than 5 doctors later |
| **Patient** | `id`, `full_name`, `email` (unique), `phone` | Contact identity for bookings |
| **WorkingHours** | `doctor_id`, `day_of_week` (0=Mon…6=Sun), `start_time`, `end_time` | Recurring weekly windows |
| **Appointment** | `doctor_id`, `patient_id`, `start_at`, `end_at`, `status`, `cancel_reason`, timestamps | Lifecycle: `booked` \| `cancelled` |

**Slots are not stored as rows.** Availability is derived from working hours minus active (`booked`) appointments. That avoids materializing every future half-hour and stays correct when hours change.

### Business rules

1. Each appointment lasts exactly **30 minutes**.
2. Booking references an **active** doctor and an existing patient.
3. The slot must fall entirely within the doctor's working hours for that weekday.
4. Past / too-soon bookings are rejected (**60-minute lead time** — bonus rule, applied to availability and book/reschedule alike).
5. Starts must align to a 30-minute boundary (seconds/microseconds zero).
6. A doctor cannot have two **active** appointments at the same `start_at`.
7. Cancel requires a reason; status becomes `cancelled`; the slot is free again.
8. Already-cancelled appointments cannot be cancelled or rescheduled again (`409`).
9. Reschedule validates the new slot like a fresh booking; on failure the original booking stays.
10. Cancelled rows remain for auditability.

### Concurrency (critical design decision)

Checking availability in Python alone is **not** enough:

1. Patient A checks → free  
2. Patient B checks → free  
3. Both try to book  

**Approach:** validate in the service, then rely on a **PostgreSQL partial unique index** and a transaction:

```sql
CREATE UNIQUE INDEX uq_active_doctor_slot
ON appointments (doctor_id, start_at)
WHERE status = 'booked';
```

Cancelled rows do not participate, so the same wall-clock slot can be rebooked after cancel.

This index is appropriate because appointments are **fixed 30-minute aligned starts**. A unique start alone would not prevent overlapping arbitrary intervals; if durations became variable, we would use a range exclusion constraint (`EXCLUDE USING gist`) instead.

### Assumptions (ambiguities resolved)

- Working hours are recurring weekly schedules (seeded Mon–Fri 09:00–17:00).
- API uses ISO 8601 datetimes; clinic timezone is **`Africa/Nairobi`**.
- Naive datetimes in requests are treated as clinic-local; columns are `timestamptz`.
- Appointment duration is fixed at 30 minutes.
- Only `booked` appointments occupy slots.
- Auth is out of scope for this assessment.
- Reschedule keeps the same doctor.

### Trade-offs

| Choice | Why | Cost |
| --- | --- | --- |
| Derived slots | Fewer rows, hours stay flexible | Slightly more CPU per availability query |
| Partial unique index | Correct under concurrency | Assumes fixed aligned slots |
| No auth | Matches assessment scope | Would add JWT/session before production |
| Commit in API, flush in service | Clear request transactions; tests can roll back | Callers must remember to commit |

---

## SECTION 2 — API IMPLEMENTATION

Stack: **FastAPI** + **PostgreSQL** + **SQLAlchemy** + **Alembic**. Code is split across `api/`, `schemas/`, `services/`, and `models/` (not a single file).

### Required endpoints

| Method | Path | Behaviour |
| --- | --- | --- |
| `POST` | `/appointments` | Book a slot — within working hours, not in the past / inside lead time, not already taken → `201` |
| `GET` | `/doctors/{id}/availability?date=` | All free 30-minute slots for that doctor/day → `200` |
| `PATCH` | `/appointments/{id}/cancel` | Cancel with a reason; slot free again; error if already cancelled → `200` / `409` |
| `PATCH` | `/appointments/{id}/reschedule` | Move to a new validated slot; original freed; error if cancelled → `200` / `409` |

### Bonus

| Method | Path | Behaviour |
| --- | --- | --- |
| `GET` | `/patients/{id}/appointments` | Upcoming booked appointments, sorted by date |
| — | — | Reject bookings (and hide slots) within **60 minutes** of now |

### Helpers

| Method | Path | Notes |
| --- | --- | --- |
| `GET` | `/` | `{"status":"ok"}` |
| `GET` | `/health` | Liveness |
| `GET` | `/doctors` | List seeded doctors |
| `GET` | `/docs` | OpenAPI UI |

### HTTP status codes

| Status | When |
| --- | --- |
| `200` / `201` | Success |
| `400` | Business-rule failure (outside hours, lead time, bad alignment) — meaningful `detail` message |
| `404` | Doctor / patient / appointment missing |
| `409` | Slot taken, already cancelled, or invalid state transition |
| `422` | Pydantic schema validation (FastAPI default) |

### Tests

`tests/` covers booking, double-book, cancel, reschedule, availability, and concurrent booking against PostgreSQL (`pytest`).

### Examples (production)

Base URL: `https://clinic-booking-system-7j1l.onrender.com`

```bash
# Root
curl -s https://clinic-booking-system-7j1l.onrender.com/

# Availability
curl -s "https://clinic-booking-system-7j1l.onrender.com/doctors/1/availability?date=2026-10-30"

# Book
curl -s -X POST https://clinic-booking-system-7j1l.onrender.com/appointments \
  -H 'Content-Type: application/json' \
  -d '{"doctor_id":1,"patient_id":1,"start_at":"2026-10-30T10:00:00+03:00"}'

# Cancel
curl -s -X PATCH https://clinic-booking-system-7j1l.onrender.com/appointments/1/cancel \
  -H 'Content-Type: application/json' \
  -d '{"reason":"Patient requested cancellation"}'

# Reschedule
curl -s -X PATCH https://clinic-booking-system-7j1l.onrender.com/appointments/1/reschedule \
  -H 'Content-Type: application/json' \
  -d '{"start_at":"2026-10-30T11:30:00+03:00"}'
```

---

## Run locally

### Prerequisites

- **Python 3.12** (`python3.12 -m venv venv`)
- PostgreSQL (Homebrew `postgresql@16` or `docker compose up -d db`)

> Database URL must use the psycopg3 driver:  
> `postgresql+psycopg://USER:PASS@localhost:5432/clinic_booking`

```bash
cp .env.example .env   # edit DATABASE_URL
createdb clinic_booking

python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
python -m scripts.seed
uvicorn app.main:app --reload
```

```bash
pytest -v
```

Tests create/use `clinic_booking_test` on the same Postgres server.

---

## SECTION 3 — DEPLOYMENT & CI/CD

### Public URL

**Live API:** [https://clinic-booking-system-7j1l.onrender.com/](https://clinic-booking-system-7j1l.onrender.com/)

Quick checks: [`/`](https://clinic-booking-system-7j1l.onrender.com/), [`/health`](https://clinic-booking-system-7j1l.onrender.com/health), [`/docs`](https://clinic-booking-system-7j1l.onrender.com/docs), [`/doctors`](https://clinic-booking-system-7j1l.onrender.com/doctors)

### Cloud provider

- **Host:** [Render](https://render.com)
- **Web service:** Docker image from this repo (`Dockerfile` → `scripts/start.sh`)
- **Database:** Render PostgreSQL (connected via `DATABASE_URL`)
- **On boot:** `alembic upgrade head` then `python -m scripts.seed`, then Uvicorn  
  (needed because Render free compute has no web shell for one-off migrations)

### Which branch triggers a deployment, and how?

| Item | Detail |
| --- | --- |
| **Deploy branch** | `main` |
| **How** | Render is connected to the GitHub repo with **auto-deploy on `main`**. When a PR is **merged into `main`**, Render builds and deploys the new commit. |
| **CI vs CD** | GitHub Actions runs **Setup → Migrate → Test** on every PR (and on pushes to `main`). Deploy itself is handled by **Render auto-deploy**, not a separate Actions deploy job. |

Flow:

```text
feature branch → open PR → GitHub Actions (Setup / Migrate / Test)
                              ↓ (all green)
                         merge into main
                              ↓
                    Render auto-deploys production
```

### What the CI/CD pipeline does

Workflow file: [`.github/workflows/ci-cd.yml`](.github/workflows/ci-cd.yml)

| Stage | When | What it does |
| --- | --- | --- |
| **Setup** | Every PR + push to `main` | Checkout, Python 3.12, install deps, confirm app imports |
| **Migrate** | After Setup | Spin up Postgres service, run `alembic upgrade head` |
| **Test** | After Migrate | Fresh Postgres, migrations, full Pytest suite |
| **Deploy** | Merge / push to `main` | Render watches `main` and deploys automatically |

---


## SECTION 4 — AI REFLECTION

Answer the following. Bullet points are fine.

### 1. What did you use AI for across the four sections?

- **Section 1 (design):** Drafting models, business rules, trade-offs, and the concurrency story for the README.
- **Section 2 (API):** Scaffolding the FastAPI layout, SQLAlchemy models, booking service validation, Alembic migration, and Pytest fixtures/tests.
- **Section 3 (deploy/CI):** Dockerfile/start script so migrations run on boot (Render free has no shell), and splitting GitHub Actions into Setup / Migrate / Test stages.
- **Section 4 (this reflection):** Structuring honest examples from what actually broke or improved during implementation.

### 2. Give one example where an AI suggestion improved your work. What did you prompt it with?

- **Prompt (paraphrased):** how to stop two patients booking the same 30-minute slot at the same time, beyond checking availability in Python.
- **What improved:** AI suggested a PostgreSQL **partial unique index** on `(doctor_id, start_at) WHERE status = 'booked'`, on top of application validation.
- **Why it mattered:** cancelled slots can be rebooked, and concurrent inserts cannot both succeed — something a plain “check then insert” path cannot guarantee.

### 3. Give one example where AI output was wrong or incomplete and how you caught it.

- **Wrong / incomplete:** early booking code `commit()`’d inside the service layer; that broke transactional Pytest fixtures (nested savepoints) and made cancel-then-rebook tests flaky/inconsistent.
- **Also:** a test compared `start_at` as ISO strings (`+03:00` vs CI’s `Z` UTC). Same instant, different string — CI failed while local passed.
- **How I caught it:** running the suite locally and on GitHub Actions, then fixing commits to live in the API layer and comparing **datetime instants** instead of raw strings.

### 4. Name two decisions you made without AI. Why did you trust your own judgment there?

1. **Derived slots instead of storing every 30-minute row** — for five doctors this is simpler to reason about and stays correct when working hours change; I did not want a calendar table to maintain.
2. **Run `alembic upgrade` + seed on container startup** — Render’s free plan has no shell/SSH; shipping a start script was the practical way to get schema + seed data without upgrading compute.

---

## Submission readiness

| Item | Status |
| --- | --- |
| System design & assumptions in README | Done |
| Four required endpoints + bonus patient list | Done |
| DB constraint prevents double booking | Done (`uq_active_doctor_slot`) |
| Cancel / reschedule behaviour | Done |
| Automated tests for main booking rules | Done (incl. concurrent booking) |
| Public deployment + URL documented | Done — https://clinic-booking-system-7j1l.onrender.com/ |
| PRs run tests (GitHub Actions) | Done (Setup / Migrate / Test) |
| Merge to `main` auto-deploys | Done (Render auto-deploy on `main`) |
| Secrets not committed (`.env` / `.env.prod` gitignored) | Done |
| AI reflection finalized | Done |
| Git repository initialized | Done |
