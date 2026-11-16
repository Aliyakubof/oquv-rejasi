"""Har bir sahifa shabloniga uzatiladigan umumiy kontekst."""

from django.conf import settings
from django.http import HttpRequest

from plans.models import Bildirishnoma


def debug_rejim(request: HttpRequest) -> dict[str, object]:
    """To'liq yoki HTMX sahifalar uchun DEBUG holati va so'nggi xabarlarni beradi."""
    user = getattr(request, "user", None)
    qisman_htmx = (
        request.headers.get("HX-Request") == "true"
        and request.headers.get("HX-Boosted") != "true"
    )
    if user is None or not user.is_authenticated or qisman_htmx:
        return {
            "debug_rejim": settings.DEBUG,
            "oqilmagan_xabarlar_soni": 0,
            "songgi_xabarlar": [],
        }
    qs = Bildirishnoma.objects.filter(qabul_qiluvchi=user).order_by(
        "-yaratilgan_vaqt", "-pk"
    )
    songgi = list(qs[:6])
    oqilmagan = qs.filter(oqilgan=False).count()
    return {
        "debug_rejim": settings.DEBUG,
        "oqilmagan_xabarlar_soni": oqilmagan,
        "songgi_xabarlar": songgi,
    }
