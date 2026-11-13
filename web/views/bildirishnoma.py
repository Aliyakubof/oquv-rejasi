"""Notification inbox and read-state actions."""

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.views.generic import ListView

from plans.models import Bildirishnoma
from plans.services import keshni_tozala


class BildirishnomaListView(LoginRequiredMixin, ListView):
    template_name = "web/bildirishnomalar/list.html"
    model = Bildirishnoma
    context_object_name = "bildirishnomalar"
    paginate_by = 30

    def get_queryset(self) -> QuerySet[Bildirishnoma]:
        return Bildirishnoma.objects.filter(qabul_qiluvchi=self.request.user).order_by(
            "-yaratilgan_vaqt", "-pk"
        )


@login_required
@require_POST
def bildirishnoma_oqish(request: HttpRequest, pk: int) -> HttpResponse:
    xabar = get_object_or_404(Bildirishnoma, pk=pk, qabul_qiluvchi=request.user)
    if not xabar.oqilgan:
        xabar.oqilgan = True
        xabar.save(update_fields=["oqilgan"])
        keshni_tozala()
    if xabar.havola and url_has_allowed_host_and_scheme(
        xabar.havola,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(xabar.havola)
    return redirect("bildirishnoma_list")


@login_required
@require_POST
def bildirishnoma_barchasi_oqildi(request: HttpRequest) -> HttpResponse:
    yangilandi = Bildirishnoma.objects.filter(
        qabul_qiluvchi=request.user, oqilgan=False
    ).update(oqilgan=True)
    if yangilandi:
        keshni_tozala()
    keyingi = request.POST.get("next") or ""
    if keyingi and url_has_allowed_host_and_scheme(
        keyingi,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(keyingi)
    return redirect("bildirishnoma_list")
