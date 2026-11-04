from django.urls import path

from web.views.kafedra.dashboard import (
    KafedraDashboardView,
    tasdiqqa_yuborish_view,
)
from web.views.kafedra.hisobot import HisobotExcelView, HisobotView
from web.views.kafedra.oqituvchilar import (
    KafedraOqituvchiListView,
    KafedraOqituvchiTahrirView,
    KafedraOqituvchiYangiView,
    KafedraOqituvchiYuklamaView,
)
from web.views.kafedra.yuklama import (
    TaqsimotPanelView,
    YuklamaOchirishView,
    YuklamaYaratishView,
)

urlpatterns = [
    path("", KafedraDashboardView.as_view(), name="dashboard"),
    path("tasdiqqa-yuborish/", tasdiqqa_yuborish_view, name="tasdiqqa_yuborish"),
    path(
        "fan-semestr/<int:pk>/panel/",
        TaqsimotPanelView.as_view(),
        name="taqsimot_panel",
    ),
    path(
        "fan-semestr/<int:pk>/maruza/",
        YuklamaYaratishView.as_view(shakl="maruza"),
        name="maruza_yaratish",
    ),
    path(
        "fan-semestr/<int:pk>/guruh/",
        YuklamaYaratishView.as_view(shakl="guruh"),
        name="guruh_yaratish",
    ),
    path(
        "fan-semestr/<int:pk>/kurs-ishi/",
        YuklamaYaratishView.as_view(shakl="kurs_ishi"),
        name="kurs_ishi_yaratish",
    ),
    path(
        "yuklama/<int:pk>/ochirish/",
        YuklamaOchirishView.as_view(),
        name="yuklama_ochirish",
    ),
    path("oqituvchilar/", KafedraOqituvchiListView.as_view(), name="oqituvchi_list"),
    path(
        "oqituvchilar/yangi/",
        KafedraOqituvchiYangiView.as_view(),
        name="oqituvchi_yangi",
    ),
    path(
        "oqituvchilar/<int:pk>/yuklama/",
        KafedraOqituvchiYuklamaView.as_view(),
        name="oqituvchi_yuklama",
    ),
    path(
        "oqituvchilar/<int:pk>/tahrir/",
        KafedraOqituvchiTahrirView.as_view(),
        name="oqituvchi_tahrir",
    ),
    path("hisobot/", HisobotView.as_view(), name="hisobot"),
    path("hisobot/excel/", HisobotExcelView.as_view(), name="hisobot_excel"),
]
