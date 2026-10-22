# MyClinic API

A REST API for a small clinic (5 doctors) where patients view free 30-minute slots, book, cancel and reschedule appointments.

**Stack:** Python · Django REST Framework · Djoser (JWT) · PostgreSQL · Docker · GCP (Cloud Run + Cloud SQL) · GitHub Actions

| | |
| --- | --- |
| **Live URL** | `TODO: https://<cloud-run-url>` |
| **API docs** | `TODO: https://<cloud-run-url>/api/docs/` |
| **Repository** | `https://github.com/Rontim/myclinic-api` |
| **Deploy branch** | `main` |

## Contents

1. [Section 1: System design](#section-1-system-design)
2. [Section 2: API reference](#section-2-api-reference)
3. [Running locally](#running-locally)
4. [Section 3: Deployment and CI/CD](#section-3-deployment-and-cicd)
5. [Assumptions on ambiguous requirements](#assumptions-on-ambiguous-requirements)
6. [Section 4: AI reflection](#section-4-ai-reflection)

---

## Section 1: System design

### Core ideas

**1. Slots are computed, not stored.**
A doctor has weekly working hours. When availability is requested, the service generates the 30-minute slots for that date and subtracts the booked appointments. Only appointments are persisted.
There is no slot table to keep in sync, and schedule changes apply immediately. The cost is a small amount of computation per availability request, which is negligible at this scale.

**2. The database, not the application, prevents double booking.**
An application-level "check, then insert" has a race: two requests can both see the slot as free. Instead, Postgres enforces a partial unique index:

```sql
UNIQUE (doctor_id, start_time) WHERE status = 'booked'
```

The service catches `IntegrityError` and returns `409 Conflict`. Cancelled rows are kept for history, and the slot frees up automatically because the index only covers `booked` rows.

### Models

```
User (custom, Djoser)  email, role (patient | staff)
Patient                user (1:1), full_name, phone
Doctor                 full_name, specialty, is_active
WorkingHours           doctor, weekday (0=Mon..6=Sun), start_time, end_time
Appointment            doctor, patient, start_time (UTC), end_time,
                       status (booked | cancelled), cancellation_reason,
                       cancelled_at, created_at, updated_at
```

- `WorkingHours` allows multiple rows per doctor per weekday, so a lunch break is simply two intervals.
- `Appointment` carries the partial unique constraint above.

### Components

```
config/         settings, root urls, wsgi
accounts/       custom User, Patient profile, Djoser configuration
doctors/        Doctor, WorkingHours, slots.py, availability endpoint
appointments/   Appointment, services.py, views, serializers
```

- **`slots.py`**: pure functions that generate slots from working hours and subtract booked ones. No database writes, so it is easy to unit test.
- **`services.py`**: transactional `book`, `cancel` and `reschedule` operations holding all validation and conflict handling.
- **Views**: thin. Parse input, call a service, serialize the result.

### Key decisions

1. **Time handling.** All timestamps are stored in UTC. The clinic zone is `Africa/Nairobi` (`TIME_ZONE`). Working hours are stored as clinic-local times, and the availability `date` is interpreted in clinic time. Naive datetimes in requests are treated as clinic-local.
2. **Booking validation order.** Doctor exists and is active → start is on the 30-minute grid → slot lies entirely inside working hours → not in the past and not within the minimum lead time (`BOOKING_MIN_LEAD_MINUTES = 60`) → DB constraint decides whether it is taken.
3. **Reschedule.** Runs in `transaction.atomic()` with `select_for_update()` on the appointment. It updates in place (same appointment ID) and applies the same validation as a fresh booking. Rescheduling to the identical slot is rejected.
4. **Cancel.** Sets `status`, `cancellation_reason` and `cancelled_at`. Appointments that have already started cannot be cancelled.
5. **Auth and permissions.** Djoser with JWT. The patient is derived from the token, never from the request body. Patients can view and modify only their own appointments; staff can access all. Doctors and working hours are managed through Django admin.
6. **Status codes.** `400` validation (past, off-grid, outside hours, too soon), `401` unauthenticated, `403` ownership violation, `404` missing resource, `409` state conflict (slot taken, already cancelled).
7. **Extra endpoint.** `GET /doctors` lets patients discover doctor IDs.

### Trade-offs considered

| Choice | Alternative | Why |
| --- | --- | --- |
| Computed slots | Pre-generated slot table | Less maintenance and flexible schedules, at the cost of slightly more logic |
| Partial unique index | Postgres exclusion constraint (`tstzrange`) | Simpler for fixed 30-minute slots. The exclusion constraint is the upgrade path for variable durations |
| Update-in-place reschedule | Cancel and create new | Stable appointment ID for patients, though history is thinner (an audit table can be added later) |
| Doctor separate from User | Doctor as a User | Fewer moving parts now. An optional link to User can be added when doctors need logins |
| Cloud Run + Cloud SQL | Docker Compose on a single VM | Managed Postgres, backups and HTTPS, and simple CI/CD, at the cost of ongoing spend |

### Growth path

Time-off and holiday exceptions, multiple clinics, variable appointment lengths, SMS/email reminders, doctor logins, availability caching, and an appointment audit trail. None of these require reworking the core model.

---

## Section 2: API reference

> TODO: fill in with request/response examples once implemented.

| Method | Path | Description | Auth |
| --- | --- | --- | --- |
| POST | `/api/auth/users/` | Register (Djoser) | Public |
| POST | `/api/auth/jwt/create/` | Obtain JWT | Public |
| GET | `/api/doctors/` | List active doctors | Authenticated |
| GET | `/api/doctors/{id}/availability/?date=YYYY-MM-DD` | Free 30-minute slots for a doctor on a date | Authenticated |
| POST | `/api/appointments/` | Book a slot | Patient |
| PATCH | `/api/appointments/{id}/cancel/` | Cancel with a reason | Owner / staff |
| PATCH | `/api/appointments/{id}/reschedule/` | Move to a new slot | Owner / staff |
| GET | `/api/patients/{id}/appointments/` | Upcoming appointments sorted by date (bonus) | Owner / staff |

### Error format

```json
{ "detail": "Human-readable message", "code": "slot_taken" }
```

---

## Running locally

> TODO: confirm commands once the scaffold exists.

```bash
cp .env.example .env
docker compose up --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py seed_doctors
```

Run tests (requires Postgres, as the double-booking constraint is Postgres-specific):

```bash
docker compose exec web pytest
```

---

## Section 3: Deployment and CI/CD

### Target architecture (GCP)

| Component | Service |
| --- | --- |
| API container | Cloud Run |
| Database | Cloud SQL for PostgreSQL (smallest suitable tier) |
| Container images | Artifact Registry |
| Secrets (`SECRET_KEY`, DB password) | Secret Manager |
| CI → GCP auth | Workload Identity Federation (no long-lived service account keys) |

### Pipeline (GitHub Actions)

**On every pull request:** start a Postgres service container, install dependencies, run the test suite (and linting).

**On merge to `main`:**

1. Run the tests again.
2. Authenticate to GCP via Workload Identity Federation.
3. Build the Docker image and push it to Artifact Registry, tagged with the commit SHA.
4. Run database migrations as a Cloud Run Job using the new image.
5. Deploy the new revision to Cloud Run.
6. Smoke-test the health endpoint.

Branch protection on `main` requires the PR checks to pass before merging.

---

## Assumptions on ambiguous requirements

- Clinic timezone is `Africa/Nairobi`. Naive datetimes are treated as clinic-local.
- Availability excludes slots that could not be booked (in the past or within the 60-minute lead time), so the list always matches what booking will accept.
- Every appointment is exactly 30 minutes and starts on the `:00` or `:30` mark.
- Rescheduling keeps the same appointment ID.
- Cancelling or rescheduling an appointment that has already started is rejected.
- Doctors are managed by staff via Django admin. There is no public doctor-management API.

---

## Section 4: AI reflection

1. **What did you use AI for across the four sections?**
   - TODO

2. **One example where an AI suggestion improved your work. What did you prompt it with?**
   - TODO

3. **One example where AI output was wrong or incomplete, and how you caught it.**
   - TODO

4. **Two decisions you made without AI, and why you trusted your own judgment.**
   - TODO
