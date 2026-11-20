"""Bước (d): quên mật khẩu qua email, link đặt lại (hết hạn / dùng 1 lần / băm token), giới hạn số lần yêu cầu."""
import re
from datetime import datetime, timedelta
from unittest import mock

from werkzeug.security import generate_password_hash

from tests.base import AppTestCase, TEST_PASSWORD, app, db

from event_checkin import security
from event_checkin.controllers import password_controller
from event_checkin.models.audit_log import AuditLog
from event_checkin.models.password_reset import PasswordReset

SENT = password_controller.FORGOT_SENT_MESSAGE
UNKNOWN = "Email này chưa đăng ký tài khoản."


class PasswordResetTest(AppTestCase):
    def setUp(self):
        self.sent = []                       # các thư "đã gửi": (to, subject, text)
        sync = lambda function, *args: function(*args)  # noqa: E731  gửi đồng bộ để test thấy ngay
        send = lambda to, subject, text, html=None: (self.sent.append((to, subject, text)) or (True, None))  # noqa: E731
        patches = [
            mock.patch.object(password_controller, "_run_async", sync),
            mock.patch.object(password_controller, "send_system_email", send),
        ]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.email = f"staff_{self.suffix}@example.com"
        # Mỗi test bắt đầu từ trạng thái sạch: mật khẩu thử gốc, chưa có link nào, bộ đếm giới hạn rỗng
        self.set_admin("staff", email=self.email, password_hash=generate_password_hash(TEST_PASSWORD), is_active=True)
        with app.app_context():
            PasswordReset.query.filter_by(admin_id=self.accounts["staff"][0]).delete()
            AuditLog.query.filter(AuditLog.action.in_(["password.forgot_request", "password.forgot_throttled", "password.reset_done"])).delete(synchronize_session=False)
            db.session.commit()

    def forgot(self, email, ip="203.0.113.7", client=None):
        client = client or app.test_client()
        return client.post("/api/admin/forgot-password", json={"email": email}, environ_overrides={"REMOTE_ADDR": ip})

    def last_token(self):
        text = self.sent[-1][2]
        match = re.search(r"/admin/reset-password/([\w-]+)", text)
        self.assertIsNotNone(match, text)
        return match.group(1)

    # ---- yêu cầu quên mật khẩu -----------------------------------------------------------------------------
    def test_existing_email_gets_link_and_unknown_email_is_reported(self):
        known = self.forgot(self.email)
        unknown = self.forgot(f"khong-co-{self.suffix}@example.com", ip="203.0.113.8")
        self.assertEqual((known.status_code, known.get_json()), (200, {"success": True, "message": SENT}))
        self.assertEqual((unknown.status_code, unknown.get_json()), (404, {"success": False, "message": UNKNOWN}))
        self.assertEqual(len(self.sent), 1)                                   # chỉ email có thật mới được gửi thư
        self.assertEqual(self.sent[0][0], self.email)
        self.assertIn("30 phút", self.sent[0][2])
        self.assertTrue(re.search(r"http://[^/\s]+/admin/reset-password/[\w-]{20,}", self.sent[0][2]))

    def test_email_matching_is_case_insensitive_and_validated(self):
        self.assertEqual(self.forgot(self.email.upper()).status_code, 200)
        self.assertEqual(len(self.sent), 1)
        for bad in ("", "khong-phai-email", "   "):
            self.assertEqual(self.forgot(bad, ip="203.0.113.9").status_code, 400, bad)

    def test_locked_account_gets_no_link(self):
        self.set_admin("staff", is_active=False)
        try:
            r = self.forgot(self.email)
            self.assertEqual((r.status_code, r.get_json()["message"]), (403, password_controller.FORGOT_LOCKED_MESSAGE))
            self.assertEqual(self.sent, [])
            with app.app_context():
                self.assertEqual(PasswordReset.query.filter_by(admin_id=self.accounts["staff"][0]).count(), 0)
        finally:
            self.set_admin("staff", is_active=True)

    def test_rate_limit_3_per_15_minutes_per_email_and_per_ip(self):
        for i in range(3):
            self.assertEqual(self.forgot(self.email, ip=f"198.51.100.{i + 1}").status_code, 200)   # IP khác nhau, cùng email
        self.assertEqual(len(self.sent), 3)
        r = self.forgot(self.email, ip="198.51.100.77")                                      # lần 4 cùng email -> chặn
        self.assertEqual(r.status_code, 429)
        self.assertEqual(r.get_json()["success"], False)
        self.assertRegex(r.get_json()["message"], r"^Bạn đã yêu cầu quá nhiều lần\. Vui lòng đợi 1[45] phút rồi thử lại\.$")
        self.assertEqual(len(self.sent), 3)

        self.sent.clear()
        for i in range(3):                                                                    # cùng IP, email khác nhau
            self.forgot(f"x{i}_{self.suffix}@example.com", ip="198.51.100.200")
        self.forgot(self.email.replace("staff_", "other_"), ip="198.51.100.200")
        with app.app_context():
            self.assertGreaterEqual(AuditLog.query.filter_by(action="password.forgot_throttled").count(), 2)

    def test_throttle_message_counts_down_remaining_minutes(self):
        for i in range(3):
            self.forgot(self.email, ip=f"198.51.100.{120 + i}")
        with app.app_context():     # yêu cầu cũ nhất cách đây 11 phút -> còn khoảng 4 phút
            row = AuditLog.query.filter_by(action="password.forgot_request").order_by(AuditLog.id).first()
            row.created_at = datetime.utcnow() - timedelta(minutes=11)
            db.session.commit()
        r = self.forgot(self.email, ip="198.51.100.130")
        self.assertEqual(r.status_code, 429)
        self.assertIn("Vui lòng đợi 4 phút rồi thử lại.", r.get_json()["message"])

    def test_old_requests_do_not_count_after_window(self):
        for i in range(3):
            self.forgot(self.email, ip=f"198.51.100.{50 + i}")
        with app.app_context():     # đẩy các yêu cầu cũ ra ngoài cửa sổ 15 phút
            AuditLog.query.filter_by(action="password.forgot_request").update({"created_at": datetime.utcnow() - timedelta(minutes=16)})
            db.session.commit()
        self.sent.clear()
        self.assertEqual(self.forgot(self.email, ip="198.51.100.99").status_code, 200)
        self.assertEqual(len(self.sent), 1)

    # ---- link đặt lại ---------------------------------------------------------------------------------
    def test_reset_flow_single_use_and_logs_out_old_sessions(self):
        old_session = self.client_for("staff")
        self.forgot(self.email)
        token = self.last_token()

        with app.app_context():                    # chỉ lưu BĂM của token
            row = PasswordReset.query.filter_by(admin_id=self.accounts["staff"][0]).order_by(PasswordReset.id.desc()).first()
            self.assertEqual(row.token_hash, security.hash_token(token))
            self.assertNotEqual(row.token_hash, token)
            self.assertLessEqual(abs((row.expires_at - row.created_at).total_seconds() - 30 * 60), 5)

        client = app.test_client()
        page = client.get(f"/admin/reset-password/{token}")
        self.assertEqual(page.status_code, 200)
        self.assertIn('name="password"', page.get_data(as_text=True))

        def reset(password, confirm=None):
            return client.post("/api/admin/reset-password", json={"token": token, "password": password, "confirm_password": confirm or password})

        self.assertEqual(reset("ngan1").status_code, 400)                       # không đạt quy định mật khẩu
        self.assertEqual(reset("Moi12345", "Khac12345").status_code, 400)
        ok = reset("Moi12345")
        self.assertEqual(ok.status_code, 200, ok.get_data(as_text=True))

        self.assertEqual(reset("Khac12345").status_code, 400)                   # link chỉ dùng được 1 lần
        again = client.get(f"/admin/reset-password/{token}").get_data(as_text=True)
        self.assertIn("không hợp lệ hoặc đã hết hạn", again)
        self.assertNotIn('name="password"', again)
        self.assertEqual(old_session.get("/staff/events").status_code, 302)     # phiên cũ bị đăng xuất
        username = self.accounts["staff"][1]
        self.assertEqual(app.test_client().post("/api/admin/login", json={"username": username, "password": TEST_PASSWORD}).status_code, 401)
        self.assertEqual(app.test_client().post("/api/admin/login", json={"username": username, "password": "Moi12345"}).status_code, 200)
        with app.app_context():
            self.assertEqual(AuditLog.query.filter_by(action="password.reset_done", admin_id=self.accounts["staff"][0]).count(), 1)

    def test_expired_and_invalid_tokens_rejected(self):
        self.forgot(self.email)
        token = self.last_token()
        with app.app_context():
            PasswordReset.query.filter_by(token_hash=security.hash_token(token)).update({"expires_at": datetime.utcnow() - timedelta(seconds=1)})
            db.session.commit()
        client = app.test_client()
        self.assertIn("không hợp lệ hoặc đã hết hạn", client.get(f"/admin/reset-password/{token}").get_data(as_text=True))
        r = client.post("/api/admin/reset-password", json={"token": token, "password": "Moi12345", "confirm_password": "Moi12345"})
        self.assertEqual(r.status_code, 400)
        for bad in ("", "khong-co-token-nay", token[:-2] + "xx"):
            r = client.post("/api/admin/reset-password", json={"token": bad, "password": "Moi12345", "confirm_password": "Moi12345"})
            self.assertEqual(r.status_code, 400, bad)
        self.assertEqual(app.test_client().post("/api/admin/login", json={"username": self.accounts["staff"][1], "password": TEST_PASSWORD}).status_code, 200)  # mật khẩu không bị đổi

    def test_new_request_invalidates_previous_link(self):
        self.forgot(self.email, ip="203.0.113.21")
        first = self.last_token()
        self.forgot(self.email, ip="203.0.113.22")
        second = self.last_token()
        self.assertNotEqual(first, second)
        client = app.test_client()
        self.assertEqual(client.post("/api/admin/reset-password", json={"token": first, "password": "Moi12345", "confirm_password": "Moi12345"}).status_code, 400)
        self.assertEqual(client.post("/api/admin/reset-password", json={"token": second, "password": "Moi12345", "confirm_password": "Moi12345"}).status_code, 200)

    def test_account_locked_after_request_cannot_use_link(self):
        self.forgot(self.email)
        token = self.last_token()
        self.set_admin("staff", is_active=False)
        try:
            r = app.test_client().post("/api/admin/reset-password", json={"token": token, "password": "Moi12345", "confirm_password": "Moi12345"})
            self.assertEqual(r.status_code, 400)
        finally:
            self.set_admin("staff", is_active=True)

    def test_forgot_request_is_audited_without_plain_email(self):
        self.forgot(self.email)
        with app.app_context():
            rows = AuditLog.query.filter_by(action="password.forgot_request").all()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].target_id, security.hash_email_key(self.email))
            self.assertNotIn(self.email, (rows[0].detail or "") + (rows[0].target_id or "") + (rows[0].username or ""))
            self.assertEqual(rows[0].ip, "203.0.113.7")

    def test_forgot_and_reset_pages_and_login_link(self):
        c = app.test_client()
        self.assertEqual(c.get("/admin/forgot-password").status_code, 200)
        self.assertIn("/admin/forgot-password", c.get("/admin/login").get_data(as_text=True))
        self.assertIn("không hợp lệ hoặc đã hết hạn", c.get("/admin/reset-password/abc").get_data(as_text=True))


