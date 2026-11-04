"""Audit logging service for tracking system changes."""

from typing import Any

from django.http import HttpRequest

from accounts.models import Foydalanuvchi
from plans.models import AuditAmali, AuditYozuvi


def audit_yoz(
    amal: AuditAmali | str,
    tavsif: str,
    *,
    foydalanuvchi: Foydalanuvchi | None = None,
    model_nomi: str = "",
    obyekt_id: Any = "",
    request: HttpRequest | None = None,
) -> AuditYozuvi:
    """Record an audit trail event."""
    ip_manzil = None
    if request is not None:
        if (
            foydalanuvchi is None
            and hasattr(request, "user")
            and request.user.is_authenticated
        ):
            foydalanuvchi = request.user
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip_manzil = x_forwarded_for.split(",")[0].strip()
        else:
            ip_manzil = request.META.get("REMOTE_ADDR")

    return AuditYozuvi.objects.create(
        foydalanuvchi=foydalanuvchi,
        amal=amal,
        model_nomi=model_nomi,
        obyekt_id=str(obyekt_id) if obyekt_id else "",
        tavsif=tavsif,
        ip_manzil=ip_manzil,
    )
