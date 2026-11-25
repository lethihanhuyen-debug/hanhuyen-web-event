"""Lỗ hổng chứng chỉ: file ngoài static, link token, link cũ phải xác nhận mã CB/SV, trang xác minh tối thiểu,
giới hạn tần suất, quyền admin/staff, migration m007, ProxyFix chỉ tin IIS cùng máy."""
import re
import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from tests.base import TEST_CERT_DIR, AppTestCase, app, db

from event_checkin.certificates import mailer
from event_checkin.certificates.service import generate_certificate, get_certificate_file_path
from event_checkin.controllers import certificate_controller
from event_checkin.models.audit_log import AuditLog
from event_checkin.models.certificate import Certificate
from event_checkin.models.checkin_record import CheckinRecord
from event_checkin.models.email_log import EmailLog
from event_checkin.models.event import Event
from event_checkin.models.registration import Registration
from event_checkin.models.user import User
from event_checkin.utils.timezone import now_vn_naive

TEMPLATE = "certificates/templates/event_1_certificate.png"
EMAIL_A, EMAIL_B = "chu-chung-chi-a@example.com", "chu-chung-chi-b@example.com"
UNIT = "Đơn vị bí mật thử"


class _CertificateFixture(AppTestCase):
    """1 sự kiện có mẫu chứng chỉ + 2 người đã check-in và đã có chứng chỉ (A, B); xóa sạch khi xong."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        now = now_vn_naive()
        with app.app_context():
            event = Event(
                ten_su_kien=f"Sự kiện thử chứng chỉ {cls.suffix}", dia_diem="Phòng thử",
                ngay_bat_dau=now - timedelta(hours=1), ngay_ket_thuc=now + timedelta(hours=3),
                thang=now.month, nam=now.year,
                thoi_gian_mo_dang_ky=now - timedelta(days=2), thoi_gian_dong_dang_ky=now + timedelta(days=1),
                trang_thai="ongoing", created_by=cls.accounts["super_admin"][0],
                certificate_enabled=True, certificate_template=TEMPLATE,
            )
            db.session.add(event)
            db.session.flush()
            cls.event_id = event.id
            cls.code_a, cls.code_b = f"CA{cls.suffix}".upper(), f"CB{cls.suffix}".upper()
            for code, name, email in ((cls.code_a, "Nguyễn Văn Chứng", EMAIL_A), (cls.code_b, "Trần Thị Chỉ", EMAIL_B)):
                db.session.add(User(ma_cbsv=code, ho_ten=name, email=email, chuc_vu="Sinh viên"))
                db.session.flush()
                db.session.add(Registration(ma_cbsv=code, event_id=event.id))
                db.session.add(CheckinRecord(event_id=event.id, patron_code=code, checkin_at=now))
            db.session.commit()
            with app.test_request_context():
                cert_a, _ = generate_certificate(cls.code_a, event_id=cls.event_id)
                cert_b, _ = generate_certificate(cls.code_b, event_id=cls.event_id)
            cls.cert_a = (cert_a.id, cert_a.certificate_code, cert_a.token)
            cls.cert_b = (cert_b.id, cert_b.certificate_code, cert_b.token)

    @classmethod
    def tearDownClass(cls):
        with app.app_context():
            EmailLog.query.filter_by(event_id=cls.event_id).delete()
            Certificate.query.filter_by(event_id=cls.event_id).delete()
            CheckinRecord.query.filter_by(event_id=cls.event_id).delete()
            Registration.query.filter_by(event_id=cls.event_id).delete()
            User.query.filter(User.ma_cbsv.in_([cls.code_a, cls.code_b])).delete(synchronize_session=False)
            Event.query.filter_by(id=cls.event_id).delete()
            db.session.commit()
        super().tearDownClass()

    def setUp(self):
        certificate_controller.public_limiter.reset()
        with app.app_context():
            AuditLog.query.filter(AuditLog.action.like("certificate.legacy%")).delete(synchronize_session=False)
            db.session.commit()

    def anon(self, ip="203.0.113.50"):
        client = app.test_client()
        client.environ_base["REMOTE_ADDR"] = ip
        return client


class CertificateSecurityTest(_CertificateFixture):

    # ---- nơi lưu file ------------------------------------------------------------------------------------------
    def test_file_is_outside_static_and_static_url_is_404(self):
        _id, code, _token = self.cert_a
        with app.app_context():
            certificate = db.session.get(Certificate, _id)
            path = get_certificate_file_path(certificate)
            self.assertTrue(path.is_file())
            path.resolve().relative_to(Path(TEST_CERT_DIR).resolve())          # nằm trong thư mục lưu, ngoài static
            self.assertFalse(certificate.file_url.startswith("/static"))
            year = certificate.issued_at.year
        self.assertFalse((Path(app.static_folder) / "certificates" / "generated" / str(year) / f"{code}.pdf").exists())
        c = self.anon()
        for url in (f"/static/certificates/generated/{year}/{code}.pdf",
                    "/static/certificates/generated/2026/USSH-2026-EVENT001-000001.png"):   # file cũ còn sót cũng bị chặn
            self.assertEqual(c.get(url).status_code, 404, url)

    def test_token_is_random_unique_and_long(self):
        tokens = {self.cert_a[2], self.cert_b[2]}
        self.assertEqual(len(tokens), 2)
        for token in tokens:
            self.assertGreaterEqual(len(token), 22)
            self.assertNotIn(self.cert_a[1], token)

    # ---- link token --------------------------------------------------------------------------------------------
    def test_token_link_downloads_the_right_certificate_with_private_headers(self):
        _id, code, token = self.cert_a
        c = self.anon()
        r = c.get(f"/c/{token}")
        self.assertEqual(r.status_code, 200)
        self.assertIn("attachment", r.headers["Content-Disposition"])
        self.assertIn(code, r.headers["Content-Disposition"])
        self.assertTrue(r.data.startswith(b"%PDF"))
        self.assertEqual(r.headers["Cache-Control"], "private, no-store")
        self.assertIn("noindex", r.headers["X-Robots-Tag"])
        with app.app_context():
            self.assertEqual(r.data, get_certificate_file_path(db.session.get(Certificate, _id)).read_bytes())
        view = c.get(f"/c/{token}/view")
        self.assertEqual(view.status_code, 200)
        self.assertIn("inline", view.headers.get("Content-Disposition", "inline"))

    def test_wrong_token_and_revoked_are_same_404(self):
        c = self.anon()
        for url in ("/c/khong-co-token-nay-1234567890", "/c/khong-co-token-nay-1234567890/view",
                    "/verify/t/khong-co-token-nay-1234567890"):
            r = c.get(url)
            self.assertEqual(r.status_code, 404, url)
            self.assertEqual(r.headers["Cache-Control"], "private, no-store", url)
        _id, _code, token = self.cert_b
        with app.app_context():
            Certificate.query.filter_by(id=_id).update({"status": "revoked"})
            db.session.commit()
        try:
            missing = c.get("/c/khong-co-token-nay-1234567890")
            revoked = c.get(f"/c/{token}")
            self.assertEqual((revoked.status_code, revoked.data), (missing.status_code, missing.data))
            page = c.get(f"/verify/t/{token}").get_data(as_text=True)
            self.assertIn("Đã thu hồi", page)
            self.assertNotIn(f"/c/{token}", page)                                   # không còn nút tải
        finally:
            with app.app_context():
                Certificate.query.filter_by(id=_id).update({"status": "generated"})
                db.session.commit()

    def test_changing_last_digits_of_code_never_shows_another_certificate(self):
        _id_a, code_a, _ = self.cert_a
        _id_b, code_b, _ = self.cert_b
        c = self.anon()
        for url in (f"/api/certificates/{code_b}", f"/api/certificates/{code_b}/view"):
            r = c.get(url)                                    # chỉ là trang nhập mã CB/SV, không có file
            self.assertEqual(r.status_code, 200, url)
            self.assertNotIn("application/pdf", r.headers["Content-Type"], url)
            self.assertIn("Xác nhận để tải chứng chỉ", r.get_data(as_text=True), url)
            self.assertNotIn("Trần Thị Chỉ", r.get_data(as_text=True), url)
        # Trang nhập mã giống hệt nhau dù mã có tồn tại hay không (không lộ mã nào có thật)
        fake = code_a[:-6] + "999999"
        self.assertEqual(c.get(f"/api/certificates/{fake}").get_data(as_text=True).replace(fake, "X"),
                         c.get(f"/api/certificates/{code_b}").get_data(as_text=True).replace(code_b, "X"))
        # Biết mã chứng chỉ của B + nhập mã CB/SV của A -> không khớp
        r = c.post(f"/api/certificates/{code_b}", data={"ma_cbsv": self.code_a})
        self.assertEqual(r.status_code, 400)
        self.assertIn("Thông tin không khớp", r.get_data(as_text=True))

    # ---- link cũ ----------------------------------------------------------------------------------------------
    def test_legacy_link_with_right_code_redirects_to_token_and_downloads(self):
        _id, code, token = self.cert_a
        c = self.anon()
        r = c.post(f"/api/certificates/{code}", data={"ma_cbsv": f"  {self.code_a.lower()} "})   # hoa/thường, khoảng trắng
        self.assertEqual(r.status_code, 303)
        self.assertTrue(r.headers["Location"].endswith(f"/c/{token}"))
        downloaded = c.get(r.headers["Location"])
        self.assertEqual(downloaded.status_code, 200)
        self.assertTrue(downloaded.data.startswith(b"%PDF"))
        view = c.post(f"/api/certificates/{code}/view", data={"ma_cbsv": self.code_a})
        self.assertTrue(view.headers["Location"].endswith(f"/c/{token}/view"))
        with app.app_context():
            self.assertEqual(AuditLog.query.filter_by(action="certificate.legacy_success", target_id=code).count(), 2)

    def test_legacy_link_with_other_person_code_is_mismatch_and_logged(self):
        _id, code, _token = self.cert_a
        r = self.anon().post(f"/api/certificates/{code}", data={"ma_cbsv": self.code_b})
        self.assertEqual(r.status_code, 400)
        self.assertIn("Thông tin không khớp", r.get_data(as_text=True))
        with app.app_context():
            row = AuditLog.query.filter_by(action="certificate.legacy_failed", target_id=code).one()
            self.assertEqual(row.ip, "203.0.113.50")

    def test_six_wrong_attempts_get_429(self):
        _id, code, _token = self.cert_a
        c = self.anon("203.0.113.61")
        for attempt in range(5):
            self.assertEqual(c.post(f"/api/certificates/{code}", data={"ma_cbsv": "SAI"}).status_code, 400, attempt)
        r = c.post(f"/api/certificates/{code}", data={"ma_cbsv": self.code_a})     # lần 6, kể cả nhập đúng
        self.assertEqual(r.status_code, 429)
        self.assertIn("Thử lại sau 15 phút", r.get_data(as_text=True))
        # Chặn theo mã chứng chỉ: đổi IP vẫn bị chặn
        self.assertEqual(self.anon("203.0.113.62").post(f"/api/certificates/{code}", data={"ma_cbsv": "SAI"}).status_code, 429)
        with app.app_context():
            self.assertGreaterEqual(AuditLog.query.filter_by(action="certificate.legacy_throttled", target_id=code).count(), 2)
            # quá 15 phút thì được thử lại
            AuditLog.query.filter_by(action="certificate.legacy_failed").update({"created_at": datetime.utcnow() - timedelta(minutes=16)})
            db.session.commit()
        self.assertEqual(c.post(f"/api/certificates/{code}", data={"ma_cbsv": self.code_a}).status_code, 303)

    def test_wrong_attempts_are_also_limited_per_ip(self):
        c = self.anon("203.0.113.70")
        for attempt in range(5):
            c.post(f"/api/certificates/KHONG-CO-{attempt}", data={"ma_cbsv": "SAI"})
        r = c.post(f"/api/certificates/{self.cert_b[1]}", data={"ma_cbsv": self.code_b})
        self.assertEqual(r.status_code, 429)

    # ---- trang xác minh ---------------------------------------------------------------------------------------
    def test_verify_pages_show_only_minimal_info(self):
        _id, code, token = self.cert_a
        c = self.anon()
        for url in (f"/verify/{code}", f"/verify/t/{token}"):
            r = c.get(url)
            self.assertEqual(r.status_code, 200, url)
            page = r.get_data(as_text=True)
            self.assertIn("Nguyễn Văn Chứng", page, url)
            self.assertIn(f"Sự kiện thử chứng chỉ {self.suffix}", page, url)
            self.assertIn("Hợp lệ", page, url)
            for secret in (EMAIL_A, self.code_a, UNIT, "Mã CB/SV"):
                self.assertNotIn(secret, page, f"{url}: {secret}")
            self.assertIn('name="robots" content="noindex', page, url)
            self.assertIn("noindex", r.headers["X-Robots-Tag"], url)
        legacy = c.get(f"/verify/{code}").get_data(as_text=True)
        self.assertNotIn(f"/c/{token}", legacy)                       # trang theo mã cũ không lộ token / file
        self.assertIn(f"/api/certificates/{code}", legacy)            # nút tải dẫn sang trang nhập mã CB/SV
        self.assertIn(f"/c/{token}", c.get(f"/verify/t/{token}").get_data(as_text=True))
        self.assertEqual(c.get("/verify/USSH-2026-EVENT999-000001").status_code, 404)

    # ---- giới hạn tần suất -------------------------------------------------------------------------------------
    def test_public_rate_limit_per_ip_from_config(self):
        token = self.cert_a[2]
        with mock.patch.dict(app.config, {"CERT_PUBLIC_RATE_LIMIT": 3}):
            c = self.anon("203.0.113.80")
            self.assertEqual([c.get(f"/verify/t/{token}").status_code for _ in range(4)], [200, 200, 200, 429])
            self.assertEqual(c.get(f"/c/{token}").status_code, 429)
            self.assertEqual(self.anon("203.0.113.81").get(f"/verify/t/{token}").status_code, 200)   # IP khác không bị
        self.assertEqual(app.config["CERT_PUBLIC_RATE_LIMIT"], 120)

    # ---- admin / staff -----------------------------------------------------------------------------------------
    def test_admin_routes_work_and_staff_gets_403(self):
        code = self.cert_a[1]
        for role in ("admin", "super_admin"):
            c = self.client_for(role)
            for url in (f"/api/admin/certificates/{code}", f"/api/admin/certificates/{code}/view",
                        f"/api/admin/events/{self.event_id}/certificates/storage"):
                self.assertEqual(c.get(url).status_code, 200, f"{role} {url}")
            archive = c.get(f"/api/admin/events/{self.event_id}/certificates/archive")
            self.assertEqual(archive.status_code, 200, role)
            self.assertEqual(archive.mimetype, "application/zip")
            self.assertEqual(c.get(f"/api/admin/events/{self.event_id}/certificates/storage").get_json()["count"], 2)
        staff = self.client_for("staff")
        for method, url in (("get", f"/api/admin/certificates/{code}"), ("get", f"/api/admin/certificates/{code}/view"),
                            ("get", f"/api/admin/events/{self.event_id}/certificates/archive"),
                            ("get", f"/api/admin/events/{self.event_id}/certificates/storage"),
                            ("post", f"/api/admin/events/{self.event_id}/send-certificates")):
            self.assertEqual(getattr(staff, method)(url).status_code, 403, url)
        self.assertEqual(self.anon().get(f"/api/admin/certificates/{code}").status_code, 401)

    def test_batch_send_email_contains_token_links_and_file_in_new_dir(self):
        sent = []

        def fake_send(ho_ten, email, thoi_gian, **kwargs):
            sent.append({"email": email, **kwargs})
            return (True, None) if kwargs.get("return_error") else True

        with mock.patch.object(mailer, "send_checkin_email", fake_send), app.app_context():
            with app.test_request_context(base_url="https://su-kien.example.edu.vn"):
                entry = mailer._send_one(self.event_id, self.code_a, "Sự kiện thử")
        self.assertTrue(entry["ok"], entry)
        mail = sent[0]
        token = self.cert_a[2]
        self.assertEqual(mail["download_url"], f"https://su-kien.example.edu.vn/c/{token}")
        self.assertEqual(mail["verify_url"], f"https://su-kien.example.edu.vn/verify/t/{token}")
        Path(mail["certificate_path"]).resolve().relative_to(Path(TEST_CERT_DIR).resolve())
        self.assertNotIn("/static/", mail["download_url"] + mail["verify_url"])
        self.assertNotIn(self.cert_a[1], mail["download_url"] + mail["verify_url"])

    def test_email_body_has_token_links(self):
        from event_checkin.utils import email_service

        captured = {}
        with app.app_context(), mock.patch.dict(app.config, {"MAIL_USERNAME": "x@example.com", "MAIL_PASSWORD": "y"}), \
                mock.patch.object(email_service.mail, "send", lambda message: captured.update(body=message.body, html=message.html)):
            ok = email_service.send_checkin_email("A", "a@example.com", datetime(2026, 11, 20, 9, 0), certificate_code="USSH-X",
                                                  verify_url="https://h/verify/t/TOKEN", download_url="https://h/c/TOKEN")
        self.assertTrue(ok)
        self.assertIn("https://h/c/TOKEN", captured["body"])
        self.assertIn('href="https://h/c/TOKEN"', captured["html"])
        self.assertIn("https://h/verify/t/TOKEN", captured["body"])


class CertificateCodeSequenceTest(_CertificateFixture):
    """Mã chứng chỉ không bao giờ bị cấp lại sau khi xóa chứng chỉ (kể cả chứng chỉ có số lớn nhất)."""

    def _issue(self, code):
        with app.app_context():
            if not User.query.get(code):
                db.session.add(User(ma_cbsv=code, ho_ten=f"Người {code}"))
                db.session.flush()
                db.session.add(Registration(ma_cbsv=code, event_id=self.event_id))
            db.session.add(CheckinRecord(event_id=self.event_id, patron_code=code, checkin_at=now_vn_naive()))
            db.session.commit()
            with app.test_request_context():
                certificate, created = generate_certificate(code, event_id=self.event_id)
            self.assertTrue(created)
            return certificate.certificate_code

    def test_deleted_codes_are_never_reused(self):
        code_c = f"CC{self.suffix}".upper()
        self.addCleanup(self._cleanup_person, code_c)
        first = self._issue(code_c)
        admin = self.client_for("admin")
        r = admin.delete(f"/api/admin/events/{self.event_id}/checkins/{code_c}")      # xóa check-in -> xóa luôn chứng chỉ
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        second = self._issue(code_c)
        self.assertNotEqual(first, second)
        self.assertGreater(int(second.rsplit("-", 1)[1]), int(first.rsplit("-", 1)[1]))
        with app.app_context():
            codes = [c for (c,) in db.session.query(Certificate.certificate_code).filter_by(event_id=self.event_id)]
        self.assertEqual(len(codes), len(set(codes)))
        self.assertNotIn(first, codes)

    def _cleanup_person(self, code):
        with app.app_context():
            Certificate.query.filter_by(event_id=self.event_id, ma_cbsv=code).delete()
            CheckinRecord.query.filter_by(event_id=self.event_id, patron_code=code).delete()
            Registration.query.filter_by(event_id=self.event_id, ma_cbsv=code).delete()
            User.query.filter_by(ma_cbsv=code).delete()
            db.session.commit()


class MigrationTest(AppTestCase):
    """m007 trên thư mục tạm: chép file, đổi đường dẫn, sinh token, --check, chạy lại an toàn, --remove-old."""

    def test_migration_moves_files_and_is_idempotent(self):
        from event_checkin.migrations import m007_certificate_token as m007

        work = Path(tempfile.mkdtemp(prefix="m007_"))
        self.addCleanup(shutil.rmtree, work, True)
        legacy, storage = work / "legacy", work / "storage"
        (legacy / "2026").mkdir(parents=True)
        now = now_vn_naive()
        with app.app_context():
            event = Event(ten_su_kien="m007", ngay_bat_dau=now, ngay_ket_thuc=now, thang=now.month, nam=now.year,
                          thoi_gian_mo_dang_ky=now, thoi_gian_dong_dang_ky=now, created_by=self.accounts["super_admin"][0])
            db.session.add(event)
            db.session.flush()
            code = f"M7{self.suffix}".upper()
            db.session.add(User(ma_cbsv=code, ho_ten="M7"))
            db.session.flush()
            cert_code = f"USSH-2026-EVENT{event.id:03d}-M7{self.suffix}"
            (legacy / "2026" / f"{cert_code}.pdf").write_bytes(b"%PDF-1.4 thu" * 100)
            (legacy / "2026" / "mo-coi.png").write_bytes(b"x")
            db.session.add(Certificate(ma_cbsv=code, event_id=event.id, certificate_code=cert_code, token=None,
                                       file_url=f"/static/certificates/generated/2026/{cert_code}.pdf", file_type="pdf"))
            db.session.commit()
            event_id = event.id

        def cleanup():
            with app.app_context():
                Certificate.query.filter_by(event_id=event_id).delete()
                User.query.filter_by(ma_cbsv=code).delete()
                Event.query.filter_by(id=event_id).delete()
                db.session.commit()
        self.addCleanup(cleanup)

        with mock.patch.object(m007, "legacy_root", lambda: legacy), mock.patch.object(m007, "storage_root", lambda: storage), \
                app.app_context():
            self.assertTrue(any("chưa có token" in p for p in m007.problems()))
            m007.migrate(dry_run=True)                                                 # xem trước: không đổi gì
            self.assertFalse((storage / "2026" / f"{cert_code}.pdf").exists())
            m007.migrate()
            target = storage / "2026" / f"{cert_code}.pdf"
            self.assertEqual(target.read_bytes(), (legacy / "2026" / f"{cert_code}.pdf").read_bytes())
            row = Certificate.query.filter_by(certificate_code=cert_code).one()
            self.assertEqual(row.file_url, f"2026/{cert_code}.pdf")
            self.assertGreaterEqual(len(row.token), 22)
            token = row.token
            db.session.remove()
            self.assertEqual(m007.migrate(), [])                                       # chạy lại: không làm gì thêm
            self.assertEqual(Certificate.query.filter_by(certificate_code=cert_code).one().token, token)
            self.assertIn("2026/mo-coi.png", m007.orphan_files())
            # file mới bị hỏng (khác kích thước) -> --check báo, --remove-old không xóa
            target.write_bytes(b"hong")
            self.assertTrue(m007.problems())
            self.assertEqual(m007.remove_old(), 1)
            self.assertTrue((legacy / "2026" / f"{cert_code}.pdf").exists())
            m007.migrate()                                                             # file_url đã mới -> không chép lại
            shutil.copy2(legacy / "2026" / f"{cert_code}.pdf", target)
            self.assertFalse([p for p in m007.problems() if "chưa có token" not in p and "static" not in p])
            self.assertEqual(m007.remove_old(), 0)
            self.assertFalse(any(legacy.rglob("*.pdf")))
            self.assertTrue(target.is_file())


class ProxyIpTest(AppTestCase):
    """IP thật sau IIS: chỉ tin X-Forwarded-For khi kết nối đến từ chính máy này; bỏ cổng ARR gắn kèm."""

    def test_trusted_local_proxy_fix(self):
        from flask import Flask

        from app import TrustedLocalProxyFix
        from event_checkin.audit import client_ip

        probe = Flask(__name__)
        probe.add_url_rule("/ip", "ip", lambda: client_ip() or "-")
        probe.wsgi_app = TrustedLocalProxyFix(probe.wsgi_app)
        c = probe.test_client()

        def ip(remote, xff=None):
            headers = {"X-Forwarded-For": xff} if xff else {}
            return c.get("/ip", headers=headers, environ_base={"REMOTE_ADDR": remote}).get_data(as_text=True)

        self.assertEqual(ip("127.0.0.1", "198.51.100.7"), "198.51.100.7")          # IIS cùng máy -> IP thật
        self.assertEqual(ip("127.0.0.1", "198.51.100.7:51234"), "198.51.100.7")    # ARR gắn cổng -> bỏ cổng
        self.assertEqual(ip("127.0.0.1", "1.1.1.1, 198.51.100.7"), "198.51.100.7")  # người dùng tự gửi XFF giả -> lấy hop cuối (IIS ghi)
        self.assertEqual(ip("::1", "[2001:db8::5]:4000"), "2001:db8::5")
        self.assertEqual(ip("10.0.0.9", "198.51.100.7"), "10.0.0.9")                # không qua IIS cùng máy -> không tin XFF
        self.assertEqual(ip("127.0.0.1"), "127.0.0.1")

    def test_ip_normalizer(self):
        from event_checkin.audit import normalize_ip

        self.assertEqual(normalize_ip("203.0.113.9:443"), "203.0.113.9")
        self.assertEqual(normalize_ip("2001:db8::1"), "2001:db8::1")
        self.assertEqual(normalize_ip("[2001:db8::1]:8080"), "2001:db8::1")
        self.assertIsNone(normalize_ip(""))
