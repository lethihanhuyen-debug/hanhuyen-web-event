"""Bước (c): check-in bắt buộc đăng nhập, cảnh báo quét trùng, trang staff (ẩn thông tin liên lạc), ẩn nút theo vai trò."""
import re
from datetime import timedelta

from tests.base import AppTestCase, app, db

from event_checkin.models.checkin_record import CheckinRecord
from event_checkin.models.event import Event
from event_checkin.models.registration import Registration
from event_checkin.models.user import User
from event_checkin.utils.timezone import now_vn_naive

SECRET_EMAIL = "bi-mat-006@example.com"
SECRET_PHONE = "0909006006"
SECRET_QUESTION = "cau-hoi-bi-mat-006"


class CheckinFlowTest(AppTestCase):
    """Dựng 1 sự kiện ĐANG DIỄN RA + 2 người đăng ký trong DB thử, xóa sạch khi xong."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        now = now_vn_naive()
        with app.app_context():
            event = Event(
                ten_su_kien=f"Sự kiện thử phân quyền {cls.suffix}", dia_diem="Phòng thử",
                ngay_bat_dau=now - timedelta(hours=1), ngay_ket_thuc=now + timedelta(hours=3),
                thang=now.month, nam=now.year,
                thoi_gian_mo_dang_ky=now - timedelta(days=2), thoi_gian_dong_dang_ky=now + timedelta(days=1),
                trang_thai="ongoing", created_by=cls.accounts["super_admin"][0],
            )
            db.session.add(event)
            db.session.flush()
            cls.event_id = event.id
            cls.code_a, cls.code_b, cls.code_none = f"TA{cls.suffix}".upper(), f"TB{cls.suffix}".upper(), f"TX{cls.suffix}".upper()
            for code, name in ((cls.code_a, "Nguyễn Văn Thử"), (cls.code_b, "Trần Thị Mẫu")):
                db.session.add(User(ma_cbsv=code, ho_ten=name, email=SECRET_EMAIL, so_dien_thoai=SECRET_PHONE))
                db.session.flush()
                db.session.add(Registration(ma_cbsv=code, event_id=event.id, cau_hoi=SECRET_QUESTION))
            db.session.commit()

    @classmethod
    def tearDownClass(cls):
        with app.app_context():
            CheckinRecord.query.filter_by(event_id=cls.event_id).delete()
            Registration.query.filter_by(event_id=cls.event_id).delete()
            User.query.filter(User.ma_cbsv.in_([cls.code_a, cls.code_b])).delete(synchronize_session=False)
            Event.query.filter_by(id=cls.event_id).delete()
            db.session.commit()
        super().tearDownClass()

    def scan(self, client, code):
        return client.post("/api/checkin", json={"ma_cbsv": code, "event_id": self.event_id})

    # ---- bắt buộc đăng nhập ------------------------------------------------------------------------------
    def test_checkin_requires_login(self):
        anon = self.client_for(None)
        with app.app_context():
            before = CheckinRecord.query.filter_by(event_id=self.event_id).count()
        r = self.scan(anon, self.code_a)
        self.assertEqual(r.status_code, 401)
        self.assertFalse(r.get_json()["success"])
        for url in ("/checkin", f"/checkin/{self.event_id}"):
            r = anon.get(url)
            self.assertEqual(r.status_code, 302, url)
            self.assertTrue(r.headers["Location"].startswith("/admin/login?next="), url)
        # next trỏ đúng trang check-in để đăng nhập xong quay lại đó
        self.assertEqual(anon.get(f"/checkin/{self.event_id}").headers["Location"], f"/admin/login?next=/checkin/{self.event_id}")
        with app.app_context():
            self.assertEqual(CheckinRecord.query.filter_by(event_id=self.event_id).count(), before)  # chưa đăng nhập: không ghi gì

    def test_all_roles_can_open_checkin_page(self):
        for role in ("staff", "admin", "super_admin"):
            c = self.client_for(role)
            self.assertEqual(c.get(f"/checkin/{self.event_id}").status_code, 200, role)

    # ---- ghi checked_in_by + cảnh báo quét trùng ----------------------------------------------------------
    def test_checkin_records_who_and_warns_on_duplicate(self):
        staff, admin = self.client_for("staff"), self.client_for("admin")
        first = self.scan(staff, self.code_a)
        self.assertEqual(first.status_code, 200)
        body = first.get_json()
        self.assertTrue(body["success"])
        self.assertFalse(body["already_checked_in"])

        second = self.scan(admin, self.code_a)   # người khác quét lại cùng mã
        self.assertEqual(second.status_code, 200)
        dup = second.get_json()
        self.assertTrue(dup["success"] and dup["already_checked_in"])
        self.assertEqual(dup["first_checkin_by"], self.accounts["staff"][1])
        self.assertRegex(dup["first_checkin_at"], r"^\d{2}:\d{2}$")
        self.assertIn(self.accounts["staff"][1], dup["message"])
        self.assertIn("đã check-in lúc", dup["message"])

        with app.app_context():
            rows = CheckinRecord.query.filter_by(event_id=self.event_id, patron_code=self.code_a).order_by(CheckinRecord.id).all()
            self.assertEqual(len(rows), 2)                                            # GIỮ thiết kế cũ: vẫn ghi 2 dòng
            self.assertEqual(rows[0].checked_in_by, self.accounts["staff"][0])
            self.assertEqual(rows[1].checked_in_by, self.accounts["admin"][0])
            self.assertEqual({r.cert_status for r in rows}, {"pending"})              # 'duplicate' chỉ được gán lúc gửi chứng chỉ

    def test_unregistered_and_missing_event(self):
        staff = self.client_for("staff")
        self.assertEqual(self.scan(staff, self.code_none).status_code, 404)
        self.assertEqual(staff.post("/api/checkin", json={"ma_cbsv": self.code_a}).status_code, 400)
        self.assertEqual(staff.post("/api/checkin", json={"ma_cbsv": self.code_a, "event_id": 99999999}).status_code, 404)

    # ---- trang staff: ẩn thông tin liên lạc ---------------------------------------------------------------
    def test_staff_event_pages_hide_contact_info(self):
        staff = self.client_for("staff")
        listing = staff.get("/staff/events").get_data(as_text=True)
        self.assertIn(f"/checkin/{self.event_id}", listing)
        self.assertIn(f"/staff/events/{self.event_id}", listing)
        self.scan(staff, self.code_b)
        page = staff.get(f"/staff/events/{self.event_id}")
        self.assertEqual(page.status_code, 200)
        html = page.get_data(as_text=True)
        for visible in (self.code_a, self.code_b, "Nguyễn Văn Thử", "Trần Thị Mẫu", "Đã check-in"):
            self.assertIn(visible, html)
        for hidden in (SECRET_EMAIL, SECRET_PHONE, SECRET_QUESTION):
            self.assertNotIn(hidden, html, "trang staff lộ " + hidden)
        self.assertEqual(staff.get("/staff/events/99999999").status_code, 404)

    def test_staff_cannot_use_admin_views_of_same_data(self):
        staff = self.client_for("staff")
        # Trang admin (có email/câu hỏi) và API check-in đầy đủ vẫn đóng với staff
        self.assertEqual(staff.get(f"/admin/events/{self.event_id}").headers["Location"], "/staff/events")
        self.assertEqual(staff.get(f"/api/admin/events/{self.event_id}/checkins").status_code, 403)
        # còn admin thì thấy đủ
        admin_html = self.client_for("admin").get(f"/admin/events/{self.event_id}").get_data(as_text=True)
        self.assertIn(SECRET_EMAIL, admin_html)

    # ---- ẩn nút theo vai trò --------------------------------------------------------------------------
    def test_delete_button_only_for_super_admin(self):
        admin_html = self.client_for("admin").get("/admin/events").get_data(as_text=True)
        super_html = self.client_for("super_admin").get("/admin/events").get_data(as_text=True)
        self.assertNotIn('class="btn btn--danger btn--sm js-delete-event"', admin_html)
        self.assertIn("js-edit-event", admin_html)  # admin vẫn thấy nút Sửa
        self.assertRegex(super_html, r'class="btn btn--danger btn--sm js-delete-event"')

    def test_header_shows_name_and_role(self):
        html = self.client_for("staff").get("/staff/events").get_data(as_text=True)
        self.assertIn(self.accounts["staff"][1], html)
        self.assertIn("Nhân viên check-in", html)
        self.assertTrue(re.search(r'href="/staff/events"[^>]*>Sự kiện<', html))     # menu của staff
        admin_html = self.client_for("admin").get("/admin").get_data(as_text=True)
        self.assertIn("Quản trị viên", admin_html)
        anon_html = self.client_for(None).get("/").get_data(as_text=True)
        self.assertNotIn("header-user", anon_html)


class GracePeriodTest(AppTestCase):
    """Sự kiện đã kết thúc: staff vẫn check-in đến CHECKIN_GRACE_HOURS sau giờ kết thúc; quá mốc thì chỉ xem."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.old_grace = app.config.get("CHECKIN_GRACE_HOURS")
        app.config["CHECKIN_GRACE_HOURS"] = 2          # cố định, không phụ thuộc .env
        now = now_vn_naive()
        cls.events = {}
        with app.app_context():
            # đã kết thúc 30 phút trước (còn trong thời gian cho phép) / 3 giờ trước (quá mốc)
            for key, ended_ago in (("grace", timedelta(minutes=30)), ("closed", timedelta(hours=3))):
                end = now - ended_ago
                event = Event(
                    ten_su_kien=f"Sự kiện {key} {cls.suffix}", dia_diem="Phòng thử",
                    ngay_bat_dau=end - timedelta(hours=2), ngay_ket_thuc=end,
                    thang=now.month, nam=now.year,
                    thoi_gian_mo_dang_ky=now - timedelta(days=3), thoi_gian_dong_dang_ky=now - timedelta(days=1),
                    trang_thai="ended", created_by=cls.accounts["super_admin"][0],
                )
                db.session.add(event)
                db.session.flush()
                code = f"G{key[0].upper()}{cls.suffix}".upper()
                db.session.add(User(ma_cbsv=code, ho_ten=f"Người {key}", email=f"{code.lower()}@example.com"))
                db.session.flush()
                db.session.add(Registration(ma_cbsv=code, event_id=event.id))
                cls.events[key] = (event.id, code, end)
            db.session.commit()

    @classmethod
    def tearDownClass(cls):
        with app.app_context():
            ids = [v[0] for v in cls.events.values()]
            CheckinRecord.query.filter(CheckinRecord.event_id.in_(ids)).delete(synchronize_session=False)
            Registration.query.filter(Registration.event_id.in_(ids)).delete(synchronize_session=False)
            User.query.filter(User.ma_cbsv.in_([v[1] for v in cls.events.values()])).delete(synchronize_session=False)
            Event.query.filter(Event.id.in_(ids)).delete(synchronize_session=False)
            db.session.commit()
        app.config["CHECKIN_GRACE_HOURS"] = cls.old_grace if cls.old_grace is not None else 5
        super().tearDownClass()

    def test_within_grace_staff_can_checkin_and_sees_notice(self):
        event_id, code, end = self.events["grace"]
        staff = self.client_for("staff")
        listing = staff.get("/staff/events").get_data(as_text=True)
        self.assertIn(f'href="/checkin/{event_id}"', listing)                   # nút Check-in vẫn hiện
        self.assertIn(f'href="/staff/events/{event_id}"', listing)
        page = staff.get(f"/checkin/{event_id}").get_data(as_text=True)
        self.assertIn(f"Sự kiện đã kết thúc lúc {end.strftime('%H:%M')}", page)  # dòng nhắc
        self.assertNotIn("disabled", page.split('id="checkinInput"')[1].split(">")[0])
        r = staff.post("/api/checkin", json={"ma_cbsv": code, "event_id": event_id})
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        self.assertTrue(r.get_json()["success"])

    def test_past_grace_staff_view_only(self):
        event_id, code, end = self.events["closed"]
        staff = self.client_for("staff")
        listing = staff.get("/staff/events").get_data(as_text=True)
        self.assertNotIn(f'href="/checkin/{event_id}"', listing)                # không còn nút Check-in
        self.assertIn(f'href="/staff/events/{event_id}"', listing)              # vẫn bấm "Xem danh sách" được
        detail = staff.get(f"/staff/events/{event_id}")
        self.assertEqual(detail.status_code, 200)
        self.assertNotIn(f'href="/checkin/{event_id}"', detail.get_data(as_text=True))
        self.assertIn(code, detail.get_data(as_text=True))
        with app.app_context():
            before = CheckinRecord.query.filter_by(event_id=event_id).count()
        r = staff.post("/api/checkin", json={"ma_cbsv": code, "event_id": event_id})   # server chặn theo cùng quy tắc
        self.assertEqual(r.status_code, 400)
        self.assertIn("quá thời gian cho phép check-in", r.get_json()["message"])
        page = staff.get(f"/checkin/{event_id}").get_data(as_text=True)         # vào thẳng URL: form bị khóa + giải thích
        self.assertIn("quá thời gian cho phép check-in", page)
        self.assertIn("disabled", page.split('id="checkinInput"')[1].split(">")[0])
        with app.app_context():
            self.assertEqual(CheckinRecord.query.filter_by(event_id=event_id).count(), before)  # không ghi thêm dòng nào

    def test_admin_can_still_add_manually_after_grace(self):
        event_id, code, end = self.events["closed"]
        admin = self.client_for("admin")
        r = admin.post(f"/api/admin/events/{event_id}/checkins", json={"patron_code": code})
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))

    def test_default_is_5_hours(self):
        from config import Config
        self.assertEqual(Config.CHECKIN_GRACE_HOURS, 5)   # mặc định khi .env không đặt CHECKIN_GRACE_HOURS

    def test_grace_hours_is_configurable(self):
        event_id, code, end = self.events["closed"]         # đã kết thúc 3 giờ trước
        app.config["CHECKIN_GRACE_HOURS"] = 76
        try:
            staff = self.client_for("staff")
            r = staff.post("/api/checkin", json={"ma_cbsv": code, "event_id": event_id})
            self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        finally:
            app.config["CHECKIN_GRACE_HOURS"] = 2


class TitlebarLayoutTest(AppTestCase):
    """Nút Quay lại và nhãn tiêu đề cùng một thanh (staff-titlebar) ở mọi trang staff có nút Quay lại."""

    def test_back_button_is_in_titlebar(self):
        c = self.client_for("staff")
        with app.app_context():
            event = Event.query.first()
            self.assertIsNotNone(event)
            event_id = event.id
        for url in (f"/staff/events/{event_id}", f"/checkin/{event_id}"):
            html = c.get(url).get_data(as_text=True)
            bar = re.search(r'<div class="staff-titlebar">(.*?)</div>', html, re.S)
            self.assertIsNotNone(bar, url)
            self.assertIn('class="eyebrow"', bar.group(1), url)
            self.assertIn("btn--back", bar.group(1), url)
            self.assertNotIn("checkin-back", html, url)
