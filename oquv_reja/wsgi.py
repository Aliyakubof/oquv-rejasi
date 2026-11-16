"""
oquv_reja loyihasi uchun WSGI sozlamalari.

Modul darajasidagi ``application`` nomli WSGI obyektini taqdim etadi.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "oquv_reja.settings")

application = get_wsgi_application()
