# MyClinic Booking API

A REST API for a small clinic (5 doctors) where patients view free 30-minute slots, book, cancel and reschedule appointments.

**Stack:** Python · Django REST Framework · Djoser (JWT) · PostgreSQL · Docker · GCP (Cloud Run + Cloud SQL) · GitHub Actions

| | |
| --- | --- |
| **Live URL** | <https://clinic-api-pubpakhhga-bq.a.run.app/> |
| **API docs** | <https://clinic-api-pubpakhhga-bq.a.run.app/api/docs/> |
| **Repository** | <https://github.com/Rontim/MyClinic> |
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
User (custom, Djoser)  email, role (patient | doctor | staff), is_staff (derived from role)
Patient                user (1:1), full_name, phone
Doctor                 user (1:1, required, role=doctor), full_name, specialty, is_active
WorkingHours           doctor, weekday (0=Mon..6=Sun), start_time, end_time
Appointment            doctor, patient, start_time (UTC), end_time,
                       status (booked | cancelled), cancellation_reason,
                       cancelled_by (patient | doctor | staff), cancelled_at,
                       created_at, updated_at
```

- `WorkingHours` allows multiple rows per doctor per weekday, so a lunch break is simply two intervals.
- `Appointment` carries the partial unique constraint above, plus check constraints: `end > start`, and a cancelled row must have a non-blank reason, `cancelled_by` and `cancelled_at` (a booked row must have none). Bad states can't be written even by code that bypasses the services.
- `Doctor.user` is required: doctors don't exist without a login. Staff provision a doctor in one step in Django admin (email + password + profile); the form creates the `role=doctor` user and the `Doctor` profile in the same transaction, so there is no half-created state. Staff can also reset a doctor's password from that screen. The linked user must have `role=doctor`, and a doctor's account can't be deleted while a profile points at it (set `is_active=False` instead).
- Doctors and patients use `on_delete=PROTECT` on appointments, so history is never lost by deleting a profile. Deactivate a doctor (`is_active`) instead.
- Working-hour boundaries must sit on the 30-minute grid, so slot generation and booking validation share one grid.

### Components

```
config/         settings, root urls, wsgi
accounts/       custom User (role-based), Patient profile, account endpoints (explicit allow-list)
doctors/        Doctor, WorkingHours, slots.py, availability endpoint
appointments/   Appointment, services.py, views, serializers
```

- **`slots.py`**: pure functions that generate slots from working hours and subtract booked ones. No database writes, so it is easy to unit test.
- **`services.py`**: transactional `book`, `cancel` and `reschedule` operations holding all validation and conflict handling.
- **Views**: thin. Parse input, call a service, serialize the result.

### Key decisions

1. **Time handling.** All timestamps are stored in UTC. The clinic zone is `Africa/Nairobi` (`TIME_ZONE`). Working hours are stored as clinic-local times, and the availability `date` is interpreted in clinic time. A request time without an offset is treated as clinic-local; responses are rendered in clinic time (`+03:00`).
2. **Booking validation order.** Doctor is active → start is on the 30-minute grid → slot lies entirely inside working hours → not in the past and not within the minimum lead time (`BOOKING_MIN_LEAD_MINUTES = 60`, which covers the bonus requirement) → the database constraint decides whether it is taken.
3. **Reschedule.** Runs in `transaction.atomic()` with `select_for_update()` on the appointment. It updates in place (same appointment ID, same doctor) and applies the same validation as a fresh booking. Rescheduling to the identical slot is rejected, and so is rescheduling a cancelled or already-started appointment.
4. **Cancel.** Sets `status`, `cancellation_reason`, `cancelled_by` and `cancelled_at`. A reason is required, and appointments that have already started cannot be cancelled.
5. **Who can do what.** Patients: book, view, cancel and reschedule their own appointments. Doctors: view the appointments assigned to them and cancel them, but not book or reschedule (moving a patient's slot without asking is riskier than cancelling it, which the patient must hear about either way). Staff: everything, including booking on a patient's behalf.
6. **Identity and roles.** Djoser with JWT. The patient is derived from the token, never from the request body. `User.role` (patient / doctor / staff) is the single source of truth, and Django's `is_staff` is derived from it by a `pre_save` signal so the two can't drift apart. Registration always creates a patient (`role` in the payload is ignored). Doctor and staff accounts are created by staff in Django admin, never self-registered.
7. **Status codes.** `400` the request is not acceptable (past, off-grid, outside hours, too soon, invalid body), `401` unauthenticated, `403` the role never has this action (a doctor booking) or you asked for another person's data by their id, `404` missing **or not visible to you** (so appointment ids don't leak), `409` the request is fine but conflicts with current state (slot taken, already cancelled). Every error is `{detail, code}` with a stable machine-readable code.
8. **Extra endpoints beyond the brief.** `GET /doctors/` (discover doctor ids), `GET /appointments/{id}/`, and `GET /doctors/me/appointments/` (a doctor's own schedule).

### Booking logic (how the pieces fit)

- `doctors/slots.py`: pure functions (generate slots, grid check, fits-in-hours, merge overlaps). No database, no clock.
- `appointments/services.py`: `get_availability`, `book_appointment`, `cancel_appointment`, `reschedule_appointment`. The current time is an optional `now` parameter, so service tests pass it directly; the API tests freeze the clock instead.
- **Validation is a friendly first check; the database is the guarantee.** Two requests can both pass validation for the same slot. The unique index lets one through and the other gets `409 slot_taken`. This is tested with two real threads racing for one slot.
- `cancel` and `reschedule` lock the appointment row (`SELECT ... FOR UPDATE`) inside a transaction, so concurrent changes to the same appointment are serialised. A reschedule frees the old slot and claims the new one in a single `UPDATE`; if the new slot is taken, nothing changes.
- Availability lists only slots that are actually bookable (booked, past and inside-lead-time slots are hidden), so the list and the booking rules can't disagree.

### Trade-offs considered

| Choice | Alternative | Why |
| --- | --- | --- |
| Computed slots | Pre-generated slot table | Less maintenance and flexible schedules, at the cost of slightly more logic |
| Partial unique index | Postgres exclusion constraint (`tstzrange`) | Simpler for fixed 30-minute slots. The exclusion constraint is the upgrade path for variable durations |
| Update-in-place reschedule | Cancel and create new | Stable appointment ID for patients, though history is thinner (an audit table can be added later) |
| Doctor profile separate from User (1:1, required) | Doctor as a User subclass | Keeps login concerns (Djoser, roles) apart from clinic data (specialty, working hours, appointments), and mirrors how Patient is modelled |
| Cloud Run + Cloud SQL | Docker Compose on a single VM | Managed Postgres, backups and HTTPS, and simple CI/CD, at the cost of ongoing spend |

### Growth path

Time-off and holiday exceptions, multiple clinics, variable appointment lengths, SMS/email reminders and password reset (both need email delivery), availability caching, and an appointment audit trail. None of these require reworking the core model.

---

## Section 2: API reference

Interactive docs (Swagger UI) are served at `/api/docs/`; the raw OpenAPI schema is at `/api/schema/`. All paths below are under `/api`. Everything except registration and login needs `Authorization: Bearer <access token>`.

| Method | Path | Who | Description |
| --- | --- | --- | --- |
| POST | `/auth/users/` | public | **Register** a patient (`email`, `password`, `full_name`, optional `phone`) |
| POST | `/auth/login/` | public | **Log in**, returns `access` and `refresh` tokens |
| POST | `/auth/jwt/refresh/` | public | Exchange a `refresh` token for a new `access` token |
| GET | `/auth/users/me/` | any | **Current user**: `role`, `patient_id` / `doctor_id`, `full_name`, `phone` |
| PATCH / PUT | `/auth/users/me/` | patient | **Update** own `full_name` and `phone` |
| GET | `/doctors/` | any | Active doctors (extra endpoint, so patients can discover doctor ids) |
| GET | `/doctors/{id}/availability/?date=YYYY-MM-DD` | any | **Free 30-minute slots** for a doctor on a date |
| POST | `/appointments/` | patient, staff | **Book a slot** |
| GET | `/appointments/{id}/` | participants | One appointment |
| PATCH | `/appointments/{id}/cancel/` | patient, doctor, staff | **Cancel** with a `reason` |
| PATCH | `/appointments/{id}/reschedule/` | patient, staff | **Reschedule** to a new `start_time` |
| GET | `/patients/{id}/appointments/` | patient (own), staff | **Bonus:** upcoming appointments, soonest first |
| GET | `/doctors/me/appointments/` | doctor | The doctor's own schedule (`?date=`, `?status=`) |

### Accounts

Djoser provides the account logic (registration, `me`), but its URL modules are **not** included: `accounts/urls.py` is an explicit allow-list of the five endpoints above, so there is no user listing, per-id user access, deletion, activation or password-reset surface to secure. `email` is read-only (it is the login identity and there is no email verification) and so is `role`; `PATCH /me` silently ignores them. Doctors and staff can read their profile but cannot edit it here (`403`): clinic staff manage those accounts in the admin.

### Who can do what

| | Book | View / cancel | Reschedule |
| --- | --- | --- | --- |
| Patient | own (identity from token) | own | own |
| Doctor | no | appointments assigned to them | no |
| Staff | for any patient (`patient` id required) | all | all |

- An appointment you may not see behaves as if it doesn't exist (`404 appointment_not_found`), so ids don't leak. A role that never has an action gets `403` (e.g. a doctor trying to book or reschedule).
- Asking for another person's data by their id (`/patients/{other id}/appointments/`) is `403`, whether or not that patient exists.
- Whoever cancels is recorded in `cancelled_by` (patient / doctor / staff).

### Example

```bash
# 1. register and log in
curl -X POST $URL/api/auth/users/ -H 'Content-Type: application/json' \
  -d '{"email":"jane@example.com","password":"S3cure-pass-phrase","full_name":"Jane Wanjiru"}'
