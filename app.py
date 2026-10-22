"""Preview-only entrypoint (not committed to the repo, see README.md) --
used to run the app locally with SQLite to check UI/CSS changes without
needing MySQL or a production .env."""

from datetime import timedelta

from flask import Flask
from werkzeug.security import generate_password_hash

from config import Config
from event_checkin.extensions import mail
from event_checkin.models import db
from event_checkin.models.admin import Admin
from event_checkin.models.don_vi import DonVi
from event_checkin.models.event import Event
from event_checkin.utils.timezone import now_vn_naive

app = Flask(
    __name__,
    template_folder="event_checkin/views",
    static_folder="event_checkin/static",
)
app.config.from_object(Config)

db.init_app(app)
mail.init_app(app)

from event_checkin.controllers.admin_controller import admin_bp
from event_checkin.controllers.certificate_controller import certificate_bp
from event_checkin.controllers.checkin_controller import checkin_bp
from event_checkin.controllers.register_controller import register_bp

app.register_blueprint(register_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(checkin_bp)
app.register_blueprint(certificate_bp)

with app.app_context():
    db.create_all()

    if not Admin.query.first():
        admin = Admin(
            username=app.config["ADMIN_DEFAULT_USERNAME"],
            password_hash=generate_password_hash(app.config["ADMIN_DEFAULT_PASSWORD"]),
            role="super_admin",
            is_active=True,
        )
        db.session.add(admin)
        db.session.flush()

        if not Event.query.first():
            now = now_vn_naive()
            db.session.add(
                Event(
                    ten_su_kien="Sự kiện demo xem giao diện",
                    mo_ta="Sự kiện mẫu để xem thử giao diện đăng ký.",
                    dia_diem="Hội trường A",
                    ngay_bat_dau=now,
                    ngay_ket_thuc=now + timedelta(hours=3),
                    thang=now.month,
                    nam=now.year,
                    thoi_gian_mo_dang_ky=now - timedelta(days=1),
                    thoi_gian_dong_dang_ky=now + timedelta(days=7),
                    created_by=admin.id,
                )
            )

        if not DonVi.query.first():
            db.session.add(DonVi(ten_don_vi="Trung tâm Thông tin - Thư viện - Bảo tàng", is_active=True))

        db.session.commit()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
