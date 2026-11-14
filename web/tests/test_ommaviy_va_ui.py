"""Regression tests for bulk kafedra assignment, cache TTL, and UI/UX upgrades."""

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Department
from plans import dashboard, services
from plans.models import AuditAmali, AuditYozuvi, FanTuri, SoatTuri
from plans.tests.factories import (
    make_fan,
    make_fan_semestr,
    make_oqituvchi,
    make_reja,
)
from web.tests.helpers import login, mudir_yarat, office_admin_yarat, oqituvchi_yarat
from web.views.jonli import _kesh_muddati


class OmmaviyKafedraBiriktirishTests(TestCase):
    def setUp(self) -> None:
        self.yil = dashboard.joriy_akademik_yil()
        self.reja = make_reja(boshlanish_yili=self.yil)
        services.guruhlarni_sinxronlash(self.reja)
        self.kaf1 = Department.objects.create(nomi="Dasturiy injiniring")
        self.kaf2 = Department.objects.create(nomi="Axborot xavfsizligi")
        self.admin = office_admin_yarat()

    def test_ommaviy_biriktirish_va_bekor_qilish(self) -> None:
        fan1 = make_fan(self.reja, raqam="1.01")
        fan2 = make_fan(self.reja, raqam="1.02", nomi="Ma'lumotlar bazasi")
        v1 = fan1.tanlangan_variant
        v2 = fan2.tanlangan_variant
        assert v1 is not None and v2 is not None

        soni = services.kafedraga_ommaviy_biriktirish([v1.pk, v2.pk, v1.pk], self.kaf1)
        self.assertEqual(soni, 2)
        v1.refresh_from_db()
        v2.refresh_from_db()
        self.assertEqual(v1.kafedra, self.kaf1)
        self.assertEqual(v2.kafedra, self.kaf1)

        self.assertEqual(
            services.kafedraga_ommaviy_biriktirish([v1.pk, v2.pk], self.kaf1), 0
        )

        bekor_soni = services.kafedraga_ommaviy_biriktirish([v1.pk, v2.pk], None)
        self.assertEqual(bekor_soni, 2)
        v1.refresh_from_db()
        v2.refresh_from_db()
        self.assertIsNone(v1.kafedra)
        self.assertIsNone(v2.kafedra)

    def test_tanlanmagan_variant_yoki_yuklama_bolsa_atomic_bekor_boladi(self) -> None:
        fan_maj = make_fan(self.reja, raqam="1.01")
        v_maj = fan_maj.tanlangan_variant
        assert v_maj is not None
        fs = make_fan_semestr(v_maj, semestr=1)

        fan_tanlov = make_fan(self.reja, raqam="1.02", turi=FanTuri.TANLOV)
        v_tanlov = fan_tanlov.variantlar.first()
        assert v_tanlov is not None

        with self.assertRaises(ValidationError):
            services.kafedraga_ommaviy_biriktirish([v_maj.pk, v_tanlov.pk], self.kaf1)
        v_maj.refresh_from_db()
        self.assertIsNone(v_maj.kafedra)

        services.kafedraga_ommaviy_biriktirish([v_maj.pk], self.kaf1)
        oqituvchi = make_oqituvchi(kafedra=self.kaf1)
        services.guruhlarga_ommaviy_taqsimlash(fs, oqituvchi, SoatTuri.AMALIYOT)

        with self.assertRaises(ValidationError) as ctx:
            services.kafedraga_ommaviy_biriktirish([v_maj.pk], self.kaf2)
        self.assertIn("yuklamalar bor", str(ctx.exception))
        v_maj.refresh_from_db()
        self.assertEqual(v_maj.kafedra, self.kaf1)

    def test_office_ommaviy_view_ruxsat_va_xato_kirish(self) -> None:
        url = reverse("office:ommaviy_kafedra_biriktirish")
        login(self.client, oqituvchi_yarat(kafedra=self.kaf1))
        rad = self.client.post(url, {"yil": self.yil, "kafedra": self.kaf1.pk})
        self.assertRedirects(rad, reverse("bosh_sahifa"), target_status_code=302)

        login(self.client, self.admin)
        bosh = self.client.post(
            url, {"yil": self.yil, "kafedra": self.kaf1.pk}, HTTP_HX_REQUEST="true"
        )
        self.assertEqual(bosh.status_code, 200)
        self.assertContains(bosh, 'id="app-messages"')
        self.assertContains(bosh, 'hx-swap-oob="true"')
        self.assertContains(bosh, "Kamida bitta fanni tanlang.")
        for bad in ("bad", "999999"):
            self.assertEqual(
                self.client.post(url, {"yil": self.yil, "kafedra": bad}).status_code,
                404,
            )

    def test_office_ommaviy_view_htmx_va_redirect(self) -> None:
        url = reverse("office:ommaviy_kafedra_biriktirish")
        v1 = make_fan(self.reja, raqam="1.01").tanlangan_variant
        v2 = make_fan(self.reja, raqam="1.02").tanlangan_variant
        assert v1 is not None and v2 is not None
        login(self.client, self.admin)

        htmx = self.client.post(
            url,
            {
                "yil": self.yil,
                "kafedra": self.kaf1.pk,
                "variantlar": [str(v1.pk), str(v2.pk)],
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(htmx.status_code, 200)
        self.assertContains(htmx, f"2 ta fan {self.kaf1.nomi} ga biriktirildi.")
        v1.refresh_from_db()
        v2.refresh_from_db()
        self.assertEqual((v1.kafedra, v2.kafedra), (self.kaf1, self.kaf1))
        self.assertTrue(
            AuditYozuvi.objects.filter(
                amal=AuditAmali.TAHRIRLANDI, model_nomi="FanVariant"
            ).exists()
        )

        bekor = self.client.post(
            url,
            {"yil": self.yil, "kafedra": "", "variantlar": [str(v1.pk), str(v2.pk)]},
            follow=True,
        )
        self.assertRedirects(bekor, f"{reverse('office:dashboard')}?yil={self.yil}")
        self.assertContains(bekor, "2 ta fan biriktirilishi bekor qilindi.")
        v1.refresh_from_db()
        self.assertIsNone(v1.kafedra)


class SamaradorlikVaUiYaxshilashTests(TestCase):
    def test_jonli_kesh_muddati_redis_va_lokal(self) -> None:
        with override_settings(
            CACHES={
                "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
            }
        ):
            self.assertEqual(_kesh_muddati(), 5)
        with override_settings(
            CACHES={
                "default": {"BACKEND": "django.core.cache.backends.redis.RedisCache"}
            }
        ):
            self.assertEqual(_kesh_muddati(), 3600)

    def test_shablonlar_va_ui_yaxshilanishlar(self) -> None:
        yil = dashboard.joriy_akademik_yil()
        reja = make_reja(boshlanish_yili=yil, yonalish_kodi="60610200")
        kaf = Department.objects.create(nomi="Sun'iy intellekt")
        fan = make_fan(reja, kafedra=kaf)
        assert fan.tanlangan_variant is not None
        make_fan_semestr(fan.tanlangan_variant, semestr=1)

        kirish = self.client.get(reverse("kirish"))
        self.assertEqual(kirish.status_code, 200)
        for belgi in (
            "auth-body",
            "auth-shell",
            "auth-input-wrap",
            "auth-submit",
            "<h1>Kirish</h1>",
        ):
            self.assertContains(kirish, belgi)
        for eski_matn in (
            "Tizim tayyorlanmoqda",
            "Tizimga kirish",
            "O'quv yuklamasi platformasi",
        ):
            self.assertNotContains(kirish, eski_matn)

        login(self.client, office_admin_yarat())
        dash = self.client.get(reverse("office:dashboard"), {"yil": yil})
        self.assertEqual(dash.status_code, 200)
        self.assertNotContains(dash, "Tizim tayyorlanmoqda")
        for belgi in (
            'media="print" onload="this.media=\'all\'"',
            "<noscript>",
            "app.css?v=59",
            "jonli.js?v=3",
            "window.yopishTableModal",
            "btn-ripple",
            "is-closing",
            "is-page-loading",
            "animateCounters",
            'class="loader-emblem"',
            'class="loader-progress-fill"',
            "PageLoader.playFor(muddat)",
            'class="search-clear"',
            reverse("office:ommaviy_kafedra_biriktirish"),
            'class="row-check"',
            "sun&#x27;iy intellekt 60610200",
            ":class=\"ochiq && 'popover-ochiq'\"",
            'x-ref="qidiruvInput"',
            "anim-pop-enter",
            "anim-bulk-enter",
            "anim-tab-enter",
        ):
            self.assertContains(dash, belgi)

        semestrovka = self.client.get(reverse("office:reja_detail", args=[reja.pk]))
        self.assertContains(semestrovka, ":class=\"ochiq && 'popover-ochiq'\"")
        self.assertContains(semestrovka, 'x-ref="qidiruvInput"')
        self.assertContains(semestrovka, "anim-tab-enter")

        semestr = self.client.get(
            reverse("office:reja_detail", args=[reja.pk]),
            {"tab": "semestr", "sem": 1},
        )
        self.assertContains(semestr, ":class=\"ochiq_k && 'popover-ochiq'\"")
        self.assertContains(semestr, 'x-ref="qidiruvInput"')

    def test_office_sahifalar_ui_yaxshilanishlari(self) -> None:
        yil = dashboard.joriy_akademik_yil()
        reja = make_reja(boshlanish_yili=yil, yonalish_kodi="60610300")
        kaf = Department.objects.create(nomi="Kiberxavfsizlik")
        make_oqituvchi(kaf)
        fan = make_fan(reja, kafedra=kaf)
        assert fan.tanlangan_variant is not None
        make_fan_semestr(fan.tanlangan_variant, semestr=1)
        login(self.client, office_admin_yarat())

        sahifa_tekshiruvlari = [
            (
                reverse("office:dashboard"),
                (
                    "office-dash-actions",
                    "segmented-tabs",
                    "filter-toolbar",
                    "popover-up",
                ),
            ),
            (
                reverse("office:reja_list"),
                ("filter-toolbar", "row-actions", "badge-count"),
            ),
            (
                reverse("office:reja_detail", args=[reja.pk]),
                ("segmented-tabs", "filter-toolbar", "table-action-bar"),
            ),
            (
                reverse("office:reja_yangi"),
                ("card form-card", "form-actions"),
            ),
            (
                reverse("office:reja_tahrir", args=[reja.pk]),
                ("card form-card", "form-actions"),
            ),
            (
                reverse("office:kafedra_list"),
                ("table-wrap cards", "filter-toolbar", "popover-ochiq", "popover-up"),
            ),
            (
                reverse("office:oqituvchi_list"),
                ("filter-toolbar", "action-menu-fixed", "qamrov-cell"),
            ),
            (
                reverse("office:oqituvchi_import"),
                ("breadcrumb", "card form-card", "form-actions"),
            ),
            (
                reverse("office:dastur_topshirishlar"),
                ("filter-toolbar", "empty-state-rich"),
            ),
            (
                reverse("office:audit_list"),
                ("filter-toolbar", "audit-filter-form", "empty-state-rich"),
            ),
            (
                reverse("office:sozlamalar"),
                (
                    "settings-card",
                    "sozlamalar-tools-bar",
                    "file-picker-compact",
                    "Fayl tanlash",
                ),
            ),
            (
                reverse("office:lavozim_yangi"),
                ("card form-card", "form-actions"),
            ),
        ]

        for url, belgilar in sahifa_tekshiruvlari:
            javob = self.client.get(url)
            self.assertEqual(javob.status_code, 200, url)
            for belgi in belgilar:
                self.assertContains(javob, belgi, msg_prefix=url)

    def test_men_yuklamalar_va_dastur_panel_ui(self) -> None:
        from plans.models import Yuklama

        yil = dashboard.joriy_akademik_yil()
        kaf = Department.objects.create(nomi="Raqamli texnologiyalar")
        user = oqituvchi_yarat(kafedra=kaf)
        login(self.client, user)

        bosh_men = self.client.get(reverse("men:yuklamalar"), {"yil": yil})
        self.assertEqual(bosh_men.status_code, 200)
        self.assertContains(bosh_men, "empty-state-rich")
        self.assertNotContains(bosh_men, "empty-state-filtered")

        reja = make_reja(boshlanish_yili=yil, yonalish_kodi="60610400")
        fan = make_fan(reja, kafedra=kaf)
        assert fan.tanlangan_variant is not None
        fs = make_fan_semestr(fan.tanlangan_variant, semestr=1)
        yuklama = Yuklama.objects.create(
            fan_semestr=fs, tur=SoatTuri.MARUZA, oqituvchi=user.oqituvchi_profil
        )

        yuklamali = self.client.get(reverse("men:yuklamalar"), {"yil": yil})
        self.assertEqual(yuklamali.status_code, 200)
        for belgi in (
            "tur-legend-row",
            "filter-toolbar",
            "search-clear",
            "reja-link-btn",
            "table-total-label",
            "empty-state-filtered",
        ):
            self.assertContains(yuklamali, belgi)

        panel = self.client.get(
            reverse("men:dastur_tarixi", args=[fan.tanlangan_variant.pk])
        )
        self.assertEqual(panel.status_code, 200)
        for belgi in (
            "app-modal-close",
            "tarix-panel-foot",
            "file-picker-compact",
            "Fayl tanlash",
        ):
            self.assertContains(panel, belgi)

        yuklama.delete()
        user.oqituvchi_profil.delete()
        profilsiz = self.client.get(reverse("men:yuklamalar"), {"yil": yil})
        self.assertEqual(profilsiz.status_code, 200)
        self.assertContains(profilsiz, "empty-state-rich")
        self.assertContains(profilsiz, "Profil biriktirilmagan")

    def test_bildirishnoma_ui_yaxshilanishlari(self) -> None:
        from plans.models import Bildirishnoma

        user = oqituvchi_yarat()
        login(self.client, user)

        bild_bosh = self.client.get(reverse("bildirishnoma_list"))
        self.assertEqual(bild_bosh.status_code, 200)
        self.assertContains(bild_bosh, "empty-state-rich")

        Bildirishnoma.objects.bulk_create(
            [
                Bildirishnoma(qabul_qiluvchi=user, sarlavha=f"Bildirishnoma {i}")
                for i in range(31)
            ]
        )
        bild_royxat = self.client.get(reverse("bildirishnoma_list"))
        self.assertEqual(bild_royxat.status_code, 200)
        for belgi in ("audit-vaqt", "notif-title-unread", "notif-dot-inline", "page=2"):
            self.assertContains(bild_royxat, belgi)

    def test_jadval_popover_fixed_va_qidiruv_belgilari(self) -> None:
        yil = dashboard.joriy_akademik_yil()
        reja = make_reja(boshlanish_yili=yil, yonalish_kodi="60610500")
        kaf = Department.objects.create(nomi="Sun'iy intellekt kafedrasi")
        make_oqituvchi(kaf)
        fan = make_fan(reja, kafedra=kaf)
        assert fan.tanlangan_variant is not None
        make_fan_semestr(fan.tanlangan_variant, semestr=1)
        login(self.client, office_admin_yarat())

        sahifalar = [
            reverse("office:dashboard"),
            reverse("office:reja_detail", args=[reja.pk]),
            f"{reverse('office:reja_detail', args=[reja.pk])}?tab=semestr&sem=1",
            reverse("office:kafedra_list"),
        ]
        for url in sahifalar:
            javob = self.client.get(url)
            self.assertEqual(javob.status_code, 200, url)
            for belgi in (
                "Alpine.data('jadvalPopover'",
                "anim-tugadi",
                "popover popover-fixed",
                "popover-scroll-body",
                "popover-empty-hint",
            ):
                self.assertContains(javob, belgi, msg_prefix=url)

        from django.conf import settings

        css_matn = (
            settings.BASE_DIR / "web" / "static" / "web" / "css" / "app.css"
        ).read_text(encoding="utf-8")
        self.assertIn("table-wrap.anim-tugadi", css_matn)
        self.assertNotIn("table-wrap:has(.popover-ochiq)", css_matn)

    def test_kafedra_sahifalar_va_panel_shablonlari(self) -> None:
        yil = dashboard.joriy_akademik_yil()
        kaf = Department.objects.create(nomi="Dasturlash kafedrasi")
        mudir = mudir_yarat(kaf)
        reja = make_reja(boshlanish_yili=yil, yonalish_kodi="60610600")
        fan = make_fan(reja, kafedra=kaf)
        assert fan.tanlangan_variant is not None
        fs = make_fan_semestr(fan.tanlangan_variant, semestr=1)
        login(self.client, mudir)

        for url in (
            reverse("kafedra:dashboard"),
            reverse("kafedra:hisobot"),
            reverse("kafedra:oqituvchi_list"),
            reverse("kafedra:taqsimot_panel", args=[fs.pk]),
        ):
            javob = self.client.get(url)
            self.assertEqual(javob.status_code, 200, url)
            self.assertContains(javob, 'stroke="currentColor"', msg_prefix=url)
