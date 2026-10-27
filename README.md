# Clinic Booking System (CBS)

Implementation Engineer take-home — Savannah Informatics.

**Stack:** Python · FastAPI · PostgreSQL · SQLAlchemy 2 · Alembic · Pytest · GitHub Actions

---

## Section 1 — System design

### Scenario

A small clinic with 5 doctors. Patients book **30-minute slots** online within each doctor's working hours, cancel with a reason, or reschedule. Once booked, a slot must not be available to others — including under concurrent requests.

### Architecture

```
Client / API consumer
        ↓  HTTP + JSON
FastAPI (routes · Pydantic schemas · validation)
        ↓
Booking service (working hours · slot rules · lifecycle)
        ↓
SQLAlchemy + PostgreSQL (transactions · partial unique index · persistence)
```

| Layer | Role |
| --- | --- |
| `app/api/` | HTTP only — status codes and request/response |
| `app/schemas/` | Pydantic validation and serialization |
| `app/services/booking.py` | Business rules |
| `app/models/` | Tables, FKs, partial unique index |
| `tests/` | Booking behaviour against PostgreSQL |

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

## Section 2 — API

| Method | Path | Success |
| --- | --- | --- |
| `POST` | `/appointments` | `201` |
| `GET` | `/doctors/{id}/availability?date=YYYY-MM-DD` | `200` |
| `PATCH` | `/appointments/{id}/cancel` | `200` |
| `PATCH` | `/appointments/{id}/reschedule` | `200` |
| `GET` | `/patients/{id}/appointments` | `200` (bonus) |
| `GET` | `/doctors` | `200` (helper) |
| `GET` | `/health` | `200` |

| Status | When |
| --- | --- |
| `200` / `201` | Success |
| `400` | Business-rule failure (outside hours, lead time, bad alignment) |
| `404` | Doctor / patient / appointment missing |
| `409` | Slot taken, already cancelled, or invalid state transition |
| `422` | Pydantic schema validation (FastAPI default) |

Interactive docs: `http://localhost:8000/docs`

### Examples

```bash
# Book
curl -s -X POST http://localhost:8000/appointments \
  -H 'Content-Type: application/json' \
  -d '{"doctor_id":1,"patient_id":1,"start_at":"2026-10-28T10:00:00+03:00"}'

# Availability
curl -s "http://localhost:8000/doctors/1/availability?date=2026-10-28"

# Cancel
curl -s -X PATCH http://localhost:8000/appointments/1/cancel \
  -H 'Content-Type: application/json' \
  -d '{"reason":"Patient requested cancellation"}'

# Reschedule
curl -s -X PATCH http://localhost:8000/appointments/1/reschedule \
  -H 'Content-Type: application/json' \
  -d '{"start_at":"2026-10-28T11:30:00+03:00"}'
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

## Section 3 — Deployment & CI/CD

**Public URL:** _add after deploy (e.g. Render)_

**CI:** `.github/workflows/ci-cd.yml`

| Trigger | Action |
| --- | --- |
| Pull request → `main` | Postgres service · Alembic · Pytest |
| Push / merge → `main` | Same tests; **deploy job still stubbed** — wire Render/Railway/Fly + secrets |

Checklist for Section 3:

- [ ] GitHub remote + public or shared repo
- [ ] Cloud Postgres + API deploy
- [ ] Migrations on deploy
- [ ] Auto-deploy on merge to `main` enabled and verified
- [ ] Document public URL here

---

## Section 4 — AI reflection

_Replace with your honest answers before submission._

1. **What I used AI for** — scaffolding FastAPI layout, models, booking validation, Alembic, pytest fixtures, and README wording.
2. **Where AI improved the work** — reviewing race conditions and recommending a partial unique index in addition to application checks.
3. **Where AI was wrong** — early suggestion to `commit()` inside the service broke transactional tests; commits moved to the API layer.
4. **Decisions without AI** — derived slots vs slot table; keeping cancelled rows for audit while freeing the slot via the partial index.

---

## Submission readiness

| Item | Status |
| --- | --- |
| System design & assumptions in README | Done |
| Four required endpoints + bonus patient list | Done |
| DB constraint prevents double booking | Done (`uq_active_doctor_slot`) |
| Cancel / reschedule behaviour | Done |
| Automated tests for main booking rules | Done (incl. concurrent booking) |
| Public deployment + URL documented | **Todo** |
| PRs run tests (GitHub Actions) | Workflow ready; needs git remote |
| Merge to `main` auto-deploys | **Todo** (stub in workflow) |
| Secrets not committed (`.env` gitignored) | Done |
| AI reflection finalized | **Todo** (edit Section 4) |
| Git repository initialized | **Todo** (`git init` / push) |

---

## Interview talking points (quick)

1. **Why FastAPI?** Fast validation (Pydantic), clear OpenAPI docs, good fit for a focused REST API.
2. **Double booking?** Service validation + partial unique index + transaction; never trust a prior availability read alone.
3. **Failed reschedule?** Validate new slot first; mutate only if valid; on conflict return `409` and leave original `start_at`.
4. **Availability?** Generate 30-minute intervals from working hours for the date, drop booked starts and slots inside the lead window.
5. **Transaction vs constraint?** Transaction = atomic unit of work; constraint = invariant the DB enforces even under concurrency.
6. **Scale?** Derived slots fine for hundreds of doctors/day; add caching, indexes on `(doctor_id, start_at)`, later optional materialization or sharding by clinic.
