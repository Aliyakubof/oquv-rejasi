"""Login, logout, password change and the role-based landing dispatch."""

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.views.generic import FormView

from accounts.models import Rol
from web.forms.auth import ParolOzgartirishForm, TelefonKirishForm
from web.mixins import _boshqarayotgan_kafedra

ROL_SAHIFALARI = {
    Rol.SUPERADMIN: "office:dashboard",
    Rol.OFFICE_ADMIN: "office:dashboard",
    Rol.DEPARTMENT_ADMIN: "kafedra:dashboard",
    Rol.TEACHER: "men:yuklamalar",
}


class KirishView(LoginView):
    template_name = "web/auth/kirish.html"
    form_class = TelefonKirishForm
    redirect_authenticated_user = True


class ParolOzgartirishView(LoginRequiredMixin, FormView):
    template_name = "web/auth/parol.html"
    form_class = ParolOzgartirishForm

    def get_form_kwargs(self) -> dict[str, object]:
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form: ParolOzgartirishForm) -> HttpResponse:
        user = form.save()
        update_session_auth_hash(self.request, user)
        messages.success(self.request, "Parolingiz muvaffaqiyatli o'zgartirildi.")
        return redirect("bosh_sahifa")


@login_required
def bosh_sahifa(request: HttpRequest) -> HttpResponse:
    if (
        request.user.rol == Rol.DEPARTMENT_ADMIN
        and _boshqarayotgan_kafedra(request) is None
    ):
        return redirect("men:yuklamalar")
    return redirect(ROL_SAHIFALARI.get(request.user.rol, "kirish"))
