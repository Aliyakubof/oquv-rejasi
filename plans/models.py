from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, Sum
from django.utils import timezone

from accounts.models import Department, Foydalanuvchi, OqituvchiProfil
from parser.models import derived_credits
from plans.managers import (
    FanManager,
    FanSemestrManager,
    FanVariantManager,
    YuklamaManager,
)

# Rate fixed by the owner: kurs ishi supervision is 2 contact hours per student,
# independent of the hours printed in the reja's kurs-ishi column.
KURS_ISHI_SOAT_TALABAGA = 2


class FanTuri(models.TextChoices):
    MAJBURIY = "MAJBURIY", "Majburiy"
    TANLOV = "TANLOV", "Tanlov"


class SoatTuri(models.TextChoices):
    MARUZA = "MARUZA", "Ma'ruza"
    AMALIYOT = "AMALIYOT", "Amaliyot"
    LABORATORIYA = "LABORATORIYA", "Laboratoriya"
    SEMINAR = "SEMINAR", "Seminar"
    KURS_ISHI = "KURS_ISHI", "Kurs ishi"


# Lecture is taught once to the whole intake; these three are taught per group.
PER_GURUH_TURLAR = (SoatTuri.AMALIYOT, SoatTuri.LABORATORIYA, SoatTuri.SEMINAR)

AUDITORIYA_MAYDONLARI: dict[str, str] = {
    SoatTuri.MARUZA: "maruza_soat",
    SoatTuri.AMALIYOT: "amaliyot_soat",
    SoatTuri.LABORATORIYA: "laboratoriya_soat",
    SoatTuri.SEMINAR: "seminar_soat",
}


class TalimYonalishi(models.Model):
    """Official classifier row: major code -> field of study / knowledge.

    Maintained by AOH via admin, one row per major, independent of any
    single reja upload. `OquvReja.bilim_sohasi_*`/`talim_sohasi_*`/
    `yonalish_nomi` are populated from here at import time.
    """

    kodi = models.CharField(max_length=20, unique=True)
    nomi = models.CharField(max_length=255)
    bilim_sohasi_kodi = models.CharField(max_length=10)
    bilim_sohasi_nomi = models.CharField(max_length=255)
    talim_sohasi_kodi = models.CharField(max_length=10)
    talim_sohasi_nomi = models.CharField(max_length=255)

    class Meta:
        verbose_name = "Ta'lim yo'nalishi (klassifikator)"
        verbose_name_plural = "Ta'lim yo'nalishlari (klassifikator)"
        ordering = ["kodi"]

    def __str__(self) -> str:
        return f"{self.kodi} {self.nomi}"


class OquvReja(models.Model):
    """One major intake: a curriculum (direction + start year + study form)."""

    bilim_sohasi_kodi = models.CharField(max_length=10)
    bilim_sohasi_nomi = models.CharField(max_length=255)
    talim_sohasi_kodi = models.CharField(max_length=10)
    talim_sohasi_nomi = models.CharField(max_length=255)
    yonalish_kodi = models.CharField(max_length=20)
    yonalish_nomi = models.CharField(max_length=255, blank=True)
    boshlanish_yili = models.PositiveSmallIntegerField(db_index=True)
    daraja = models.CharField(max_length=100, blank=True)
    talim_shakli = models.CharField(max_length=100, blank=True)
    davomiylik_yil = models.PositiveSmallIntegerField(default=4)
    talabalar_soni = models.PositiveIntegerField(null=True, blank=True)
    guruhlar_soni = models.PositiveSmallIntegerField(null=True, blank=True)
    guruh_prefiksi = models.CharField(
        max_length=20, blank=True, default="", help_text="Masalan: DI"
    )
    manba_fayl = models.CharField(max_length=255, blank=True)
    import_vaqti = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "O'quv reja"
        verbose_name_plural = "O'quv rejalar"
        constraints = [
            models.UniqueConstraint(
                fields=["yonalish_kodi", "boshlanish_yili", "talim_shakli"],
                name="uniq_reja_kod_yil_shakl",
            )
        ]

    def __str__(self) -> str:
        return f"{self.yonalish_nomi} {self.boshlanish_yili}"

    @property
    def semestrlar_soni(self) -> int:
        return self.davomiylik_yil * 2


