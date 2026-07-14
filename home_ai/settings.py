import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "django-insecure-@13pmv_u_c-(#-cp)_r4g=0dknd#je0u(1n1#ad25zw*vkqg5i"
DEBUG = True

ALLOWED_HOSTS = []


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "home_ai",
    "accounts",
    "abbreviation_tool",
    "jssdm",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "home_ai.operations.RetentionCleanupMiddleware",
]

ROOT_URLCONF = "home_ai.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "home_ai.context_processors.feature_flags",
            ],
        },
    },
]

WSGI_APPLICATION = "home_ai.wsgi.application"


if os.getenv("DATABASE_ENGINE", "postgresql").lower() in {"postgres", "postgresql"}:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("POSTGRES_DB", "home_ai"),
            "USER": os.getenv("POSTGRES_USER", "home_ai"),
            "PASSWORD": os.getenv("POSTGRES_PASSWORD", "home_ai_dev"),
            "HOST": os.getenv("POSTGRES_HOST", "127.0.0.1"),
            "PORT": os.getenv("POSTGRES_PORT", "5432"),
            "CONN_MAX_AGE": int(os.getenv("POSTGRES_CONN_MAX_AGE", "60")),
        }
    }
else:
    # Offline builds use SQLite; deployments set DATABASE_ENGINE=postgresql.
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
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


LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True


STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]

LOGIN_REDIRECT_URL = "/"
LOGIN_URL = "/login/"

DOCX_ABBREVIATION_TOOL_ENABLED = os.getenv(
    "DOCX_ABBREVIATION_TOOL_ENABLED", "true"
).lower() in {"1", "true", "yes", "on"}
DOCX_ABBREVIATION_SESSION_TTL_MINUTES = int(
    os.getenv("DOCX_ABBREVIATION_SESSION_TTL_MINUTES", "30")
)
DOCX_ABBREVIATION_TEMP_ROOT = os.getenv(
    "DOCX_ABBREVIATION_TEMP_ROOT", str(BASE_DIR / ".private_docx_sessions")
)
DOCX_ABBREVIATION_MAX_UNCOMPRESSED_MB = int(
    os.getenv("DOCX_ABBREVIATION_MAX_UNCOMPRESSED_MB", "250")
)
DOCX_ABBREVIATION_MAX_ZIP_RATIO = int(
    os.getenv("DOCX_ABBREVIATION_MAX_ZIP_RATIO", "100")
)
DOCX_ABBREVIATION_MAX_ZIP_MEMBERS = int(
    os.getenv("DOCX_ABBREVIATION_MAX_ZIP_MEMBERS", "5000")
)
DOCX_ABBREVIATION_MAX_ACTIVE_SESSIONS = int(
    os.getenv("DOCX_ABBREVIATION_MAX_ACTIVE_SESSIONS", "5")
)
DOCX_ABBREVIATION_MAX_SUGGESTIONS = int(
    os.getenv("DOCX_ABBREVIATION_MAX_SUGGESTIONS", "5000")
)
DOCX_ABBREVIATION_ANALYSIS_TIMEOUT_SECONDS = int(
    os.getenv("DOCX_ABBREVIATION_ANALYSIS_TIMEOUT_SECONDS", "60")
)
DATA_RETENTION_CLEANUP_INTERVAL_SECONDS = int(
    os.getenv("DATA_RETENTION_CLEANUP_INTERVAL_SECONDS", "900")
)

LOG_DIR = Path(os.getenv("APP_LOG_DIR", str(BASE_DIR / "logs")))
LOG_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json_redacted": {"()": "home_ai.operations.RedactingJsonFormatter"}
    },
    "handlers": {
        "structured_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_DIR / "application.jsonl",
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "json_redacted",
            "encoding": "utf-8",
        },
        "console": {"class": "logging.StreamHandler", "formatter": "json_redacted"},
    },
    "loggers": {
        "django.request": {
            "handlers": ["structured_file", "console"],
            "level": "WARNING",
            "propagate": False,
        },
        "home_ai": {
            "handlers": ["structured_file", "console"],
            "level": "INFO",
            "propagate": False,
        },
        "abbreviation_tool": {
            "handlers": ["structured_file", "console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
