import pathlib
import unittest
from collections import Counter

from flask import Flask

from tests.base import AppTestCase, app, db  # import này cũng kiểm tra tên DB trước tiên

from config import Config
from event_checkin import permissions as perm
from event_checkin.access import access, init_access
from event_checkin.controllers.admin_controller import admin_bp
from event_checkin.models.event import Event
from event_checkin.models.registration import Registration
from event_checkin.models.user import User

# Các endpoint được phép CÔNG KHAI -- danh sách tường minh: thêm route công khai mới mà quên cập nhật chỗ này thì test đỏ.
EXPECTED_PUBLIC = {
    "register.index", "register.event_register", "register.events_month_groups", "register.search_events",
    "register.public_events", "register.public_don_vi", "register.register",
    "certificates.download", "certificates.view_certificate", "certificates.verify",
    "admin.login_page", "admin.me", "admin.login", "admin.logout",
    "password.forgot_page", "password.forgot_api", "password.reset_page", "password.reset_api",
}
# Mọi tài khoản đã đăng nhập (kể cả đang bị bắt đổi mật khẩu tạm)
EXPECTED_AUTHENTICATED = {"password.change_page", "password.change_api"}


class UrlMapTest(unittest.TestCase):
    """Quét toàn bộ app.url_map: không route nào được thiếu khai báo quyền."""

    def rules(self):
        return [r for r in app.url_map.iter_rules() if r.endpoint != "static"]

    def test_every_route_declares_access(self):
        undeclared = [f"{r.rule} ({r.endpoint})" for r in self.rules()
                      if getattr(app.view_functions[r.endpoint], "required_access", None) is None]
        self.assertEqual(undeclared, [], "Route chưa khai báo @access: " + ", ".join(undeclared))

    def test_declared_values_are_valid(self):
        valid = {perm.PUBLIC, perm.AUTHENTICATED} | set(perm.ALL_PERMISSIONS)
        for r in self.rules():
            self.assertIn(app.view_functions[r.endpoint].required_access, valid, r.rule)

    def test_public_set_is_exactly_expected(self):
        public = {r.endpoint for r in self.rules() if app.view_functions[r.endpoint].required_access == perm.PUBLIC}
        self.assertEqual(public, EXPECTED_PUBLIC)

    def test_authenticated_set_is_exactly_expected(self):
        authed = {r.endpoint for r in self.rules() if app.view_functions[r.endpoint].required_access == perm.AUTHENTICATED}
        self.assertEqual(authed, EXPECTED_AUTHENTICATED)

    def test_super_admin_only_routes(self):
        """Quản lý tài khoản / nhật ký / xóa sự kiện / reset chỉ khai báo cho quyền của super_admin."""
        only_super = perm.ROLE_PERMISSIONS[perm.ROLE_SUPER_ADMIN] - perm.ROLE_PERMISSIONS[perm.ROLE_ADMIN]
        for r in self.rules():
            if r.endpoint.startswith("account.") and r.endpoint not in ():
                self.assertIn(app.view_functions[r.endpoint].required_access, only_super, r.rule)

    def test_old_decorator_is_gone(self):
        text = "".join(p.read_text(encoding="utf-8") for p in pathlib.Path("event_checkin/controllers").glob("*.py"))
        self.assertNotIn("@admin_required", text)

    def test_print_summary(self):
        counts = Counter(app.view_functions[r.endpoint].required_access for r in self.rules())
        print("\nTổng route (trừ /static):", sum(counts.values()))
        for key, number in sorted(counts.items()):
            print(f"  {key:24s} {number}")