class ResetSuperAdminScriptTest(AppTestCase):
    """scripts/reset-superadmin.py: chạy thật bằng dòng lệnh trên DB thử."""

    def run_script(self, username):
        import os
        import subprocess
        import sys
        env = dict(os.environ, MYSQL_DATABASE="checkin_event_test", PYTHONIOENCODING="utf-8")
        return subprocess.run([sys.executable, "scripts/reset-superadmin.py", username],
                              capture_output=True, text=True, encoding="utf-8", env=env, timeout=60)

    def test_resets_locked_super_admin_and_forces_change(self):
        username = self.accounts["super_admin"][1]
        session = self.client_for("super_admin")
        self.set_admin("super_admin", is_active=False)
        result = self.run_script(username)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        match = re.search(r"Mật khẩu tạm \(chỉ hiện lần này\): (\S+)", result.stdout)
        self.assertIsNotNone(match, result.stdout)
        temp = match.group(1)
        self.assertIsNone(security.password_error(temp))
        self.assertIn("mở khóa", result.stdout)
        self.assertEqual(session.get("/api/admin/accounts").status_code, 401)             # phiên cũ bị đăng xuất
        self.assertEqual(app.test_client().post("/api/admin/login", json={"username": username, "password": TEST_PASSWORD}).status_code, 401)
        login = app.test_client().post("/api/admin/login", json={"username": username, "password": temp})
        self.assertEqual(login.status_code, 200)
        self.assertTrue(login.get_json()["must_change_password"])
        with app.app_context():
            logs = AuditLog.query.filter_by(action="account.reset_password", admin_id=self.accounts["super_admin"][0]).all()
            self.assertEqual(len(logs), 1)
            self.assertIn("reset-superadmin.py", logs[0].detail)

    def test_refuses_non_super_admin_and_unknown(self):
        result = self.run_script(self.accounts["staff"][1])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("không phải super_admin", result.stdout)
        self.assertNotEqual(self.run_script("khong-co-tai-khoan-nay").returncode, 0)
        self.assertEqual(app.test_client().post("/api/admin/login", json={"username": self.accounts["staff"][1], "password": TEST_PASSWORD}).status_code, 200)
