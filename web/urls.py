from django.contrib.auth.views import LogoutView
from django.urls import include, path

from web.views.auth import KirishView, ParolOzgartirishView, bosh_sahifa
from web.views.jonli import jonli_holat

urlpatterns = [
    path("", bosh_sahifa, name="bosh_sahifa"),
    path("kirish/", KirishView.as_view(), name="kirish"),
    path("parol/", ParolOzgartirishView.as_view(), name="parol_ozgartirish"),
    path("chiqish/", LogoutView.as_view(), name="chiqish"),
    path("jonli-holat/", jonli_holat, name="jonli_holat"),
    path("office/", include(("web.urls_office", "office"))),
    path("kafedra/", include(("web.urls_kafedra", "kafedra"))),
    path("men/", include(("web.urls_men", "men"))),
    path("dev/", include(("web.urls_dev", "dev"))),
]
