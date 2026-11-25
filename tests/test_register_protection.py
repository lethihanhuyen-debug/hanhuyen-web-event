"""Chống đăng ký ảo: giới hạn số lần đăng ký theo IP (REGISTER_RATE_LIMIT) và ô bẫy (honeypot) trong form."""
import json
from datetime import timedelta

from event_checkin.controllers import register_controller
from event_checkin.models.audit_log import AuditLog
from event_checkin.models.event import Event
from event_checkin.models.registration import Registration
from event_checkin.models.user import User
from event_checkin.utils.timezone import now_vn_naive
from tests.base import AppTestCase, app, db


class RegisterProtectionTest(AppTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        now = now_vn_naive()
        with app.app_context():
            event = Event(
                ten_su_kien=f"Sự kiện thử chống đăng ký ảo {cls.suffix}", ngay_bat_dau=now + timedelta(days=1),
                ngay_ket_thuc=now + timedelta(days=1, hours=2), thang=now.month, nam=now.year,
                thoi_gian_mo_dang_ky=now - timedelta(days=1), thoi_gian_dong_dang_ky=now + timedelta(days=1),
                created_by=cls.accounts["super_admin"][0],
            )
            db.session.add(event)
            db.session.commit()
            cls.event_id = event.id
        cls.prefix = f"RP{cls.suffix}".upper()

    @classmethod
    def tearDownClass(cls):
        with app.app_context():
            Registration.query.filter_by(event_id=cls.event_id).delete()
            User.query.filter(User.ma_cbsv.like(f"{cls.prefix}%")).delete(synchronize_session=False)
            Event.query.filter_by(id=cls.event_id).delete()
            db.session.commit()
        super().tearDownClass()

    def setUp(self):
        self.saved_limit = app.config["REGISTER_RATE_LIMIT"]
        register_controller.register_limiter.reset()

    def tearDown(self):
        app.config["REGISTER_RATE_LIMIT"] = self.saved_limit
        register_controller.register_limiter.reset()

    def payload(self, n, **extra):
        return {"ma_cbsv": f"{self.prefix}{n:03d}", "ho_ten": "Người Thử", "email": f"rp{n}@example.com", "chuc_vu": "Sinh viên",
                "event_id": self.event_id, **extra}

    def registered(self, n):
        with app.app_context():
            return Registration.query.filter_by(event_id=self.event_id, ma_cbsv=f"{self.prefix}{n:03d}").count()

    def test_default_limit_is_30(self):
        from config import Config
        self.assertEqual(Config.REGISTER_RATE_LIMIT, 30)

    def test_rate_limit_per_ip_on_both_routes(self):
        app.config["REGISTER_RATE_LIMIT"] = 3
        client = self.client_for()
        self.assertEqual(client.post("/api/register", json=self.payload(1)).status_code, 200)
        self.assertEqual(client.post("/register", json=self.payload(2)).status_code, 200)
        self.assertEqual(client.post("/api/register", json={"ma_cbsv": ""}).status_code, 400)  # lần lỗi cũng tính
        for path in ("/api/register", "/register"):
            response = client.post(path, json=self.payload(4))
            self.assertEqual(response.status_code, 429, path)
            self.assertEqual(response.get_json()["message"], "Bạn thao tác quá nhanh, vui lòng thử lại sau 1 phút")
            self.assertEqual(response.headers["Retry-After"], "60")
        self.assertEqual(self.registered(4), 0)
        # IP khác (sau ProxyFix là IP thật) không bị ảnh hưởng
        other = client.post("/api/register", json=self.payload(5), environ_base={"REMOTE_ADDR": "10.9.8.7"})
        self.assertEqual(other.status_code, 200)

    def test_honeypot_pretends_success_saves_nothing_and_logs(self):
        client = self.client_for()
        response = client.post("/api/register", json=self.payload(10, ghi_chu_noi_bo="http://spam.example"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["success"])
        self.assertIn("Đăng ký thành công", response.get_json()["message"])
        self.assertEqual(self.registered(10), 0)
        with app.app_context():
            self.assertIsNone(db.session.get(User, f"{self.prefix}010"))
            log = AuditLog.query.filter_by(action="registration.honeypot").order_by(AuditLog.id.desc()).first()
            self.assertEqual(json.loads(log.detail)["ma_cbsv"], f"{self.prefix}010")
        # ô bẫy để trống (người thật) -> đăng ký bình thường
        self.assertEqual(client.post("/api/register", json=self.payload(11, ghi_chu_noi_bo="")).status_code, 200)
        self.assertEqual(self.registered(11), 1)

    def test_form_has_css_hidden_honeypot(self):
        page = self.client_for().get(f"/events/{self.event_id}/register").get_data(as_text=True)
        field = page.split('class="hp-field"', 1)[1].split("</div>", 1)[0]
        self.assertIn('name="ghi_chu_noi_bo"', field)
        self.assertIn('tabindex="-1"', field)
        self.assertNotIn("display:none", field.replace(" ", ""))
        self.assertNotIn(" hidden", field)

    def test_ban_la_must_be_can_bo_or_sinh_vien(self):
        client = self.client_for()
        for value in (None, "", "Giảng viên"):
            data = self.payload(20)
            if value is None:
                data.pop("chuc_vu")
            else:
                data["chuc_vu"] = value
            response = client.post("/api/register", json=data)
            self.assertEqual(response.status_code, 400, value)
            self.assertIn("học viên sau đại học", response.get_json()["message"])
        self.assertEqual(self.registered(20), 0)
        self.assertEqual(client.post("/api/register", json=self.payload(21, chuc_vu="Cán bộ")).status_code, 200)
        with app.app_context():
            self.assertEqual(db.session.get(User, f"{self.prefix}021").chuc_vu, "Cán bộ")
        self.assertEqual(client.post("/api/register", json=self.payload(22, chuc_vu="Học viên sau đại học")).status_code, 200)
        with app.app_context():
            self.assertEqual(db.session.get(User, f"{self.prefix}022").chuc_vu, "Học viên sau đại học")
        page = client.get(f"/events/{self.event_id}/register").get_data(as_text=True)
        self.assertIn("<span>Đối tượng</span>", page)
        self.assertIn('<option value="Sinh viên">Sinh viên</option>', page)
        self.assertIn('<option value="Học viên sau đại học">Học viên sau đại học</option>', page)
        self.assertNotIn("Chức vụ", page)


class HeroOrderTest(AppTestCase):
    """Banner trang chủ: 3 sự kiện mới tạo nhất, tạo cùng giây thì sự kiện tạo sau (id lớn hơn) đứng trước, cố định."""

    def test_same_created_at_keeps_stable_order(self):
        from datetime import datetime

        from event_checkin.controllers.register_controller import _hero_events

        now = now_vn_naive()
        future = datetime(2099, 1, 1, 0, 0, 0)
        with app.app_context():
            ids = []
            for i in range(3):
                event = Event(ten_su_kien=f"Banner cùng giây {i} {self.suffix}", ngay_bat_dau=now, ngay_ket_thuc=now,
                              thang=now.month, nam=now.year, thoi_gian_mo_dang_ky=now, thoi_gian_dong_dang_ky=now,
                              created_by=self.accounts["super_admin"][0], created_at=future)
                db.session.add(event)
                db.session.flush()
                ids.append(event.id)
            db.session.commit()
            try:
                with app.test_request_context():
                    for _ in range(5):
                        self.assertEqual([item["id"] for item in _hero_events()], sorted(ids, reverse=True))
            finally:
                Event.query.filter(Event.id.in_(ids)).delete(synchronize_session=False)
                db.session.commit()
