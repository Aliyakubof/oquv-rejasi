"""Oflayn zaxira sahifasi va ildiz darajasidagi Service Worker ko'rinishlari."""

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render


def offline_sahifa(request: HttpRequest) -> HttpResponse:
    """Alohida oflayn zaxira ekranini ko'rsatadi (foydalanuvchi ma'lumotisiz)."""
    javob = render(request, "web/offline.html")
    javob["Cache-Control"] = "public, max-age=300"
    return javob


def service_worker_skript(request: HttpRequest) -> HttpResponse:
    """Oflayn navigatsiya zaxirasi uchun Service Worker skriptini beradi."""
    javob = render(
        request,
        "web/sw.js",
        content_type="application/javascript; charset=utf-8",
    )
    javob["Cache-Control"] = "no-cache, no-store, must-revalidate"
    javob["Service-Worker-Allowed"] = "/"
    return javob
