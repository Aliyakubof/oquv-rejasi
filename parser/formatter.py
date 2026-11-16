from parser.models import MajburiyFan, TanlovFani, TanlovVarianti


def sonni_matnga(qiymat: int | float | None) -> str:
    """Sonni Markdown katakchasiga moslaydi; None bo'lsa bo'sh matn qaytaradi."""
    return "" if qiymat is None else str(qiymat)


def md_qator(kataklar: list[str], qoshimcha: str = "") -> str:
    """Katakchalar ro'yxatidan Markdown jadval qatorini yig'adi."""
    return "| " + " | ".join(kataklar) + " |" + qoshimcha


def soat_kataklari(fan: MajburiyFan | TanlovVarianti | None) -> list[str]:
    """Fan yoki variantning oltita soat katakchasini tayyorlaydi."""
    if fan is None:
        return ["", "", "", "", "", ""]
    return [
        sonni_matnga(fan.auditoriya),
        sonni_matnga(fan.maruza),
        sonni_matnga(fan.amaliyot),
        sonni_matnga(fan.laboratoriya),
        sonni_matnga(fan.seminar),
        sonni_matnga(fan.kurs_ishi),
    ]


def _semestr_kataklari(
    fan: MajburiyFan | TanlovFani, faol_semestrlar: list[int]
) -> str:
    return "".join(
        f" {sonni_matnga(fan.semestr_kreditlari.get(s))} |"
        f" {sonni_matnga(fan.semestr_haftalik_soatlar.get(s))} |"
        for s in faol_semestrlar
    )


def _jadval_sarlavhasi(faol_semestrlar: list[int]) -> tuple[str, str]:
    sem_sarlavha = "".join(f" S{s} | H{s} |" for s in faol_semestrlar)
    sem_ajratgich = "".join(" --- | --- |" for _ in faol_semestrlar)
    sarlavha = (
        "| # | Kod | Nomi | Soat | Kredit | Auditoriya"
        " | Ma'ruza | Amaliyot | Laboratoriya | Seminar | Kurs ishi |" + sem_sarlavha
    )
    ajratgich = (
        "|---|-----|------|------|--------|------------|"
        "---------|----------|--------------|---------|-----------|" + sem_ajratgich
    )
    return sarlavha, ajratgich


def _tanlov_qatorlari(
    tanlov_fanlar: list[TanlovFani],
    faol_semestrlar: list[int],
    sarlavha: str,
    ajratgich: str,
) -> list[str]:
    qatorlar = ["", "## Tanlov Fanlar", "", sarlavha, ajratgich]
    bosh_semestr = "".join("  |  |" for _ in faol_semestrlar)
    for blok in tanlov_fanlar:
        birinchi = blok.variantlar[0] if blok.variantlar else None
        kataklar = [
            blok.raqam,
            birinchi.kod if birinchi else "",
            birinchi.nom if birinchi else "",
            sonni_matnga(blok.soat),
            sonni_matnga(blok.kredit),
            *soat_kataklari(birinchi),
        ]
        qatorlar.append(md_qator(kataklar, _semestr_kataklari(blok, faol_semestrlar)))
        for variant in blok.variantlar[1:]:
            var_kataklari = [
                "",
                variant.kod,
                variant.nom,
                "",
                "",
                *soat_kataklari(variant),
            ]
            qatorlar.append(md_qator(var_kataklari, bosh_semestr))
    return qatorlar


def _majburiy_qatorlar(
    majburiy_fanlar: list[MajburiyFan],
    faol_semestrlar: list[int],
    sarlavha: str,
    ajratgich: str,
) -> list[str]:
    qatorlar = ["## Majburiy Fanlar", "", sarlavha, ajratgich]
    for fan in majburiy_fanlar:
        kataklar = [
            fan.raqam,
            fan.kod,
            fan.nom,
            sonni_matnga(fan.soat),
            sonni_matnga(fan.kredit),
            *soat_kataklari(fan),
        ]
        qatorlar.append(md_qator(kataklar, _semestr_kataklari(fan, faol_semestrlar)))
    return qatorlar


def markdown_yarat(
    sarlavha_nomi: str,
    boshlanish_yili: str,
    daraja: str,
    muddat: str,
    talim_shakli: str,
    majburiy_fanlar: list[MajburiyFan],
    tanlov_fanlar: list[TanlovFani] | None = None,
) -> str:
    """O'qilgan o'quv reja ma'lumotlaridan chiroyli Markdown hujjat yasaydi."""
    barcha_fanlar = list(majburiy_fanlar) + list(tanlov_fanlar or [])
    faol_semestrlar = sorted(
        {sem for item in barcha_fanlar for sem in item.semestr_kreditlari}
        | {sem for item in barcha_fanlar for sem in item.semestr_haftalik_soatlar}
    )

    qatorlar = [f"# Oquv Reja: {sarlavha_nomi}", ""]
    for yorliq, qiymat in (
        ("Akademik daraja", daraja),
        ("O'qish muddati", muddat),
        ("Ta'lim shakli", talim_shakli),
    ):
        if qiymat:
            qatorlar.append(f"**{yorliq}:** {qiymat}")
    if daraja or muddat or talim_shakli:
        qatorlar.append("")

    sarlavha, ajratgich = _jadval_sarlavhasi(faol_semestrlar)
    qatorlar.extend(
        _majburiy_qatorlar(majburiy_fanlar, faol_semestrlar, sarlavha, ajratgich)
    )
    if tanlov_fanlar:
        qatorlar.extend(
            _tanlov_qatorlari(tanlov_fanlar, faol_semestrlar, sarlavha, ajratgich)
        )
    qatorlar.append("")
    if boshlanish_yili:
        qatorlar.extend(["---", f"**O'quv yili:** {boshlanish_yili}", ""])
    return "\n".join(qatorlar)
