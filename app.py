from flask import Flask

from config import Config
from event_checkin.controllers.admin_controller import admin_bp
from event_checkin.controllers.certificate_controller import certificate_bp
from event_checkin.controllers.checkin_controller import checkin_bp
from event_checkin.controllers.register_controller import register_bp
from event_checkin.extensions import mail
from event_checkin.models import db


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
    app.register_blueprint(register_bp)
    app.register_blueprint(checkin_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(certificate_bp)

    with app.app_context():
        db.create_all()

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
