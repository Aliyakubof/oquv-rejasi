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
    obyekt: Any | None = None,
    model_nomi: str = "",
    obyekt_id: Any = "",
    ip_manzil: str | None = None,
    request: HttpRequest | None = None,
) -> AuditYozuvi:
    """Record an audit trail event.

    Supports passing an `obyekt` directly to auto-derive `model_nomi` and `obyekt_id`,
    as well as passing `ip_manzil` directly or resolving it from `request`.
    """
    if obyekt is not None:
        if not model_nomi:
            model_nomi = getattr(obyekt, "__class__", type(obyekt)).__name__
        if not obyekt_id:
            obyekt_id = getattr(obyekt, "pk", getattr(obyekt, "id", ""))

    if ip_manzil is None and request is not None:
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
