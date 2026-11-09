"""Builds the docxtpl render context for one FanVariant's o'quv dastur."""

from django.utils import timezone

from accounts.services import universitet_nomi
from plans.dastur.mavzular import SOAT_MUSTAQIL_TOPSHIRIQDA, Natija, bosh_mavzular
from plans.models import FanSemestr, FanVariant

BLANK = "_____"

# No model field records the language of instruction or the city; every
# curriculum the platform handles is taught in Uzbek from Namangan.
TALIM_TILI = "O‘zbek"
SHAHAR = "Namangan"

TN_SONI = 8


def _soatlar_va_mavzular(variant: FanVariant, mustaqil_soat: int) -> dict[str, object]:
    return {
        "hours": {
            "lecture": _soat_matni(variant.maruza_soat),
            "practice": _soat_matni(variant.amaliyot_soat),
            "lab": _soat_matni(variant.laboratoriya_soat),
            "seminar": _soat_matni(variant.seminar_soat),
            "self_study": _soat_matni(mustaqil_soat),
            "coursework": _soat_matni(variant.kurs_ishi_soat),
        },
        "purpose": "",
        "tasks": "",
        "prerequisites": ["", "", ""],
        "outcomes": {
            "professional": [Natija(f"TN{i}", "") for i in range(1, TN_SONI + 1)],
            "skills": [Natija(f"TN{i}", "") for i in range(1, TN_SONI + 1)],
        },
        "lectures": bosh_mavzular(variant.maruza_soat, "M"),
        "practicals": bosh_mavzular(variant.amaliyot_soat, "A"),
        "labs": bosh_mavzular(variant.laboratoriya_soat, "L"),
        "seminars": bosh_mavzular(variant.seminar_soat, "S"),
        "self_study_tasks": bosh_mavzular(
            mustaqil_soat, "", soat_mavzuda=SOAT_MUSTAQIL_TOPSHIRIQDA
        ),
    }


def dastur_kontekst(variant: FanVariant) -> dict[str, object]:
    fan = variant.fan
    reja = fan.reja
    semestrlar = list(variant.semestrlar.order_by("semestr"))
    mustaqil_soat = max((fan.jami_soat or 0) - variant.auditoriya_soat, 0)

    return {
        "university": _universitet_nomi(),
        "city": SHAHAR,
        "language": TALIM_TILI,
        "kafedra": variant.kafedra.nomi if variant.kafedra else "",
        "kafedra_council": {"year": BLANK, "date": BLANK},
        "major": {
            "bilim_sohasi": _kod_bilan(reja.bilim_sohasi_kodi, reja.bilim_sohasi_nomi),
            "talim_sohasi": _kod_bilan(reja.talim_sohasi_kodi, reja.talim_sohasi_nomi),
            "talim_yonalishi": _kod_bilan(reja.yonalish_kodi, reja.yonalish_nomi),
        },
        "education_form": reja.talim_shakli.lower(),
        "year": _muqova_yili(semestrlar),
        "course": {
            "code": variant.kodi,
            "name": variant.nomi,
            "module_type": fan.get_turi_display(),
        },
        "academic_years_str": _oquv_yillari_matni(semestrlar),
        "semesters_str": ", ".join(str(fs.semestr) for fs in semestrlar),
        "credits_str": ", ".join(str(fs.kredit) for fs in semestrlar),
        "weekly_hours_str": ", ".join(str(fs.haftalik_soat) for fs in semestrlar),
        "plan_number": _kod_bilan(reja.yonalish_kodi, fan.raqam),
        "total_hours": _soat_matni(fan.jami_soat or 0),
        "classroom_total": _soat_matni(variant.auditoriya_soat),
        **_soatlar_va_mavzular(variant, mustaqil_soat),
    }


def _kod_bilan(kodi: str, matn: str) -> str:
    """Official documents join a classifier code to its name with a spaced
    en-dash — used for both the soha/yonalish lines and the plan number."""
    return f"{kodi} – {matn}" if kodi else matn


def _soat_matni(soat: int) -> str:
    return str(soat) if soat else "-"


def _oquv_yillari_matni(semestrlar: list[FanSemestr]) -> str:
    yillar = sorted({fs.akademik_yil for fs in semestrlar})
    return ", ".join(f"{yil}/{yil + 1}" for yil in yillar)


def _muqova_yili(semestrlar: list[FanSemestr]) -> int:
    if not semestrlar:
        return timezone.now().year
    return min(fs.akademik_yil for fs in semestrlar)


def _universitet_nomi() -> str:
    return universitet_nomi(bosh="Turan International University")
