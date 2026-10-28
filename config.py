import os
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv


load_dotenv()


class Config:
    APP_ENV = os.getenv("APP_ENV", "development")
    IS_PRODUCTION = APP_ENV == "production"

    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
    BASE_DIR = Path(__file__).resolve().parent
    MYSQL_USER = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
    MYSQL_PORT = os.getenv("MYSQL_PORT", "3306")
    MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "checkin_event")
    # Username/password are percent-encoded before going into the URI -- special
    # characters like @, :, or / in a real password (e.g. "Admin@libtestDB123")
    # would otherwise be misread as URI delimiters (e.g. the "@" splitting into
    # a bogus extra host segment) and connect to the wrong place or fail outright.
    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{quote_plus(MYSQL_USER)}:{quote_plus(MYSQL_PASSWORD)}"
        f"@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}?charset=utf8mb4"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
        "pool_size": int(os.getenv("DB_POOL_SIZE", "10")),
        "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "20")),
    }

    # Behind the IIS reverse proxy in production, requests arrive over HTTPS but
    # are forwarded to waitress over plain HTTP -- ProxyFix (see app.py) restores
    # the original scheme/host from X-Forwarded-* headers so these settings are
    # evaluated correctly instead of always looking like an insecure HTTP request.
    SESSION_COOKIE_SECURE = IS_PRODUCTION
    PREFERRED_URL_SCHEME = "https" if IS_PRODUCTION else "http"
    MAIL_SERVER = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
    MAIL_USERNAME = os.getenv("MAIL_USERNAME", "")
    # Gmail app passwords are sometimes copied with spaces (e.g. xxxx xxxx xxxx xxxx)
    MAIL_PASSWORD = (os.getenv("MAIL_PASSWORD", "") or "").replace(" ", "")
    MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "true").lower() in {"1", "true", "yes", "on"}
    MAIL_USE_SSL = os.getenv("MAIL_USE_SSL", "false").lower() in {"1", "true", "yes", "on"}
    MAIL_SENDER = os.getenv("MAIL_SENDER", MAIL_USERNAME)
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER", MAIL_SENDER)
    ADMIN_DEFAULT_USERNAME = os.getenv("ADMIN_DEFAULT_USERNAME", "admin")
    ADMIN_DEFAULT_PASSWORD = os.getenv("ADMIN_DEFAULT_PASSWORD", "admin123")
    REMEMBER_LOGIN_DAYS = int(os.getenv("REMEMBER_LOGIN_DAYS", "30"))
    PERMANENT_SESSION_LIFETIME = timedelta(days=REMEMBER_LOGIN_DAYS)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
