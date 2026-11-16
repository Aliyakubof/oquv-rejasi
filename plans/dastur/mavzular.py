"""O'quv dasturidagi mashg'ulot jadvallari uchun bo'sh mavzu qatorlarini tuzadi.

Qatorlar soni jami soatga bog'liq — standart shaklda har bir mavzu belgilangan
soatga ega, o'qituvchi esa Word'da faqat mavzu nomlarini to'ldirib chiqadi.
"""

from dataclasses import dataclass

SOAT_MAVZUDA = 2
SOAT_MUSTAQIL_TOPSHIRIQDA = 4


@dataclass(frozen=True)
class Mavzu:
    code: str
    title: str
    hours: int


@dataclass(frozen=True)
class Natija:
    code: str
    text: str


def bosh_mavzular(
    soat: int, prefiks: str, *, soat_mavzuda: int = SOAT_MAVZUDA
) -> list[Mavzu]:
    """`soat // soat_mavzuda` ta `{prefiks}1`, `{prefiks}2`... bo'sh qatorlar yasaydi.

    Qoldiq chiqsa oxiriga qisqaroq qator qo'shiladi; 0 dan kichik bo'lsa bo'sh.
    5-bo'limda 2 soat/mavzu, 6-bo'lim mustaqil topshiriqlarda esa 4 soat/topshiriq.
    """
    if soat <= 0:
        return []
    to_liq, qoldiq = divmod(soat, soat_mavzuda)
    mavzular = [
        Mavzu(code=f"{prefiks}{i}", title="", hours=soat_mavzuda)
        for i in range(1, to_liq + 1)
    ]
    if qoldiq:
        mavzular.append(Mavzu(code=f"{prefiks}{to_liq + 1}", title="", hours=qoldiq))
    return mavzular
