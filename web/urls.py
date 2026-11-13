from django.contrib.auth.views import LogoutView
from django.urls import include, path

from web.views.auth import (
    KirishView,
    ParolOzgartirishView,
    bosh_sahifa,
    korinish_saqlash,
    profil_telegram_saqlash,
)
from web.views.bildirishnoma import (
    BildirishnomaListView,
    bildirishnoma_barchasi_oqildi,
    bildirishnoma_oqish,
)
from web.views.jonli import jonli_holat

urlpatterns = [
    path("", bosh_sahifa, name="bosh_sahifa"),
    path("kirish/", KirishView.as_view(), name="kirish"),
    path("parol/", ParolOzgartirishView.as_view(), name="parol_ozgartirish"),
    path(
        "profil/telegram/",
        profil_telegram_saqlash,
        name="profil_telegram_saqlash",
    ),
    path(
        "bildirishnomalar/",
        BildirishnomaListView.as_view(),
        name="bildirishnoma_list",
    ),
    path(
        "bildirishnomalar/<int:pk>/oqish/",
        bildirishnoma_oqish,
        name="bildirishnoma_oqish",
    ),
    path(
        "bildirishnomalar/barchasi-oqildi/",
        bildirishnoma_barchasi_oqildi,
        name="bildirishnoma_barchasi_oqildi",
    ),
    path("korinish-sozlash/", korinish_saqlash, name="korinish_saqlash"),
    path("chiqish/", LogoutView.as_view(), name="chiqish"),
    path("jonli-holat/", jonli_holat, name="jonli_holat"),
    path("office/", include(("web.urls_office", "office"))),
    path("kafedra/", include(("web.urls_kafedra", "kafedra"))),
    path("men/", include(("web.urls_men", "men"))),
    path("dev/", include(("web.urls_dev", "dev"))),
]
