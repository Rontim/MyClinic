from django.db import connection
from django.http import JsonResponse


def health(request):
    """Liveness/readiness probe used by CI smoke tests and Cloud Run."""
    try:
        connection.ensure_connection()
    except Exception:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})
