"""Login, logout, password change and the role-based landing dispatch."""

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.views.generic import FormView

from accounts.models import Foydalanuvchi, Rol
from web.forms.auth import (
    KorinishSozlamalariForm,
    ParolOzgartirishForm,
    TelefonKirishForm,
    TelegramBoglashForm,
)
from web.mixins import _boshqarayotgan_kafedra
from web.security import (
    kirish_bloklanganmi,
    kirish_muvaffaqiyatini_tozala,
    kirish_xatosini_qayd_et,
)

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

    def post(
        self, request: HttpRequest, *args: object, **kwargs: object
    ) -> HttpResponse:
        telefon = str(request.POST.get("username", ""))
        bloklangan, soniya = kirish_bloklanganmi(request, telefon)
        if bloklangan:
            daqiqa = max(1, (soniya + 59) // 60)
            form = self.get_form()
            form.add_error(
                None,
                (
                    f"Juda ko'p noto'g'ri urinish. {daqiqa} daqiqadan so'ng "
                    "qayta urinib ko'ring."
                ),
            )
            return self.render_to_response(self.get_context_data(form=form), status=429)
        return super().post(request, *args, **kwargs)

    def form_valid(self, form: TelefonKirishForm) -> HttpResponse:
        kirish_muvaffaqiyatini_tozala(
            self.request, str(form.cleaned_data.get("username", ""))
        )
        return super().form_valid(form)

    def form_invalid(self, form: TelefonKirishForm) -> HttpResponse:
        kirish_xatosini_qayd_et(
            self.request, str(self.request.POST.get("username", ""))
        )
        return super().form_invalid(form)


class ParolOzgartirishView(LoginRequiredMixin, FormView):
    template_name = "web/auth/parol.html"
    form_class = ParolOzgartirishForm

    def get_form_kwargs(self) -> dict[str, object]:
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs: object) -> dict[str, object]:
        context = super().get_context_data(**kwargs)
        context["telegram_form"] = TelegramBoglashForm(instance=self.request.user)
        return context

    def form_valid(self, form: ParolOzgartirishForm) -> HttpResponse:
        user = form.save()
        if getattr(user, "parol_ozgartirish_kerak", False):
            user.parol_ozgartirish_kerak = False
            user.save(update_fields=["parol_ozgartirish_kerak"])
        update_session_auth_hash(self.request, user)
        messages.success(self.request, "Parolingiz muvaffaqiyatli o'zgartirildi.")
        return redirect("bosh_sahifa")


@login_required
@require_POST
def profil_telegram_saqlash(request: HttpRequest) -> HttpResponse:
    form = TelegramBoglashForm(request.POST, instance=request.user)
    if form.is_valid():
        saqlangan = form.save()
        xabar = (
            "Telegram Chat ID saqlandi."
            if saqlangan.telegram_chat_id
            else "Telegram bildirishnomasi o'chirildi."
        )
        messages.success(request, xabar)
    else:
        for xs in form.errors.values():
            for x in xs:
                messages.error(request, x)
    return redirect("parol_ozgartirish")


@login_required
def bosh_sahifa(request: HttpRequest) -> HttpResponse:
    if (
        request.user.rol == Rol.DEPARTMENT_ADMIN
        and _boshqarayotgan_kafedra(request) is None
    ):
        return redirect("men:yuklamalar")
    return redirect(ROL_SAHIFALARI.get(request.user.rol, "kirish"))


def _xavfsiz_qaytish_manzili(request: HttpRequest) -> str:
    nomzod = request.POST.get("next") or request.META.get("HTTP_REFERER") or ""
    if nomzod and url_has_allowed_host_and_scheme(
        nomzod, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return nomzod
    return ""


@login_required
@require_POST
def korinish_saqlash(request: HttpRequest) -> HttpResponse:
    user: Foydalanuvchi = request.user  # type: ignore[assignment]
    form = KorinishSozlamalariForm(request.POST, instance=user)
    json_sorov = (
        "application/json" in request.headers.get("Accept", "")
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
    )
    if not form.is_valid():
        if json_sorov:
            return JsonResponse({"ok": False, "errors": form.errors}, status=400)
        messages.error(request, "Ko'rinish sozlamalarini tekshiring.")
        manzil = _xavfsiz_qaytish_manzili(request)
        return redirect(manzil) if manzil else redirect("bosh_sahifa")

    saqlangan = form.save()
    if json_sorov:
        return JsonResponse(
            {
                "ok": True,
                "shrift_olchami": saqlangan.shrift_olchami,
                "yuqori_kontrast": saqlangan.yuqori_kontrast,
                "keng_rejim": saqlangan.keng_rejim,
            }
        )
    messages.success(request, "Ko'rinish sozlamalari saqlandi.")
    manzil = _xavfsiz_qaytish_manzili(request)
    return redirect(manzil) if manzil else redirect("bosh_sahifa")
