from django.urls import path

from web.views.office.audit import AuditListView
from web.views.office.dashboard import (
    DashboardView,
    kafedra_biriktirish,
    ommaviy_kafedra_biriktirish,
    svod_excel_view,
    taqsimot_nusxalash_view,
    variant_tanlash,
)
from web.views.office.dastur import (
    DasturTopshirishlarView,
    dastur_fayl,
    dastur_qabul,
    dastur_rad,
    dastur_tarixi,
)
from web.views.office.kafedralar import (
    KafedraListView,
    KafedraTahrirView,
    KafedraYangiView,
    kafedra_mudir,
    kafedra_ochirish,
    kafedra_shakl1_zip_view,
    kafedra_yuklama_qaytarish,
    kafedra_yuklama_tasdiqlash,
)
from web.views.office.oqituvchilar import (
    OqituvchiImportView,
    OqituvchiListView,
    OqituvchiTahrirView,
    OqituvchiYangiView,
    OqituvchiYuklamaView,
    oqituvchi_import_parollar_view,
    oqituvchi_namuna_excel_view,
    oqituvchi_ochirish,
    oqituvchi_shakl1_docx_view,
    oqituvchi_vaqtinchalik_parol,
    oqituvchilar_excel_view,
)
from web.views.office.rejalar import (
    RejaDetailView,
    RejaImportView,
    RejaListView,
    RejaTahrirView,
    reja_ochirish,
    semestrovka_saqlash,
)
from web.views.office.sozlamalar import (
    LavozimTahrirView,
    LavozimYangiView,
    SozlamalarView,
    YonalishTahrirView,
    YonalishYangiView,
    lavozim_ochirish,
    universitet_saqlash,
    yonalish_import_view,
    yonalish_namuna_excel_view,
    yonalish_ochirish,
)

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path("fan/<int:pk>/variant/", variant_tanlash, name="variant_tanlash"),
    path("variant/<int:pk>/kafedra/", kafedra_biriktirish, name="kafedra_biriktirish"),
    path(
        "variantlar/ommaviy-kafedra/",
        ommaviy_kafedra_biriktirish,
        name="ommaviy_kafedra_biriktirish",
    ),
    path("nusxalash/", taqsimot_nusxalash_view, name="taqsimot_nusxalash"),
    path("svod/excel/", svod_excel_view, name="svod_excel"),
    path("rejalar/", RejaListView.as_view(), name="reja_list"),
    path("rejalar/yangi/", RejaImportView.as_view(), name="reja_yangi"),
    path("rejalar/<int:pk>/", RejaDetailView.as_view(), name="reja_detail"),
    path("rejalar/<int:pk>/tahrir/", RejaTahrirView.as_view(), name="reja_tahrir"),
    path("rejalar/<int:pk>/ochirish/", reja_ochirish, name="reja_ochirish"),
    path(
        "rejalar/<int:pk>/semestrovka/",
        semestrovka_saqlash,
        name="semestrovka_saqlash",
    ),
    path("audit/", AuditListView.as_view(), name="audit_list"),
    path("dasturlar/", DasturTopshirishlarView.as_view(), name="dastur_topshirishlar"),
    path("dasturlar/<int:pk>/qabul/", dastur_qabul, name="dastur_qabul"),
    path("dasturlar/<int:pk>/rad/", dastur_rad, name="dastur_rad"),
    path("dasturlar/<int:pk>/fayl/", dastur_fayl, name="dastur_fayl"),
    path("dasturlar/<int:variant_id>/tarixi/", dastur_tarixi, name="dastur_tarixi"),
    path("kafedralar/", KafedraListView.as_view(), name="kafedra_list"),
    path("kafedralar/yangi/", KafedraYangiView.as_view(), name="kafedra_yangi"),
    path(
        "kafedralar/<int:pk>/tahrir/",
        KafedraTahrirView.as_view(),
        name="kafedra_tahrir",
    ),
    path("kafedralar/<int:pk>/ochirish/", kafedra_ochirish, name="kafedra_ochirish"),
    path("kafedralar/<int:pk>/mudir/", kafedra_mudir, name="kafedra_mudir"),
    path(
        "kafedralar/<int:pk>/tasdiqlash/",
        kafedra_yuklama_tasdiqlash,
        name="kafedra_tasdiqlash",
    ),
    path(
        "kafedralar/<int:pk>/qaytarish/",
        kafedra_yuklama_qaytarish,
        name="kafedra_qaytarish",
    ),
    path(
        "kafedralar/shakl1-zip/",
        kafedra_shakl1_zip_view,
        name="oqituvchi_shakl1_zip",
    ),
    path(
        "kafedralar/<int:pk>/shakl1-zip/",
        kafedra_shakl1_zip_view,
        name="kafedra_shakl1_zip",
    ),
    path("oqituvchilar/", OqituvchiListView.as_view(), name="oqituvchi_list"),
    path("oqituvchilar/excel/", oqituvchilar_excel_view, name="oqituvchi_excel"),
    path(
        "oqituvchilar/import/",
        OqituvchiImportView.as_view(),
        name="oqituvchi_import",
    ),
    path(
        "oqituvchilar/namuna/",
        oqituvchi_namuna_excel_view,
        name="oqituvchi_namuna_excel",
    ),
    path(
        "oqituvchilar/import/parollar/",
        oqituvchi_import_parollar_view,
        name="oqituvchi_import_parollar",
    ),
    path("oqituvchilar/yangi/", OqituvchiYangiView.as_view(), name="oqituvchi_yangi"),
    path(
        "oqituvchilar/<int:pk>/yuklama/",
        OqituvchiYuklamaView.as_view(),
        name="oqituvchi_yuklama",
    ),
    path(
        "oqituvchilar/<int:pk>/shakl1-docx/",
        oqituvchi_shakl1_docx_view,
        name="oqituvchi_shakl1_docx",
    ),
    path(
        "oqituvchilar/<int:pk>/tahrir/",
        OqituvchiTahrirView.as_view(),
        name="oqituvchi_tahrir",
    ),
    path(
        "oqituvchilar/<int:pk>/ochirish/", oqituvchi_ochirish, name="oqituvchi_ochirish"
    ),
    path(
        "oqituvchilar/<int:pk>/vaqtinchalik-parol/",
        oqituvchi_vaqtinchalik_parol,
        name="oqituvchi_vaqtinchalik_parol",
    ),
    path("sozlamalar/", SozlamalarView.as_view(), name="sozlamalar"),
    path(
        "sozlamalar/universitet/",
        universitet_saqlash,
        name="universitet_saqlash",
    ),
    path(
        "sozlamalar/lavozimlar/yangi/",
        LavozimYangiView.as_view(),
        name="lavozim_yangi",
    ),
    path(
        "sozlamalar/lavozimlar/<int:pk>/tahrir/",
        LavozimTahrirView.as_view(),
        name="lavozim_tahrir",
    ),
    path(
        "sozlamalar/lavozimlar/<int:pk>/ochirish/",
        lavozim_ochirish,
        name="lavozim_ochirish",
    ),
    path(
        "sozlamalar/yonalishlar/yangi/",
        YonalishYangiView.as_view(),
        name="yonalish_yangi",
    ),
    path(
        "sozlamalar/yonalishlar/import/",
        yonalish_import_view,
        name="yonalish_import",
    ),
    path(
        "sozlamalar/yonalishlar/namuna/",
        yonalish_namuna_excel_view,
        name="yonalish_namuna_excel",
    ),
    path(
        "sozlamalar/yonalishlar/<int:pk>/tahrir/",
        YonalishTahrirView.as_view(),
        name="yonalish_tahrir",
    ),
    path(
        "sozlamalar/yonalishlar/<int:pk>/ochirish/",
        yonalish_ochirish,
        name="yonalish_ochirish",
    ),
]
