from django.urls import path

from web.views.api import (
    HemisSyncApiView,
    KafedralarApiView,
    OqituvchilarApiView,
    RejalarApiView,
    YuklamalarApiView,
)

app_name = "api"

urlpatterns = [
    path("rejalar/", RejalarApiView.as_view(), name="rejalar"),
    path("kafedralar/", KafedralarApiView.as_view(), name="kafedralar"),
    path("oqituvchilar/", OqituvchilarApiView.as_view(), name="oqituvchilar"),
    path("yuklamalar/", YuklamalarApiView.as_view(), name="yuklamalar"),
    path("sync/", HemisSyncApiView.as_view(), name="sync"),
]