class AnonymousTest(AppTestCase):
    def setUp(self):
        self.client = self.client_for(None)

    def test_public_pages_work_without_login(self):
        with app.app_context():
            event = Event.query.first()
            event_id = event.id if event else 1
        for url in ("/", f"/events/{event_id}/register", "/api/events", "/api/events/search",
                    "/api/events/month-groups", "/api/don-vi", "/admin/login"):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_certificate_verify_is_public_not_401(self):
        self.assertEqual(self.client.get("/verify/KHONG-CO").status_code, 404)

    def test_register_api_reachable_and_validates(self):
        response = self.client.post("/api/register", json={})
        self.assertEqual(response.status_code, 400)  # lỗi dữ liệu, KHÔNG phải 401/403

    def test_register_end_to_end_without_login(self):
        with app.app_context():
            event = next((e for e in Event.query.all() if e.is_registration_open), None)
            if event is None:
                self.skipTest("DB thử không có sự kiện đang mở đăng ký")
            event_id = event.id
            code = "T006" + self.suffix.upper()
            payload = {"ma_cbsv": code, "ho_ten": "Nguoi Test", "email": f"{code.lower()}@example.com", "event_id": event_id}
            existed = User.query.filter_by(ma_cbsv=code).first() is not None
        try:
            response = self.client.post("/api/register", json=payload)
            self.assertIn(response.status_code, (200, 201), response.get_data(as_text=True))
        finally:
            with app.app_context():
                Registration.query.filter_by(ma_cbsv=code, event_id=event_id).delete()
                if not existed:
                    User.query.filter_by(ma_cbsv=code).delete()
                db.session.commit()

    def test_protected_pages_redirect_to_login_with_next(self):
        for url in ("/admin", "/admin/events", "/admin/lucky-draw", "/staff/events"):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302, url)
            self.assertTrue(response.headers["Location"].startswith("/admin/login?next="), url)

    def test_protected_apis_return_401_json(self):
        for method, url in (("get", "/api/admin/events"), ("get", "/api/admin/me"), ("get", "/api/lookup/ABC"),
                            ("post", "/admin/reset"), ("delete", "/api/admin/events/999999"),
                            ("get", "/api/admin/events/1/checkins/export")):
            response = getattr(self.client, method)(url)
            self.assertEqual(response.status_code, 401, url)
            self.assertFalse(response.get_json()["success"])

    def test_unknown_route_is_plain_404(self):
        self.assertEqual(self.client.get("/khong-co-trang-nay").status_code, 404)


class RoleTest(AppTestCase):
    def test_staff(self):
        c = self.client_for("staff")
        self.assertEqual(c.get("/staff/events").status_code, 200)
        for url in ("/admin", "/admin/events", "/admin/events/1", "/admin/export/csv", "/admin/lucky-draw", "/admin/don-vi"):
            r = c.get(url)
            self.assertEqual((r.status_code, r.headers["Location"]), (302, "/staff/events"), url)
        page = c.get("/admin", follow_redirects=True).get_data(as_text=True)
        self.assertIn("không có quyền truy cập", page)
        self.assertNotIn("không có quyền truy cập", c.get("/staff/events").get_data(as_text=True))  # chỉ hiện 1 lần
        for method, url in (("get", "/api/admin/events"), ("get", "/api/admin/events/1/checkins"),
                            ("get", "/api/admin/events/1/checkins/export"), ("get", "/api/admin/events/1/export-registrations"),
                            ("post", "/api/admin/events"), ("put", "/api/admin/events/999999"),
                            ("delete", "/api/admin/events/999999"), ("post", "/admin/reset"),
                            ("post", "/api/admin/events/1/send-certificates"), ("get", "/api/admin/don-vi"),
                            ("get", "/api/admin/lucky-draw/1"), ("post", "/api/certificates/generate")):
            r = getattr(c, method)(url)
            self.assertEqual(r.status_code, 403, url)
            self.assertTrue(r.get_json()["message"].startswith("Bạn không có quyền"), url)
        # Câu báo cụ thể theo thao tác (giao diện hiện nguyên văn)
        self.assertIn("xóa sự kiện", c.delete("/api/admin/events/999999").get_json()["message"])
        self.assertIn("xuất dữ liệu", c.get("/api/admin/events/1/checkins/export").get_json()["message"])
        self.assertEqual(c.get("/api/lookup/KHONG-CO").status_code, 404)  # được phép (staff), chỉ là không có mã
        self.assertEqual(c.get("/api/admin/me").status_code, 200)

    def test_admin(self):
        c = self.client_for("admin")
        for url in ("/admin", "/admin/events", "/admin/don-vi", "/admin/lucky-draw", "/api/admin/events",
                    "/api/admin/summary", "/api/admin/don-vi", "/admin/export/csv"):
            self.assertEqual(c.get(url).status_code, 200, url)
        for method, url in (("delete", "/api/admin/events/999999"), ("post", "/admin/reset")):
            self.assertEqual(getattr(c, method)(url).status_code, 403, url)
        self.assertEqual(c.get("/staff/events").status_code, 200)

    def test_super_admin(self):
        c = self.client_for("super_admin")
        for url in ("/admin", "/admin/events", "/api/admin/events", "/staff/events"):
            self.assertEqual(c.get(url).status_code, 200, url)
        self.assertEqual(c.delete("/api/admin/events/999999").status_code, 404)   # qua cổng quyền; sự kiện không tồn tại
        self.assertEqual(c.post("/admin/reset", json={}).status_code, 400)        # qua cổng quyền; chưa xác nhận nên KHÔNG xóa gì

    def test_login_response_and_redirects_by_role(self):
        for role, home in (("staff", "/staff/events"), ("admin", "/admin"), ("super_admin", "/admin")):
            client = app.test_client()
            data = client.post("/api/admin/login", json={"username": self.accounts[role][1], "password": "Test1234x"}).get_json()
            self.assertEqual(data["home_path"], home)
            self.assertEqual(data["admin"]["role"], role)
            self.assertEqual(client.get("/admin/login").headers["Location"], home)
        c = self.client_for("admin")
        for evil in ("//evil.example", "/\\evil.example", "https://evil.example"):
            self.assertEqual(c.get("/admin/login", query_string={"next": evil}).headers["Location"], "/admin", evil)
        self.assertEqual(c.get("/admin/login", query_string={"next": "/admin/events"}).headers["Location"], "/admin/events")


