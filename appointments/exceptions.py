"""
Domain errors for booking. Each carries the HTTP status and a stable machine-readable
`code`; config.exceptions turns them into {"detail": ..., "code": ...} responses.
"""


class BookingError(Exception):
    status_code = 400
    code = "booking_error"
    default_detail = "The request could not be completed."

    def __init__(self, detail: str | None = None):
        self.detail = detail or self.default_detail
        super().__init__(self.detail)


# --- 400: the request itself is not acceptable ---------------------------------------
class DoctorInactive(BookingError):
    code = "doctor_inactive"
    default_detail = "This doctor is not accepting appointments."


class OffGrid(BookingError):
    code = "off_grid"
    default_detail = "Appointments start on the hour or half hour."


class OutsideWorkingHours(BookingError):
    code = "outside_working_hours"
    default_detail = "The doctor does not work at that time."


class SlotInPast(BookingError):
    code = "slot_in_past"
    default_detail = "That time is in the past."


class TooSoon(BookingError):
    code = "too_soon"
    default_detail = "That time is too soon to book."


class SameSlot(BookingError):
    code = "same_slot"
    default_detail = "The appointment is already at that time."


class ReasonRequired(BookingError):
    code = "reason_required"
    default_detail = "A cancellation reason is required."


# --- 404 ---------------------------------------------------------------------------------
class AppointmentNotFound(BookingError):
    status_code = 404
    code = "appointment_not_found"
    default_detail = "Appointment not found."


class PatientNotFound(BookingError):
    status_code = 404
    code = "patient_not_found"
    default_detail = "Patient not found."


class DoctorNotFound(BookingError):
    status_code = 404
    code = "doctor_not_found"
    default_detail = "Doctor not found."


# --- 409: valid request, but the current state conflicts with it -----------------------
class SlotTaken(BookingError):
    status_code = 409
    code = "slot_taken"
    default_detail = "That slot has already been booked."


class AlreadyCancelled(BookingError):
    status_code = 409
    code = "already_cancelled"
    default_detail = "This appointment has already been cancelled."


class AppointmentCancelled(BookingError):
    status_code = 409
    code = "appointment_cancelled"
    default_detail = "A cancelled appointment cannot be rescheduled."


class AppointmentStarted(BookingError):
    status_code = 409
    code = "appointment_started"
    default_detail = "This appointment has already started."
