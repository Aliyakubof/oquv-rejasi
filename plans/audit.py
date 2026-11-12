"""Audit logging service for tracking system changes."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_ipv46_address
from django.db import models
from django.http import HttpRequest

from accounts.models import Foydalanuvchi
from plans.models import AuditAmali, AuditYozuvi

_MODEL_NOMI_MAX = 60
_OBYEKT_ID_MAX = 64


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
    remote_ip = _toza_ip(request.META.get("REMOTE_ADDR"))
    if not getattr(settings, "TRUST_X_FORWARDED_FOR", False):
        return remote_ip
    ishonchli_proksilar = {
        ip.strip() for ip in getattr(settings, "TRUSTED_PROXY_IPS", ()) if ip.strip()
    }
    if ishonchli_proksilar and remote_ip not in ishonchli_proksilar:
        return remote_ip
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        for qism in reversed(x_forwarded_for.split(",")):
            ip = _toza_ip(qism)
            if ip is not None and ip not in ishonchli_proksilar:
                return ip
    return remote_ip


def _obyekt_meta(
    obyekt: models.Model | object | None,
    model_nomi: str,
    obyekt_id: int | str | None,
) -> tuple[str, str]:
    if obyekt is not None:
        if not model_nomi:
            model_nomi = getattr(obyekt, "__class__", type(obyekt)).__name__
        if obyekt_id is None or obyekt_id == "":
            obyekt_id = getattr(obyekt, "pk", getattr(obyekt, "id", ""))
    obyekt_matni = str(obyekt_id) if obyekt_id is not None and obyekt_id != "" else ""
    return model_nomi[:_MODEL_NOMI_MAX], obyekt_matni[:_OBYEKT_ID_MAX]


def audit_yoz(
    amal: AuditAmali | str,
    tavsif: str,
    *,
    foydalanuvchi: Foydalanuvchi | None = None,
    obyekt: models.Model | object | None = None,
    model_nomi: str = "",
    obyekt_id: int | str | None = "",
    ip_manzil: str | None = None,
    request: HttpRequest | None = None,
) -> AuditYozuvi:
    """Record an audit trail event, deriving metadata and trusted IP."""
    model_satri, obyekt_satri = _obyekt_meta(obyekt, model_nomi, obyekt_id)
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
        model_nomi=model_satri,
        obyekt_id=obyekt_satri,
        tavsif=tavsif,
        ip_manzil=ip_manzil,
    )
