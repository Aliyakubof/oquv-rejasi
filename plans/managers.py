from django.db import models
from django.db.models import ExpressionWrapper, F


def _oquv_yili_semestrlari(kurs: int) -> tuple[int, int]:
    return 2 * kurs - 1, 2 * kurs


def _akademik_yil_ifodasi(prefiks: str = "") -> ExpressionWrapper:
    # Integer division on both SQLite and Postgres, so (semestr-1)/2 floors.
    return ExpressionWrapper(
        F(f"{prefiks}variant__fan__reja__boshlanish_yili")
        + (F(f"{prefiks}semestr") - 1) / 2,
        output_field=models.IntegerField(),
    )


class FanQuerySet(models.QuerySet):
    def oquv_yilida(self, kurs: int) -> "FanQuerySet":
        semestrlar = _oquv_yili_semestrlari(kurs)
        return self.filter(variantlar__semestrlar__semestr__in=semestrlar).distinct()

    def effektiv(self) -> "FanQuerySet":
        return self.filter(tanlangan_variant__isnull=False)

    def tanlov_kutilmoqda(self) -> "FanQuerySet":
        from plans.models import FanTuri

        return self.filter(turi=FanTuri.TANLOV, tanlangan_variant__isnull=True)

    def tanlov_tanlangan(self) -> "FanQuerySet":
        from plans.models import FanTuri

        return self.filter(turi=FanTuri.TANLOV, tanlangan_variant__isnull=False)


class FanVariantQuerySet(models.QuerySet):
    def effektiv(self) -> "FanVariantQuerySet":
        return self.filter(fan__tanlangan_variant_id=F("id"))


class FanSemestrQuerySet(models.QuerySet):
    def effektiv(self) -> "FanSemestrQuerySet":
        return self.filter(variant__fan__tanlangan_variant_id=F("variant_id"))

    def oquv_yilida(self, kurs: int) -> "FanSemestrQuerySet":
        return self.filter(semestr__in=_oquv_yili_semestrlari(kurs))

    def reja_uchun(self, reja: models.Model) -> "FanSemestrQuerySet":
        return self.filter(variant__fan__reja=reja)

    def akademik_yil_bilan(self) -> "FanSemestrQuerySet":
        return self.annotate(akademik_yili=_akademik_yil_ifodasi())

    def akademik_yilda(self, yil: int) -> "FanSemestrQuerySet":
        return self.akademik_yil_bilan().filter(akademik_yili=yil)


class YuklamaQuerySet(models.QuerySet):
    def akademik_yil_bilan(self) -> "YuklamaQuerySet":
        return self.annotate(akademik_yili=_akademik_yil_ifodasi("fan_semestr__"))

    def akademik_yilda(self, yil: int) -> "YuklamaQuerySet":
        return self.akademik_yil_bilan().filter(akademik_yili=yil)


FanManager = models.Manager.from_queryset(FanQuerySet)
FanVariantManager = models.Manager.from_queryset(FanVariantQuerySet)
FanSemestrManager = models.Manager.from_queryset(FanSemestrQuerySet)
YuklamaManager = models.Manager.from_queryset(YuklamaQuerySet)
