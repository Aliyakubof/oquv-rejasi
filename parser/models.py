"""Parser va formatlovchi (hamda kelajakdagi serializerlar) o'rtasidagi
umumiy ma'lumot modellari.

Sonlar bu yerda `int | None` holida turadi — matnga aylantirish bilan
formatlovchi shug'ullanadi. Shu dataclasslar tufayli parser natijasini
JSON yoki bazaga saqlash ham ancha oson.
"""

from dataclasses import dataclass, field
from typing import NamedTuple


class TahlilXatosi(Exception):
    """Varaq tuzilmasini ishonchli aniqlab bo'lmaganda ko'tariladi.

    Taxminiy ustun yoki qator raqamiga tayanib ketishdan ko'ra xato bergan
    ma'qul — aks holda ko'rinishi to'g'ri, lekin mazmuni xato raqamlar chiqadi.
    """


class UstunJoyi(NamedTuple):
    """Bitta o'quv reja varag'idagi 0-dan boshlanadigan ustun indekslari.

    Ba'zi fayllarda laboratoriya, seminar yoki kurs ishi ustunlari bo'lmasligi
    mumkin — shunday holatda ular None bo'ladi va fan 0 soat bilan o'qilaveradi.
    """

    raqam: int
    kod: int
    nom: int
    soat: int
    auditoriya: int
    maruza: int
    amaliyot: int
    laboratoriya: int | None
    seminar: int | None
    kurs_ishi: int | None

    @property
    def taqsimot(
        self,
    ) -> tuple[int, int, int, int | None, int | None, int | None]:
        """Auditoriya va soat turlari ustunlarining tartibli ro'yxati."""
        return (
            self.auditoriya,
            self.maruza,
            self.amaliyot,
            self.laboratoriya,
            self.seminar,
            self.kurs_ishi,
        )


def hisoblangan_kredit(soat: int | None) -> int | None:
    """Umumiy soatdan kelib chiqadigan kredit (1 kredit = 30 soat)."""
    return None if soat is None else soat // 30


@dataclass
class MajburiyFan:
    """Bitta majburiy fan va uning barcha soat taqsimoti."""

    raqam: str
    kod: str
    nom: str
    soat: int | None
    auditoriya: int
    maruza: int
    amaliyot: int
    laboratoriya: int
    seminar: int
    kurs_ishi: int
    semestr_kreditlari: dict[int, int] = field(default_factory=dict)
    semestr_haftalik_soatlar: dict[int, int] = field(default_factory=dict)

    @property
    def kredit(self) -> int | None:
        return hisoblangan_kredit(self.soat)


@dataclass
class TanlovVarianti:
    """Tanlov fani ichidagi bitta muqobil fan varianti."""

    kod: str
    nom: str
    auditoriya: int
    maruza: int
    amaliyot: int
    laboratoriya: int
    seminar: int
    kurs_ishi: int


@dataclass
class TanlovFani:
    """Bitta tanlov bloki: umumiy soat/kreditlar va uning variantlari."""

    raqam: str
    soat: int | None
    semestr_kreditlari: dict[int, int] = field(default_factory=dict)
    semestr_haftalik_soatlar: dict[int, int] = field(default_factory=dict)
    variantlar: list[TanlovVarianti] = field(default_factory=list)

    @property
    def kredit(self) -> int | None:
        return hisoblangan_kredit(self.soat)


@dataclass
class TahlilNatijasi:
    """Bitta Excel kitobidan yig'ilgan hamma ma'lumot va ogohlantirishlar.

    Jiddiy tuzilma xatolari TahlilXatosi bo'lib ko'tariladi, shuning uchun
    TahlilNatijasi qo'lingizga tushdimi — demak bemalol ishlatish mumkin.
    """

    yonalish_kodi: str
    yonalish_nomi: str
    boshlanish_yili: str
    daraja: str
    davomiylik_yil: float
    talim_shakli: str
    majburiy_fanlar: list[MajburiyFan]
    tanlov_fanlar: list[TanlovFani]
    ogohlantirishlar: list[str] = field(default_factory=list)
