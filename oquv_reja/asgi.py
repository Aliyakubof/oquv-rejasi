"""
oquv_reja loyihasi uchun ASGI sozlamalari.

Modul darajasidagi ``application`` nomli ASGI obyektini taqdim etadi.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "oquv_reja.settings")

application = get_asgi_application()