class Guruh(models.Model):
    reja = models.ForeignKey(
        OquvReja, on_delete=models.CASCADE, related_name="guruhlar"
    )
    raqam = models.PositiveSmallIntegerField()
    nomi = models.CharField(max_length=50)

    class Meta:
        verbose_name = "Guruh"
        verbose_name_plural = "Guruhlar"
        ordering = ["reja", "raqam"]
        constraints = [
            models.UniqueConstraint(fields=["reja", "raqam"], name="uniq_guruh_raqam"),
            models.UniqueConstraint(fields=["reja", "nomi"], name="uniq_guruh_nomi"),
        ]

    def __str__(self) -> str:
        return self.nomi


class Fan(models.Model):
    """One curriculum line: a mandatory course or a selective slot.

    Every Fan owns 1+ FanVariant rows; a mandatory course's single variant is
    auto-selected at import, a selective slot stays unselected until the office
    head picks one. Only the selected variant counts in hour demand.
    """

    reja = models.ForeignKey(OquvReja, on_delete=models.CASCADE, related_name="fanlar")
    raqam = models.CharField(max_length=10, help_text="Masalan: 1.01 yoki 2.03")
    turi = models.CharField(max_length=10, choices=FanTuri.choices)
    jami_soat = models.PositiveIntegerField(null=True, blank=True)
    tanlangan_variant = models.ForeignKey(
        "FanVariant",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    objects = FanManager()

    class Meta:
        verbose_name = "Fan"
        verbose_name_plural = "Fanlar"
        ordering = ["raqam"]
        constraints = [
            models.UniqueConstraint(fields=["reja", "raqam"], name="uniq_fan_raqam"),
        ]
        indexes = [models.Index(fields=["reja", "turi"])]

    def __str__(self) -> str:
        variant = self.tanlangan_variant
        nomi = variant.nomi if variant else f"tanlanmagan ({self.get_turi_display()})"
        return f"{self.raqam} {nomi}"

    @property
    def kredit(self) -> int | None:
        return derived_credits(self.jami_soat)

    @property
    def effektiv_variant(self) -> "FanVariant | None":
        if self.tanlangan_variant_id is not None:
            return self.tanlangan_variant
        kesh = getattr(self, "_prefetched_objects_cache", {})
        if "variantlar" in kesh:
            variantlar = kesh["variantlar"]
            return min(variantlar, key=lambda v: v.pk) if variantlar else None
        return self.variantlar.first()

    def clean(self) -> None:
        if self.tanlangan_variant and self.tanlangan_variant.fan_id != self.pk:
            raise ValidationError(
                {"tanlangan_variant": "Variant boshqa fanga tegishli."}
            )


class FanVariant(models.Model):
    """Course content: the unit carrying a kafedra and hour breakdown."""

    fan = models.ForeignKey(Fan, on_delete=models.CASCADE, related_name="variantlar")
    kodi = models.CharField(max_length=50, blank=True)
    nomi = models.CharField(max_length=255)
    kafedra = models.ForeignKey(
        Department,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="fanlar",
    )
    auditoriya_soat = models.PositiveIntegerField(default=0)
    maruza_soat = models.PositiveIntegerField(default=0)
    amaliyot_soat = models.PositiveIntegerField(default=0)
    laboratoriya_soat = models.PositiveIntegerField(default=0)
    seminar_soat = models.PositiveIntegerField(default=0)
    kurs_ishi_soat = models.PositiveIntegerField(default=0)

    objects = FanVariantManager()

    class Meta:
        verbose_name = "Fan varianti"
        verbose_name_plural = "Fan variantlari"
        constraints = [
            models.UniqueConstraint(
                fields=["fan", "kodi", "nomi"], name="uniq_variant_fan_kod_nom"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.kodi} {self.nomi}".strip()


class FanSemestr(models.Model):
    """Materialized per-semester hour breakdown; the delegation anchor."""

    variant = models.ForeignKey(
        FanVariant, on_delete=models.CASCADE, related_name="semestrlar"
    )
    semestr = models.PositiveSmallIntegerField()
    kredit = models.PositiveSmallIntegerField(default=0)
    haftalik_soat = models.PositiveSmallIntegerField(default=0)
    maruza_soat = models.PositiveIntegerField(default=0)
    amaliyot_soat = models.PositiveIntegerField(default=0)
    laboratoriya_soat = models.PositiveIntegerField(default=0)
    seminar_soat = models.PositiveIntegerField(default=0)
    kurs_ishi_bor = models.BooleanField(default=False)

    objects = FanSemestrManager()

    class Meta:
        verbose_name = "Fan semestri"
        verbose_name_plural = "Fan semestrlari"
        ordering = ["semestr"]
        constraints = [
            models.UniqueConstraint(
                fields=["variant", "semestr"], name="uniq_fansemestr"
            ),
            models.CheckConstraint(
                condition=Q(semestr__gte=1) & Q(semestr__lte=12),
                name="chk_semestr_oraliq",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.variant} / {self.semestr}-semestr"

    @property
    def oquv_yili(self) -> int:
        return (self.semestr + 1) // 2

    @property
    def akademik_yil(self) -> int:
        return self.variant.fan.reja.boshlanish_yili + (self.semestr - 1) // 2

    def tur_soat(self, tur: str) -> int:
        maydon = AUDITORIYA_MAYDONLARI.get(tur)
        if maydon is None:
            raise ValueError(f"{tur} soati talabalar sonidan hisoblanadi")
        return getattr(self, maydon)


class Yuklama(models.Model):
    """One delegation row: a teacher takes one portion of a course-semester.

    Three shapes, enforced by chk_yuklama_shakl: MARUZA covers the whole
    intake (no guruh), per-group types cover exactly one guruh per row, and
    KURS_ISHI carries a supervised-student count instead of a guruh.
    """

    fan_semestr = models.ForeignKey(
        FanSemestr, on_delete=models.PROTECT, related_name="yuklamalar"
    )
    tur = models.CharField(max_length=15, choices=SoatTuri.choices)
    oqituvchi = models.ForeignKey(
        OqituvchiProfil, on_delete=models.PROTECT, related_name="yuklamalar"
    )
    guruh = models.ForeignKey(
        Guruh,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="yuklamalar",
    )
    talabalar_soni = models.PositiveIntegerField(null=True, blank=True)
    soat = models.PositiveIntegerField(default=0, editable=False)

    objects = YuklamaManager()

    class Meta:
        verbose_name = "Yuklama"
        verbose_name_plural = "Yuklamalar"
        constraints = [
            models.UniqueConstraint(
                fields=["fan_semestr", "tur"],
                condition=Q(tur="MARUZA"),
                name="uniq_maruza_yuklama",
            ),
            models.UniqueConstraint(
                fields=["fan_semestr", "tur", "guruh"],
                condition=Q(guruh__isnull=False),
                name="uniq_guruh_yuklama",
            ),
            models.UniqueConstraint(
                fields=["fan_semestr", "tur", "oqituvchi"],
                condition=Q(tur="KURS_ISHI"),
                name="uniq_kursishi_oqituvchi",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        tur__in=["AMALIYOT", "LABORATORIYA", "SEMINAR"],
                        guruh__isnull=False,
                        talabalar_soni__isnull=True,
                    )
                    | Q(
                        tur="MARUZA",
                        guruh__isnull=True,
                        talabalar_soni__isnull=True,
                    )
                    | Q(
                        tur="KURS_ISHI",
                        guruh__isnull=True,
                        talabalar_soni__isnull=False,
                        talabalar_soni__gt=0,
                    )
                ),
                name="chk_yuklama_shakl",
            ),
        ]
        indexes = [
            models.Index(fields=["oqituvchi", "tur"]),
            models.Index(fields=["fan_semestr", "tur"]),
        ]

    def __str__(self) -> str:
        return f"{self.oqituvchi} / {self.fan_semestr} / {self.get_tur_display()}"

    def hisoblangan_soat(self) -> int:
        if self.tur == SoatTuri.KURS_ISHI:
            return KURS_ISHI_SOAT_TALABAGA * (self.talabalar_soni or 0)
        return self.fan_semestr.tur_soat(self.tur)

    def save(self, *args: object, **kwargs: object) -> None:
        self.soat = self.hisoblangan_soat()
        super().save(*args, **kwargs)

    def clean(self) -> None:
        if self.fan_semestr_id is None or not self.tur:
            return
        self._clean_effektiv_variant()
        self._clean_soat_mavjud()
        if self.guruh_id is not None:
            self._clean_guruh_rejasi()
        if self.tur == SoatTuri.KURS_ISHI:
            if not self.talabalar_soni or self.talabalar_soni < 1:
                raise ValidationError(
                    {"talabalar_soni": "Talabalar soni kamida 1 bo'lishi kerak."}
                )
            self._clean_kurs_ishi_sigimi()

    def _clean_effektiv_variant(self) -> None:
        variant = self.fan_semestr.variant
        if variant.fan.tanlangan_variant_id != variant.pk:
            raise ValidationError({"fan_semestr": "Fan uchun bu variant tanlanmagan."})

    def _clean_soat_mavjud(self) -> None:
        if self.tur == SoatTuri.KURS_ISHI:
            if not self.fan_semestr.kurs_ishi_bor:
                raise ValidationError({"tur": "Bu fan semestrida kurs ishi yo'q."})
        elif self.fan_semestr.tur_soat(self.tur) == 0:
            raise ValidationError(
                {"tur": "Bu fan semestrida bunday mashg'ulot soati yo'q."}
            )

    def _clean_guruh_rejasi(self) -> None:
        if self.guruh.reja_id != self.fan_semestr.variant.fan.reja_id:
            raise ValidationError({"guruh": "Guruh boshqa o'quv rejaga tegishli."})

    def _clean_kurs_ishi_sigimi(self) -> None:
        reja = self.fan_semestr.variant.fan.reja
        if reja.talabalar_soni is None:
            raise ValidationError(
                {"talabalar_soni": "Rejada talabalar soni kiritilmagan."}
            )
        boshqalar = (
            Yuklama.objects.filter(fan_semestr=self.fan_semestr, tur=SoatTuri.KURS_ISHI)
            .exclude(pk=self.pk)
            .aggregate(jami=Sum("talabalar_soni"))["jami"]
            or 0
        )
        if boshqalar + self.talabalar_soni > reja.talabalar_soni:
            raise ValidationError(
                {
                    "talabalar_soni": (
                        f"Jami {boshqalar + self.talabalar_soni} talaba "
                        f"taqsimlanmoqda, rejada {reja.talabalar_soni} ta bor."
                    )
                }
            )


class TopshirishHolati(models.TextChoices):
    KUTILMOQDA = "KUTILMOQDA", "Ko'rib chiqilmoqda"
    QABUL_QILINDI = "QABUL_QILINDI", "Qabul qilindi"
    RAD_ETILDI = "RAD_ETILDI", "Rad etildi"


class DasturTopshirish(models.Model):
    """One attempt at submitting a course's O'quv Dastur, and its AOH review.

    Append-only: a variant can have many attempts (one per resubmission
    round), each immutable once reviewed. Never edit or delete a past
    attempt — that history is what lets both the teacher and the AOH see
    every prior rejection reason across the several reject/resubmit rounds
    a dastur typically goes through.
    """

    variant = models.ForeignKey(
        FanVariant, on_delete=models.CASCADE, related_name="dastur_topshirishlari"
    )
    urinish_raqami = models.PositiveSmallIntegerField()
    oqituvchi = models.ForeignKey(
        OqituvchiProfil, on_delete=models.PROTECT, related_name="dastur_topshirishlari"
    )
    fayl = models.FileField(upload_to="dasturlar/%Y/")
    holat = models.CharField(
        max_length=20,
        choices=TopshirishHolati.choices,
        default=TopshirishHolati.KUTILMOQDA,
        db_index=True,
    )
    izoh = models.TextField(blank=True)
    yuborilgan_vaqt = models.DateTimeField(default=timezone.now)
    korib_chiqilgan_vaqt = models.DateTimeField(null=True, blank=True)
    korib_chiqqan = models.ForeignKey(
        Foydalanuvchi,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        verbose_name = "Dastur topshirig'i"
        verbose_name_plural = "Dastur topshiriqlari"
        ordering = ["-yuborilgan_vaqt"]
        indexes = [
            models.Index(fields=["variant", "-yuborilgan_vaqt", "-id"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["variant", "urinish_raqami"],
                name="uniq_dastur_variant_urinish",
            ),
            models.UniqueConstraint(
                fields=["variant"],
                condition=models.Q(holat="KUTILMOQDA"),
                name="uniq_dastur_kutilmoqda_variant",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.variant} / {self.urinish_raqami}-urinish / "
            f"{self.get_holat_display()}"
        )


class KafedraTasdiqHolati(models.TextChoices):
    QORALAMA = "QORALAMA", "Qoralama"
    TASDIQDA = "TASDIQDA", "Tasdiqqa yuborilgan"
    TASDIQLANGAN = "TASDIQLANGAN", "Tasdiqlangan"
    QAYTARILGAN = "QAYTARILGAN", "Qaytarilgan"


class KafedraYuklamaTasdiq(models.Model):
    """Department workload approval status per academic year."""

    kafedra = models.ForeignKey(
        Department, on_delete=models.CASCADE, related_name="yuklama_tasdiqlari"
    )
    akademik_yil = models.PositiveSmallIntegerField(db_index=True)
    holat = models.CharField(
        max_length=20,
        choices=KafedraTasdiqHolati.choices,
        default=KafedraTasdiqHolati.QORALAMA,
        db_index=True,
    )
    yuborilgan_vaqt = models.DateTimeField(null=True, blank=True)
    tasdiqlangan_vaqt = models.DateTimeField(null=True, blank=True)
    tasdiqlagan = models.ForeignKey(
        Foydalanuvchi,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    izoh = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["kafedra", "akademik_yil"],
                name="uniq_kafedra_yil_tasdiq",
            )
        ]
        verbose_name = "Kafedra yuklama tasdig'i"
        verbose_name_plural = "Kafedra yuklama tasdiqlari"

    def __str__(self) -> str:
        return f"{self.kafedra.nomi} ({self.akademik_yil}) — {self.get_holat_display()}"


class AuditAmali(models.TextChoices):
    YARATILDI = "YARATILDI", "Yaratildi"
    TAHRIRLANDI = "TAHRIRLANDI", "Tahrirlandi"
    OCHIRILDI = "OCHIRILDI", "O'chirildi"
    TASDIQ_YUBORILDI = "TASDIQ_YUBORILDI", "Tasdiqqa yuborildi"
    TASDIQLANDI = "TASDIQLANDI", "Tasdiqlandi"
    QAYTARILDI = "QAYTARILDI", "Qaytarildi"


class AuditYozuvi(models.Model):
    """Activity tracking across curriculum and workload operations."""

    foydalanuvchi = models.ForeignKey(
        Foydalanuvchi,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_yozuvlari",
    )
    amal = models.CharField(max_length=30, choices=AuditAmali.choices, db_index=True)
    model_nomi = models.CharField(max_length=60, db_index=True)
    obyekt_id = models.CharField(max_length=64, blank=True)
    tavsif = models.TextField()
    vaqt = models.DateTimeField(default=timezone.now, db_index=True)
    ip_manzil = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        verbose_name = "Audit yozuvi"
        verbose_name_plural = "Audit jurnali"
        ordering = ["-vaqt"]
        indexes = [
            models.Index(fields=["model_nomi", "-vaqt"]),
        ]

    def __str__(self) -> str:
        foyd = self.foydalanuvchi.get_full_name() if self.foydalanuvchi else "Tizim"
        qisqa = self.tavsif[:30]
        return f"[{self.vaqt:%d.%m %H:%M}] {foyd} — {self.get_amal_display()}: {qisqa}"
