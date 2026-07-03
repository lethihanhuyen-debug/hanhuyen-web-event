from flask import Flask, request
from sqlalchemy import inspect, text
from werkzeug.security import generate_password_hash

from config import Config
from event_checkin.controllers.admin_controller import admin_bp
from event_checkin.controllers.certificate_controller import certificate_bp
from event_checkin.controllers.checkin_controller import checkin_bp
from event_checkin.controllers.register_controller import register_bp
from event_checkin.extensions import mail
from event_checkin.models import db
from event_checkin.models.admin import Admin
from event_checkin.models.event import Event


def ensure_schema_upgrades():
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

    event = Event.query.get(1)
    if not event:
        now = datetime.utcnow()
        event = Event(
            id=1,
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
        db.session.add(event)

    db.session.commit()


def create_app():
    app = Flask(
        __name__,
        template_folder="event_checkin/views",
        static_folder="event_checkin/static",
        static_url_path="/static",
    )
    app.config.from_object(Config)

    db.init_app(app)
    mail.init_app(app)

    @app.after_request
    def add_cors_headers(response):
        response.headers["Access-Control-Allow-Origin"] = app.config.get("FRONTEND_ORIGIN", "http://localhost:5173")
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Credentials"] = "true"
        if request.path.startswith("/admin"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    app.register_blueprint(register_bp)
    app.register_blueprint(checkin_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(certificate_bp)

    with app.app_context():
        db.create_all()
        ensure_schema_upgrades()
        ensure_default_records()

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
