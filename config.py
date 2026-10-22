import os

from dotenv import load_dotenv

# Đọc file .env ở thư mục gốc (khi chạy `python app.py` không ai tự đọc giúp);
# biến môi trường đã đặt sẵn trên máy vẫn được ưu tiên.
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# Preview-only config: uses local SQLite so the app can run without MySQL/MariaDB
# installed. Production config (on the IIS server) uses real MYSQL_* env vars
# per DEPLOYMENT.md -- this file is only for previewing UI changes locally.


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-preview-only-not-for-production")

    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///preview.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    MAIL_SERVER = os.getenv("MAIL_SERVER", "localhost")
    MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
    MAIL_USERNAME = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
    MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "true").lower() == "true"
    MAIL_USE_SSL = os.getenv("MAIL_USE_SSL", "false").lower() == "true"
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_SENDER")

    ADMIN_DEFAULT_USERNAME = os.getenv("ADMIN_DEFAULT_USERNAME", "admin")
    ADMIN_DEFAULT_PASSWORD = os.getenv("ADMIN_DEFAULT_PASSWORD", "admin123")
