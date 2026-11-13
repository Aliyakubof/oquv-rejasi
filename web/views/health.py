"""Health check endpoint verifying database and cache availability."""

import uuid

from django.core.cache import cache
from django.db import connection
from django.http import HttpRequest, JsonResponse


def _baza_tekshir() -> bool:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return True
    except Exception:
        return False


def _kesh_tekshir() -> bool:
    kalit = f"health:{uuid.uuid4().hex}"
    try:
        cache.set(kalit, "ok", timeout=10)
        qiymat = cache.get(kalit)
        cache.delete(kalit)
        return qiymat == "ok"
    except Exception:
        return False


def healthcheck(request: HttpRequest) -> JsonResponse:
    """Return 200 when database and cache respond, 503 otherwise."""
    db_ok = _baza_tekshir()
    kesh_ok = _kesh_tekshir()
    hammasi_ok = db_ok and kesh_ok
    return JsonResponse(
        {
            "status": "ok" if hammasi_ok else "degraded",
            "db": "ok" if db_ok else "error",
            "cache": "ok" if kesh_ok else "error",
        },
        status=200 if hammasi_ok else 503,
    )