TOKEN=$(curl -s -X POST $URL/api/auth/login/ -H 'Content-Type: application/json' \
  -d '{"email":"jane@example.com","password":"S3cure-pass-phrase"}' | python -c 'import sys,json;print(json.load(sys.stdin)["access"])')

# 2. see free slots, then book one
curl "$URL/api/doctors/1/availability/?date=2030-01-08" -H "Authorization: Bearer $TOKEN"
curl -X POST $URL/api/appointments/ -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"doctor": 1, "start_time": "2030-01-08T10:00:00+03:00"}'

# 3. cancel it
curl -X PATCH $URL/api/appointments/1/cancel/ -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"reason": "Feeling better"}'
```

Times are ISO 8601. A `start_time` without an offset is read as clinic-local (Nairobi) time, and responses are rendered in clinic time (`+03:00`).

**Behaviours worth knowing**

- *Availability* shows only slots that can actually be booked: booked, past and inside-the-60-minute-lead-time slots are hidden.
- *Upcoming appointments* means future and still booked; cancelled ones are excluded.
- *Doctor schedule* defaults to today onwards; `?date=` shows one day (past allowed); `?status=booked|cancelled` filters.

### Error format

Every error, including Djoser's, has one shape: a human `detail` and a stable machine `code`.

```json
{ "detail": "That slot has already been booked.", "code": "slot_taken" }
```

Invalid request bodies add per-field messages:

```json
{ "detail": "Invalid input.", "code": "validation_error", "errors": { "full_name": ["This field is required."] } }
```

| Status | Codes | Meaning |
| --- | --- | --- |
| 400 | `off_grid`, `outside_working_hours`, `slot_in_past`, `too_soon`, `doctor_inactive`, `same_slot`, `reason_required`, `validation_error` | The request is not acceptable as sent |
| 401 / 403 | `not_authenticated`, `permission_denied` | Not logged in / not allowed |
| 404 | `appointment_not_found`, `doctor_not_found`, `patient_not_found`, `not_found` | No such resource (or not visible to you) |
| 409 | `slot_taken`, `already_cancelled`, `appointment_cancelled`, `appointment_started` | Valid request, but it conflicts with the current state |

---

## Running locally

```bash
docker compose up --build        # starts Postgres + API; migrations run on startup
docker compose exec api python manage.py createsuperuser
docker compose exec api python manage.py seed_doctors --password '<strong-password>'
# 5 demo doctors, each with a login (e.g. amina.otieno@clinic.example), role=doctor and working hours.
# Idempotent. Omit --password to have a random one generated and printed once.
```

The API is at <http://localhost:8000/api/docs/>. Defaults work without a `.env`;
copy `.env.example` to `.env` only to override database credentials.

Run tests (they need Postgres, as the double-booking constraint is Postgres-specific):

```bash
docker compose exec api pytest
```

Without Docker: start any Postgres, `pip install -r requirements-dev.txt`, export
`DJANGO_DEBUG=true` and the `DB_*` variables, then run `pytest`.

---

## Section 3: Deployment and CI/CD

| | |
| --- | --- |
| **Public URL** | <https://clinic-api-pubpakhhga-bq.a.run.app/> |
| **Deploy branch** | `main` |
| **Trigger** | Merging a pull request into `main` (a push to `main`) runs the Deploy workflow. It can also be re-run by hand from the Actions tab. |

### Architecture (GCP, region `africa-south1`)

| Component | Service |
| --- | --- |
| API container | Cloud Run (`clinic-api`), scales to zero |
| Database | Cloud SQL for PostgreSQL 16, smallest shared-core tier |
| Container images | Artifact Registry, tagged with the commit SHA |
| Secrets (`DJANGO_SECRET_KEY`, DB password) | Secret Manager, injected as env vars at runtime |
| Migrations | A Cloud Run job (`clinic-migrate`) running the same image |
| GitHub to GCP login | Workload Identity Federation: no service-account keys exist anywhere |

Cloud Run reaches Cloud SQL through the built-in Cloud SQL connection (a Unix socket under `/cloudsql/...`), so no database credentials or IP allow-lists are exposed.

### What the pipeline does

**On every pull request** (`.github/workflows/ci.yml`):

1. Start a real Postgres 16 service container (the double-booking guard is a Postgres index, so SQLite would prove nothing).
2. `manage.py check`, then `makemigrations --check`, which fails if a model change is missing its migration.
3. Run the full test suite, with `DEBUG` off to mirror production.
4. In parallel, build the production Docker image, so a broken Dockerfile is caught on the PR.

**On merge to `main`** (`.github/workflows/deploy.yml`):

1. Re-run the same CI workflow. Deployment waits for it to pass.
2. Authenticate to GCP with a short-lived OIDC token (no stored credentials).
3. Build the image, tag it with the commit SHA and push it to Artifact Registry.
4. Run `manage.py migrate` as a Cloud Run job and wait for it to finish.
5. Deploy the new image to Cloud Run.
6. Smoke test: `/api/health/` must return 200 (this also proves the database connection), and `/api/doctors/` must return 401 (routes are live and auth is enforced). If either fails, the workflow fails.

Production deployments are serialised using GitHub Actions `concurrency`, with `cancel-in-progress: false` so a currently running deployment is not cancelled when a newer deployment is triggered.

### Design decisions

- **Migrations run as a separate job before the deploy**, not at container start. With several Cloud Run instances starting at once, in-container migrations would race each other and slow every cold start. The cost is that the old revision briefly runs against the new schema, so migrations must stay backward compatible (add, don't drop or rename in one step).
- **GitHub is only trusted when the workflow runs on `main` in this repository.** The Workload Identity provider rejects tokens from any other repository or branch, so a pull request cannot deploy. PR runs need no cloud credentials at all.
- **Least-privilege identities.** The running app can read two secrets and use Cloud SQL. The deployer can deploy, push images and act as the runtime identity. Neither has project owner rights.
- **Images are tagged by commit SHA**, so every deploy is traceable and a rollback is "redeploy a previous revision" (`gcloud run services update-traffic clinic-api --to-revisions=<REVISION>=100 --region africa-south1`).
- **Branch protection on `main`** (requires a PR and the `test` and `docker-build` checks) is what makes "merged" mean "reviewed and green". It is configured in the GitHub repository settings, not in code.

### Known limitations

- `DJANGO_ALLOWED_HOSTS` and the CSRF origin are pinned to the service's exact URL in `deploy.yml`. If the Cloud Run service is ever deleted and recreated, its URL changes and both values must be updated (the smoke test will fail loudly if they are wrong).
- Secrets are read when an instance starts, so rotating one needs a new revision (re-run the Deploy workflow).
- Cloud SQL runs a single zone with no high availability. Fine for this scale, and the obvious upgrade for production.
- The deployment uses trial credits and keeps billing until deleted. Teardown: delete the Cloud Run service and job, then `gcloud sql instances delete clinic-db`.

### Try the live API

Open `/api/docs/` (Swagger UI): register, call `auth/login/`, click **Authorize** with the `access` token (format `Bearer <token>`), then `GET /api/doctors/`, check availability, and book.

---

## Assumptions on ambiguous requirements

- Clinic timezone is `Africa/Nairobi`. Naive datetimes are treated as clinic-local.
- Availability excludes slots that could not be booked (in the past or within the 60-minute lead time), so the list always matches what booking will accept.
- Every appointment is exactly 30 minutes and starts on the `:00` or `:30` mark.
- Rescheduling keeps the same appointment ID and the same doctor; moving to a different doctor is a new booking.
- Reschedule checks, in order: appointment exists → not cancelled (`409`) → not already started (`409`) → the new slot passes the same rules as a fresh booking → not the current slot (`400 same_slot`) → not taken (`409`).
- Cancelling or rescheduling an appointment that has already started is rejected.
- Overlapping working-hour intervals are rejected by model validation (admin/forms), not by a database constraint. Slot generation also merges overlaps defensively, so a bypassed rule can't produce duplicate slots. Trade-off: a Postgres exclusion constraint would be airtight but needs `btree_gist` and a range expression for a time-only column; not worth the complexity for 5 doctors.
- A patient may hold overlapping appointments with different doctors (only a doctor's own slot is exclusive).
- Appointments are read-only in Django admin; changes go through the API so every rule is enforced.
- The account API is deliberately minimal (register, login, refresh, read and update `me`). There is **no password change or reset yet**, because a safe reset needs email delivery, which isn't set up. Until then a forgotten password is reset by a superuser in Django admin (staff can reset doctors' passwords from the Doctor screen). Adding email plus Djoser's reset endpoints is the natural next step.
- Doctor accounts are created by staff, never self-registered. Passwords are set by staff and handed over out of band; there is no email, so Djoser's activation and password-reset emails are off. Adding an email flow is the natural next step.
- Staff (`role=staff`) are automatically placed in a "Clinic staff" group that can manage doctors and working hours and view patients and appointments. They get no access to the raw Users admin, so they can't promote themselves or anyone else to staff or superuser; the first staff accounts and superusers are created with `createsuperuser` or by a superuser. There is no public doctor-management API.

---

## Section 4: AI reflection

### 1. What did you use AI for across the four sections?

- I used Claude as my main assistant, working step by step through the design, the API, and the deployment and CI/CD.
- For the GCP setup I also used Google Gemini to go over the deployment options and to verify the scripts before running them. Claude recommended Cloud Run with Cloud SQL once I required everything to stay inside GCP; I researched that option myself before approving it.
- I changed some parts of the code myself, and I ran the tests in my own Docker environment. I ran the GCP setup scripts and the deployment myself.
- I went through every function in the models, services and slot logic until I understood the algorithm, and I read the core tests closely.
- I took the serializers, exceptions and settings largely on trust, and reviewed the rest of the tests only partly.

### 2. One example where an AI suggestion improved my work

- **The suggestion:** enforce "only one booked appointment per doctor per start time" in the database with a partial unique index (`UNIQUE (doctor_id, start_time) WHERE status = 'booked'`), instead of checking in code and then inserting.
- **Why it is better:** with "check, then insert", two simultaneous requests can both pass the check and both book the slot. With the index, Postgres lets exactly one through and the other gets `409 slot_taken`. Cancelled appointments stay in the table for history but don't block the slot, because the index only covers booked rows.
- **How it was proved:** the AI also wrote a test in which two threads book the same slot at the same moment and asserts that exactly one succeeds. I ran it in my own environment and it passes.
- **What I prompted it with:** `Hello So today we a have a technical assessment that I want us to design and build. First I want us to design. We will use DRF, Djoser for user management, Postgres, Docker, and I have free GCP free tier. So lets go with the first step.`
- **Why the application check is not sufficient and the database constraint is better:** `Application-level "check then insert" is vulnerable to race conditions, so PostgreSQL enforces the booking invariant with a partial unique index on (doctor_id, start_time) for booked appointments.`

### 3. One example where AI output was wrong or incomplete, and how I caught it

- The AI's first design identified staff only through Django's `is_staff` flag and let a doctor exist without a login.
- That didn't match how the clinic works: users are patients, doctors or staff, and staff create doctor accounts with an email and password before the doctor's profile exists.
- **How I caught it:** `By going through the models and the design docs, I noticed that a doctor could be created without a linked user, and that is_staff was not derived from role. I also noticed that the AI's tests didn't cover the case of a doctor without a login.`
- I told the AI model to change it, and it rebuilt the models, migrations, admin and tests so that `role` is the single source of truth and every doctor has a login.
- Separately, the AI's own tests caught a crash in its error handling: every "not found" response would have returned a 500. I did not spot that one, and a second issue (an update-user endpoint that returned 200 but changed nothing) only came to light when I asked the AI to trim the account API.

### 4. Two decisions I made without AI, and why I trusted my own judgment

These are part of my design, made alongside the AI's: it proposed a starting design and I changed it where it didn't fit the clinic.

**Decision A: `role` (patient / doctor / staff) is the single source of truth, and `is_staff` is derived from it by a signal.**

- The AI first suggested dropping `role` and using only `is_staff`. I overruled it.
- Why I trusted my own judgment: `I wanted a clear separation of roles, and I wanted to avoid the risk of staff being able to promote themselves or others by changing is_staff. By deriving is_staff from role, I ensure that only the intended roles have staff privileges, and that the system's behavior is consistent and secure.`

**Decision B: doctors are provisioned by staff and never self-register, so every doctor has a login.**

- The AI first made the doctor's login optional. I changed it so staff create the account (email and password) together with the profile.
- Why I trusted my own judgment: `I wanted to ensure that all doctors have a proper login, as this is a security requirement and aligns with the clinic's workflow where staff create doctor accounts.`
