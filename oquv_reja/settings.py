"""
oquv_reja loyihasining asosiy Django sozlamalari.
"""

import sys
from pathlib import Path

import environ

# Loyiha ildiz katalogi: BASE_DIR / 'ichki_papka' shaklida yo'l tuziladi.
BASE_DIR = Path(__file__).resolve().parent.parent
IS_TEST = "test" in sys.argv

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env", overwrite=True)


# Ishga tushirish sozlamalari (.env orqali boshqariladi)
# XAVFSIZLIK: production da maxfiy kalitni ochiq qoldirmang!
SECRET_KEY = env("SECRET_KEY")

# XAVFSIZLIK: production muhitida DEBUG=False qiling!
DEBUG = env.bool("DEBUG", default=False)

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])

CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

TRUST_X_FORWARDED_FOR = env.bool("TRUST_X_FORWARDED_FOR", default=False)
TRUSTED_PROXY_IPS = env.list("TRUSTED_PROXY_IPS", default=[])

if not DEBUG:
    SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=True)
    CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=True)
    SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31536000)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool(
        "SECURE_HSTS_INCLUDE_SUBDOMAINS", default=True
    )
    SECURE_HSTS_PRELOAD = env.bool("SECURE_HSTS_PRELOAD", default=True)
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"


# Ilovalar ro'yxati

HEMIS_API_KEY = env(
    "HEMIS_API_KEY",
    default="hemis-secret-key-2026" if (DEBUG or IS_TEST) else "",
)
HEMIS_BASE_URL = env("HEMIS_BASE_URL", default="").strip()
HEMIS_TIMEOUT = env.int("HEMIS_TIMEOUT", default=15)
TELEGRAM_BOT_TOKEN = env("TELEGRAM_BOT_TOKEN", default="").strip()
LOGIN_MAX_URINISH = env.int("LOGIN_MAX_URINISH", default=5)
LOGIN_BLOK_SONIYA = env.int("LOGIN_BLOK_SONIYA", default=300)
API_MAX_SOROV_DAQIQA = env.int("API_MAX_SOROV_DAQIQA", default=120)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts",
    "plans",
    "web",
]

AUTH_USER_MODEL = "accounts.Foydalanuvchi"

LOGIN_URL = "kirish"
LOGIN_REDIRECT_URL = "bosh_sahifa"
LOGOUT_REDIRECT_URL = "kirish"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "web.middleware.FaolFoydalanuvchiMiddleware",
    "web.middleware.ParolAlmashtirishMajburiyMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "oquv_reja.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "web.context_processors.debug_rejim",
            ],
        },
    },
]

WSGI_APPLICATION = "oquv_reja.wsgi.application"


# Ma'lumotlar bazasi

DATABASES = {
    "default": {
        **env.db("DATABASE_URL"),
        "CONN_MAX_AGE": env.int("DB_CONN_MAX_AGE", default=0 if IS_TEST else 60),
    },
}

REDIS_URL = env("REDIS_URL", default="").strip()
if REDIS_URL and not IS_TEST:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }


# Parol tekshiruvlari

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation"
        ".UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Til va vaqt mintaqasi

LANGUAGE_CODE = "uz"

TIME_ZONE = "Asia/Tashkent"

USE_I18N = True

USE_TZ = True


# Statik fayllar (CSS, JavaScript, rasmlar)

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

if not DEBUG and not IS_TEST:
    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage",
        },
    }

# Yuklangan o'quv reja fayllari saqlanadigan joy
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Standart birlamchi kalit maydoni turi

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

if IS_TEST:
    import tempfile

    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    MEDIA_ROOT = Path(tempfile.gettempdir()) / "oquv_reja_test_media"

_LOG_HANDLERS: dict[str, dict[str, object]] = {
    "console": {
        "class": "logging.StreamHandler",
        "formatter": "standart",
    },
}
_ROOT_HANDLERS = ["console"]

if not IS_TEST:
    LOG_DIR = BASE_DIR / "logs"
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    _LOG_HANDLERS["file"] = {
        "class": "logging.handlers.RotatingFileHandler",
        "filename": str(LOG_DIR / "app.log"),
        "maxBytes": 5 * 1024 * 1024,
        "backupCount": 5,
        "encoding": "utf-8",
        "formatter": "standart",
    }
    _ROOT_HANDLERS.append("file")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standart": {
            "format": "[{asctime}] {levelname} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": _LOG_HANDLERS,
    "root": {
        "handlers": _ROOT_HANDLERS,
        "level": "DEBUG" if DEBUG else "INFO",
    },
    "loggers": {
        "django.request": {
            "handlers": _ROOT_HANDLERS,
            "level": "ERROR" if IS_TEST else "WARNING",
            "propagate": False,
        },
    },
}
