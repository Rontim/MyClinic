"""One error shape for the whole API:

    {"detail": "<human message>", "code": "<stable_machine_code>"}

Invalid request bodies add the per-field messages:

    {"detail": "Invalid input.", "code": "validation_error", "errors": {"field": ["..."]}}
"""
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions as drf_exceptions
from rest_framework.response import Response
from rest_framework.views import exception_handler

from appointments.exceptions import BookingError


def _code(exc: Exception) -> str:
    if isinstance(exc, Http404):
        return "not_found"
    if isinstance(exc, DjangoPermissionDenied):
        return "permission_denied"
    codes = exc.get_codes()
    return codes if isinstance(codes, str) else exc.default_code


def api_exception_handler(exc, context):
    if isinstance(exc, BookingError):
        return Response({"detail": exc.detail, "code": exc.code}, status=exc.status_code)

    # DRF's default: handles APIException, Http404, PermissionDenied
    response = exception_handler(exc, context)
    if response is None:
        return None

    data = response.data
    if isinstance(exc, drf_exceptions.ValidationError):
        errors = {"non_field_errors": data} if isinstance(data, list) else data
        response.data = {"detail": "Invalid input.",
                         "code": "validation_error", "errors": errors}
    elif isinstance(data, dict) and "detail" in data:
        data.setdefault("code", _code(exc))
    return response
