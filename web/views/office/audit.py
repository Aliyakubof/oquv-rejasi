"""Audit trail viewer for Office Admins."""

from django.db.models import QuerySet
from django.views.generic import ListView

from plans.models import AuditAmali, AuditYozuvi
from web.mixins import OfficeAdminTalabMixin


class AuditListView(OfficeAdminTalabMixin, ListView):
    template_name = "web/office/audit/list.html"
    model = AuditYozuvi
    context_object_name = "yozuvlar"
    paginate_by = 50

    def get_queryset(self) -> QuerySet[AuditYozuvi]:
        qs = AuditYozuvi.objects.select_related("foydalanuvchi").order_by("-vaqt")
        amal = self.request.GET.get("amal")
        if amal and amal in AuditAmali.values:
            qs = qs.filter(amal=amal)
        q = self.request.GET.get("q")
        if q:
            qs = qs.filter(tavsif__icontains=q)
        return qs

    def get_context_data(self, **kwargs: object) -> dict[str, object]:
        context = super().get_context_data(**kwargs)
        context["amallar"] = AuditAmali.choices
        context["tanlangan_amal"] = self.request.GET.get("amal", "")
        context["q"] = self.request.GET.get("q", "")
        return context
