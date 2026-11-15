"""Split whole-course hour breakdowns into per-semester portions.

Pure functions, no ORM. The reja sheet gives one hour total per course plus
per-semester weekly hours; a semester is exactly 15 weeks, so weekly hours are
the natural split weights. Largest-remainder rounding keeps every component's
semester sum exactly equal to the parsed total.
"""

HAFTA_SEMESTRDA = 15

BREAKDOWN_MAYDONLARI = (
    "maruza_soat",
    "amaliyot_soat",
    "laboratoriya_soat",
    "seminar_soat",
)


def largest_remainder_split(total: int, weights: dict[int, int]) -> dict[int, int]:
    """Split total across keys proportionally to weights, summing exactly.

    Floors each share, then hands the leftover to the largest remainders;
    ties go to the lower semester so results are deterministic.
    """
    if not weights:
        return {}
    jami_vazn = sum(weights.values())
    if jami_vazn == 0:
        weights = dict.fromkeys(weights, 1)
        jami_vazn = len(weights)
    natija = {s: (total * w) // jami_vazn for s, w in weights.items()}
    qoldiqlar = {s: (total * w) % jami_vazn for s, w in weights.items()}
    yetishmaydi = total - sum(natija.values())
    for s in sorted(weights, key=lambda s: (-qoldiqlar[s], s))[:yetishmaydi]:
        natija[s] += 1
    return natija


def semester_weights(weekly: dict[int, int], credits: dict[int, int]) -> dict[int, int]:
    """Weekly contact hours are the preferred weight per semester; a semester
    with 0 weekly hours or present only in `credits` still gets a weight
    (and so a FanSemestr row) instead of silently losing its credits."""
    return {
        s: weekly.get(s) or credits.get(s, 0) for s in weekly.keys() | credits.keys()
    }


def split_breakdown(
    maruza: int,
    amaliyot: int,
    laboratoriya: int,
    seminar: int,
    weekly: dict[int, int],
    credits: dict[int, int],
) -> tuple[dict[int, dict[str, int]], list[str]]:
    """Return per-semester {sem: {field: hours}} rows plus warnings.

    Kurs ishi is deliberately absent: its workload is 2h per student, not a
    share of the parsed classroom hours.
    """
    vaznlar = semester_weights(weekly, credits)
    if not vaznlar:
        return {}, ["semestr taqsimoti yo'q: soatlar semestrlarga bo'linmadi"]

    satrlar: dict[int, dict[str, int]] = {s: {} for s in vaznlar}
    qiymatlar = (maruza, amaliyot, laboratoriya, seminar)
    for maydon, jami in zip(BREAKDOWN_MAYDONLARI, qiymatlar):
        for s, soat in largest_remainder_split(jami, vaznlar).items():
            satrlar[s][maydon] = soat

    return satrlar, _mos_kelish_ogohlantirishlari(satrlar, weekly, sum(qiymatlar))


def _mos_kelish_ogohlantirishlari(
    satrlar: dict[int, dict[str, int]], weekly: dict[int, int], auditoriya: int
) -> list[str]:
    """Cross-check the split against the 15-week rule (weekly hours x 15)."""
    if not weekly:
        return []
    kutilgan = sum(weekly.values()) * HAFTA_SEMESTRDA
    if kutilgan != auditoriya:
        return [
            f"haftalik soat x {HAFTA_SEMESTRDA} = {kutilgan}, "
            f"auditoriya bo'linmasi {auditoriya} ga teng emas"
        ]
    # Per-semester check only when the totals agree; otherwise the overall
    # warning already explains every per-semester difference.
    ogohlantirishlar = []
    for s, haftalik in weekly.items():
        hisoblangan = sum(satrlar.get(s, {}).values())
        if haftalik * HAFTA_SEMESTRDA != hisoblangan:
            ogohlantirishlar.append(
                f"{s}-semestr: haftalik {haftalik} x {HAFTA_SEMESTRDA} = "
                f"{haftalik * HAFTA_SEMESTRDA}, bo'lingan soat {hisoblangan}"
            )
    return ogohlantirishlar
