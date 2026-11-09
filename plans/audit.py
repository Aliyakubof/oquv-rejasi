"""Audit logging service for tracking system changes."""

from django.core.exceptions import ValidationError
from django.core.validators import validate_ipv46_address
from django.db import models
from django.http import HttpRequest

from accounts.models import Foydalanuvchi
from plans.models import AuditAmali, AuditYozuvi


def _toza_ip(nomzod: str | None) -> str | None:
    if not nomzod:
        return None
    qiymat = nomzod.strip()
    try:
        validate_ipv46_address(qiymat)
        return qiymat
    except ValidationError:
        return None


def _sorovdan_ip(request: HttpRequest) -> str | None:
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip = _toza_ip(x_forwarded_for.split(",")[0])
        if ip is not None:
            return ip
    return _toza_ip(request.META.get("REMOTE_ADDR"))


def audit_yoz(
    amal: AuditAmali | str,
    tavsif: str,
    *,
    foydalanuvchi: Foydalanuvchi | None = None,
    obyekt: models.Model | object | None = None,
    model_nomi: str = "",
    obyekt_id: int | str = "",
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

    if request is not None:
        if (
            foydalanuvchi is None
            and hasattr(request, "user")
            and request.user.is_authenticated
        ):
            foydalanuvchi = request.user
        if ip_manzil is None:
            ip_manzil = _sorovdan_ip(request)
    else:
        ip_manzil = _toza_ip(ip_manzil)

    return AuditYozuvi.objects.create(
        foydalanuvchi=foydalanuvchi,
        amal=amal,
        model_nomi=model_nomi,
        obyekt_id=str(obyekt_id) if obyekt_id else "",
        tavsif=tavsif,
        ip_manzil=ip_manzil,
    )
