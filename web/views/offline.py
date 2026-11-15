"""Offline fallback page and root-scoped Service Worker views."""

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render


def offline_sahifa(request: HttpRequest) -> HttpResponse:
    """Render the standalone branded offline fallback screen (no user data)."""
    javob = render(request, "web/offline.html")
    javob["Cache-Control"] = "public, max-age=300"
    return javob


def service_worker_js(request: HttpRequest) -> HttpResponse:
    """Serve the root-scoped Service Worker script for offline navigation fallback."""
    javob = render(
        request,
        "web/sw.js",
        content_type="application/javascript; charset=utf-8",
    )
    javob["Cache-Control"] = "no-cache, no-store, must-revalidate"
    javob["Service-Worker-Allowed"] = "/"
    return javob