class RevocationTest(AppTestCase):
    """Khóa / đổi quyền / đổi phiên có hiệu lực NGAY ở request kế tiếp."""

    def test_deactivate(self):
        c = self.client_for("admin")
        self.assertEqual(c.get("/api/admin/events").status_code, 200)
        self.set_admin("admin", is_active=False)
        try:
            self.assertEqual(c.get("/api/admin/events").status_code, 401)
        finally:
            self.set_admin("admin", is_active=True)
        self.assertEqual(c.get("/api/admin/events").status_code, 401)  # phiên đã bị dọn, phải đăng nhập lại

    def test_role_change_applies_immediately(self):
        c = self.client_for("admin")
        self.assertEqual(c.get("/api/admin/events").status_code, 200)
        self.set_admin("admin", role="staff")
        try:
            self.assertEqual(c.get("/api/admin/events").status_code, 403)
            self.assertEqual(c.get("/staff/events").status_code, 200)
        finally:
            self.set_admin("admin", role="admin")

    def test_invalid_role_is_logged_out(self):
        c = self.client_for("staff")
        self.set_admin("staff", role="gi-do-la")
        try:
            self.assertEqual(c.get("/api/admin/events").status_code, 401)
        finally:
            self.set_admin("staff", role="staff")

    def test_session_version_bump_logs_out_old_sessions(self):
        old, other = self.client_for("admin"), self.client_for("admin")
        self.set_admin("admin", session_version=5)
        self.assertEqual(old.get("/api/admin/events").status_code, 401)
        self.assertEqual(other.get("/api/admin/events").status_code, 401)
        self.assertEqual(self.client_for("admin").get("/api/admin/events").status_code, 200)  # đăng nhập mới dùng số mới

    def test_session_without_sv_is_rejected(self):
        c = app.test_client()
        with c.session_transaction() as s:
            s["admin_id"] = self.accounts["admin"][0]
        self.assertEqual(c.get("/api/admin/events").status_code, 401)


class DefaultDenyTest(AppTestCase):
    """Route KHÔNG khai báo quyền phải bị từ chối kể cả super_admin -- thử trên app phụ có 2 route thiếu khai báo."""

    def setUp(self):
        sub = Flask(__name__)
        sub.config.from_object(Config)
        db.init_app(sub)
        sub.register_blueprint(admin_bp)  # để url_for('admin.login_page') hoạt động
        init_access(sub)

        @sub.get("/x-page")
        def undeclared_page():
            return "lọt"

        @sub.get("/api/x-api")
        def undeclared_api():
            return "lọt"

        @sub.get("/x-public")
        @access(perm.PUBLIC)
        def declared_public():
            return "ok"

        self.sub = sub

    def test_anonymous(self):
        c = self.sub.test_client()
        r = c.get("/x-page")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers["Location"].startswith("/admin/login?next="))
        self.assertEqual(c.get("/api/x-api").status_code, 401)
        self.assertEqual(c.get("/x-public").status_code, 200)

    def test_even_super_admin_is_denied(self):
        c = self.sub.test_client()
        with c.session_transaction() as s:
            s["admin_id"] = self.accounts["super_admin"][0]
            s["sv"] = 0
        r = c.get("/x-page")
        self.assertEqual((r.status_code, r.headers["Location"]), (302, "/admin"))
        self.assertEqual(c.get("/api/x-api").status_code, 403)

    def test_typo_in_permission_name_fails_at_import(self):
        with self.assertRaises(ValueError):
            access("event.deleet")


if __name__ == "__main__":
    unittest.main()
