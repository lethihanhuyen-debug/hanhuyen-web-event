"""Kiểm tra lúc khởi động khi DB chưa chạy đủ migration (event_checkin/schema_status.py).

Không sửa cấu trúc DB thử: giả lập "thiếu migration" bằng cách đặt tạm app.extensions["pending_migrations"]."""
from contextlib import contextmanager

from sqlalchemy.exc import OperationalError

from event_checkin import schema_status
from event_checkin.migrations import m006_phan_quyen, m007_certificate_token
from tests.base import AppTestCase, app

M007_MISSING = {"m007": ["thiếu cột certificates.token"]}
M006_MISSING = {"m006": ["thiếu cột admins.email"]}


@contextmanager
def pending(value):
    saved = app.extensions[schema_status.EXTENSION_KEY]
    app.extensions[schema_status.EXTENSION_KEY] = value
    try:
        yield
    finally:
        app.extensions[schema_status.EXTENSION_KEY] = saved


class SchemaStatusTest(AppTestCase):
    def test_test_database_is_fully_migrated(self):
        with app.app_context():
            self.assertEqual(schema_status.check_migrations(), {})
            self.assertEqual(m006_phan_quyen.schema_problems(), [])
            self.assertEqual(m007_certificate_token.schema_problems(), [])
        self.assertEqual(app.extensions[schema_status.EXTENSION_KEY], {})

    def test_no_banner_when_migrated(self):
        client = self.client_for("super_admin")
        page = client.get("/admin").get_data(as_text=True)
        self.assertNotIn("migration-banner", page)

    def test_missing_m007_blocks_certificate_routes_with_maintenance(self):
        client = self.client_for("super_admin")
        with pending(M007_MISSING):
            for path in ("/c/abcdefghijklmnopqrstuvwxyz", "/verify/USSH-2026-EVENT001-000001",
                         "/api/certificates/USSH-2026-EVENT001-000001"):
                response = self.client_for().get(path)
                self.assertEqual(response.status_code, 503, path)
                self.assertIn("Hệ thống chứng chỉ đang bảo trì", response.get_data(as_text=True))
            response = client.get("/api/admin/certificates/USSH-2026-EVENT001-000001")
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.get_json()["code"], "maintenance")

    def test_missing_m007_keeps_register_and_admin_running_with_banner(self):
        client = self.client_for("super_admin")
        with pending(M007_MISSING):
            self.assertEqual(self.client_for().get("/").status_code, 200)
            response = client.get("/admin")
            self.assertEqual(response.status_code, 200)
            page = response.get_data(as_text=True)
            self.assertIn("migration-banner", page)
            self.assertIn("Chưa chạy migration m007, xem DEPLOYMENT.md", page)
            # trang công khai không hiện banner (chỉ trang admin/staff)
            self.assertNotIn("migration-banner", self.client_for().get("/").get_data(as_text=True))

    def test_missing_m006_blocks_account_pages_but_not_register(self):
        with pending(M006_MISSING):
            client = self.client_for()
            self.assertEqual(client.get("/").status_code, 200)
            for path in ("/admin/login", "/admin", "/checkin", "/staff/events"):
                response = client.get(path)
                self.assertEqual(response.status_code, 503, path)
                self.assertIn("đang bảo trì", response.get_data(as_text=True))
            response = client.post("/api/admin/login", json={"username": "x", "password": "y"})
            self.assertEqual(response.status_code, 503)

    def test_database_error_becomes_maintenance_only_while_migration_missing(self):
        error = OperationalError("SELECT certificates.token", {}, Exception("Unknown column 'certificates.token'"))
        with app.test_request_context("/api/admin/events/1/certificates"):
            with pending(M007_MISSING):
                response = schema_status.handle_database_error(error)
                self.assertEqual(response.status_code, 503)
                self.assertIn("bảo trì", response.get_json()["message"])
            with pending({}):
                with self.assertRaises(OperationalError):
                    schema_status.handle_database_error(error)
