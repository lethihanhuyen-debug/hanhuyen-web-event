import logging
from logging.handlers import RotatingFileHandler

from flask import Flask, request
from sqlalchemy import inspect, text
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash

from config import Config
from event_checkin.controllers.admin_controller import admin_bp
from event_checkin.controllers.certificate_controller import certificate_bp
from event_checkin.controllers.checkin_controller import checkin_bp
from event_checkin.controllers.lucky_draw_controller import lucky_bp
from event_checkin.controllers.register_controller import register_bp
from event_checkin.extensions import mail
from event_checkin.models import db
from event_checkin.models.admin import Admin
from event_checkin.models.event import Event


def _indexed_columns(inspector, table_name):
    columns = set()
    for index in inspector.get_indexes(table_name):
        columns.update(index["column_names"])
    return columns


def ensure_schema_upgrades():
    """Additive, idempotent column/index fixes only (safe to run on every
    startup). Larger structural changes (new tables, data migrations) ship as
    explicit scripts under event_checkin/migrations/ and must be run by hand
    per DEPLOYMENT.md -- they are NOT run automatically here."""
    inspector = inspect(db.engine)
    if "events" not in inspector.get_table_names():
        return
    event_columns = {column["name"] for column in inspector.get_columns("events")}
    with db.engine.begin() as connection:
        if "certificate_enabled" not in event_columns:
            connection.execute(text("ALTER TABLE events ADD COLUMN certificate_enabled BOOLEAN NOT NULL DEFAULT TRUE"))
        if "certificate_template" not in event_columns:
            connection.execute(text("ALTER TABLE events ADD COLUMN certificate_template VARCHAR(255)"))
        if "certificate_layout" not in event_columns:
            connection.execute(text("ALTER TABLE events ADD COLUMN certificate_layout TEXT"))
        if "co_so" not in event_columns:
            connection.execute(text("ALTER TABLE events ADD COLUMN co_so VARCHAR(50)"))
        if "so_luong_toi_da" not in event_columns:
            connection.execute(text("ALTER TABLE events ADD COLUMN so_luong_toi_da INT"))

        if "don_vi" in inspector.get_table_names() and "is_active" not in _indexed_columns(inspector, "don_vi"):
            connection.execute(text("CREATE INDEX ix_don_vi_is_active ON don_vi (is_active)"))
        if "email_logs" in inspector.get_table_names():
            email_log_indexes = {index["name"] for index in inspector.get_indexes("email_logs")}
            if "ix_email_logs_lookup" not in email_log_indexes:
                connection.execute(
                    text("CREATE INDEX ix_email_logs_lookup ON email_logs (ma_cbsv, event_id, email_type, sent_at)")
                )


def ensure_default_records():
    from datetime import datetime, timedelta

    admin_username = Config.ADMIN_DEFAULT_USERNAME
    admin_password = Config.ADMIN_DEFAULT_PASSWORD
    admin = Admin.query.filter_by(username=admin_username).first()
    if not admin:
        admin = Admin(
            username=admin_username,
            password_hash=generate_password_hash(admin_password),
            role="super_admin",
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db.session.add(admin)
        db.session.flush()
    elif admin.password_hash == "not-used":
        admin.password_hash = generate_password_hash(admin_password)

    if not Event.query.first():
        now = datetime.utcnow()
        db.session.add(
            Event(
                ten_su_kien="Su kien mac dinh",
                mo_ta="Su kien mac dinh cho luong dang ky va check-in hien tai.",
                dia_diem="USSH",
                ngay_bat_dau=now,
                ngay_ket_thuc=now + timedelta(hours=4),
                thang=now.month,
                nam=now.year,
                thoi_gian_mo_dang_ky=now - timedelta(days=30),
                thoi_gian_dong_dang_ky=now + timedelta(days=30),
                trang_thai="ongoing",
                created_by=admin.id,
                created_at=now,
            )
        )

    db.session.commit()


def _configure_logging(app):
    if not app.config["IS_PRODUCTION"]:
        return
    log_dir = app.config["BASE_DIR"] / "logs"
    log_dir.mkdir(exist_ok=True)
    handler = RotatingFileHandler(log_dir / "app.log", maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
    handler.setLevel(logging.INFO)
    # Attach to the root logger (not just app.logger/werkzeug) so module-level
    # loggers elsewhere in the codebase -- e.g. event_checkin.utils.email_service's
    # logging.getLogger(__name__) -- propagate into this file too instead of
    # going nowhere.
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)


def create_app():
    app = Flask(
        __name__,
        template_folder="event_checkin/views",
        static_folder="event_checkin/static",
        static_url_path="/static",
    )
    app.config.from_object(Config)

    if app.config["IS_PRODUCTION"]:
        # IIS terminates TLS and forwards to waitress over plain HTTP on
        # localhost -- restore the original scheme/host/client IP from the
        # X-Forwarded-* headers IIS's ARR reverse proxy sets, one hop deep.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    _configure_logging(app)

    db.init_app(app)
    mail.init_app(app)

    @app.after_request
    def add_no_cache_headers(response):
        # Templates and APIs are served same-origin (no separate cross-origin
        # frontend is deployed), so no CORS headers are needed here. Only
        # keep admin pages from being cached by the browser/back button.
        if request.path.startswith("/admin"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    app.register_blueprint(register_bp)
    app.register_blueprint(checkin_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(certificate_bp)
    app.register_blueprint(lucky_bp)

    with app.app_context():
        db.create_all()
        ensure_schema_upgrades()
        ensure_default_records()

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
