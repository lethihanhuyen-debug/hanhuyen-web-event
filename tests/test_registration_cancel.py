"""Xóa (hủy mềm) / khôi phục người đăng ký (m009): quyền, nhả chỗ, đăng ký lại, chặn đăng ký lại, người đã check-in,
người đã có chứng chỉ / đã trúng thưởng, xóa hàng loạt, khôi phục, nhật ký."""
import json
from datetime import timedelta
from io import BytesIO

from openpyxl import load_workbook

from event_checkin.certificates import mailer
from event_checkin.certificates.validators import validate_certificate_eligibility
from event_checkin.models.audit_log import AuditLog
from event_checkin.models.certificate import Certificate
from event_checkin.models.checkin_record import CheckinRecord
from event_checkin.models.event import Event
from event_checkin.models.lucky_draw import LuckyConfig, LuckyPrize, LuckyWinner
from event_checkin.models.registration import Registration
from event_checkin.models.user import User
from event_checkin.utils.timezone import now_vn_naive
from tests.base import AppTestCase, app, db


class RegistrationCancelTest(AppTestCase):
    def setUp(self):
        """Mỗi test: 1 sự kiện ĐANG DIỄN RA, tối đa 4 chỗ, 4 người đăng ký (đủ chỗ):
        A chưa check-in, B đã check-in, C đã có chứng chỉ, D đã trúng thưởng (cả C và D đã check-in)."""
        now = now_vn_naive().replace(microsecond=0)
        tag = f"{self.suffix}{self._testMethodName[-6:]}".upper()
        with app.app_context():
            event = Event(
                ten_su_kien=f"Sự kiện thử xóa đăng ký {tag}", dia_diem="Phòng thử",
                ngay_bat_dau=now - timedelta(hours=1), ngay_ket_thuc=now + timedelta(hours=3),
                thang=now.month, nam=now.year, so_luong_toi_da=4,
                thoi_gian_mo_dang_ky=now - timedelta(days=1), thoi_gian_dong_dang_ky=now + timedelta(days=1),
                created_by=self.accounts["super_admin"][0],
            )
            db.session.add(event)
            db.session.flush()
            self.event_id = event.id
            self.codes = {key: f"X{key}{tag}"[:50] for key in "ABCDE"}
            for key in "ABCD":
                code = self.codes[key]
                db.session.add(User(ma_cbsv=code, ho_ten=f"Người {key}", email=f"{code.lower()}@example.com"))
                db.session.flush()
                db.session.add(Registration(ma_cbsv=code, event_id=event.id))
            for key in "BCD":
                db.session.add(CheckinRecord(event_id=event.id, patron_code=self.codes[key], checkin_at=now - timedelta(minutes=30)))
            db.session.add(Certificate(ma_cbsv=self.codes["C"], event_id=event.id, certificate_code=f"TEST-{tag}-C",
                                       token=f"tok{tag}", file_type="pdf"))
            db.session.add(LuckyConfig(event_id=event.id))
            prize = LuckyPrize(event_id=event.id, ten_giai="Giải nhất", so_luong=1)
            db.session.add(prize)
            db.session.flush()
            db.session.add(LuckyWinner(event_id=event.id, prize_id=prize.id, patron_code=self.codes["D"], trang_thai="confirmed"))
            db.session.commit()

    def tearDown(self):
        with app.app_context():
            LuckyWinner.query.filter_by(event_id=self.event_id).delete()
            LuckyPrize.query.filter_by(event_id=self.event_id).delete()
            LuckyConfig.query.filter_by(event_id=self.event_id).delete()
            Certificate.query.filter_by(event_id=self.event_id).delete()
            CheckinRecord.query.filter_by(event_id=self.event_id).delete()
            Registration.query.filter_by(event_id=self.event_id).delete()
            User.query.filter(User.ma_cbsv.in_(list(self.codes.values()))).delete(synchronize_session=False)
            Event.query.filter_by(id=self.event_id).delete()
            db.session.commit()

    # ---- tiện ích ----
    def cancel(self, keys, client=None, **extra):
        client = client or self.client_for("admin")
        return client.post(f"/api/admin/events/{self.event_id}/registrations/cancel",
                           json={"codes": [self.codes[k] for k in keys], **extra})

    def restore(self, keys, client=None):
        client = client or self.client_for("admin")
        return client.post(f"/api/admin/events/{self.event_id}/registrations/restore",
                           json={"codes": [self.codes[k] for k in keys]})

    def register(self, key, client=None):
        client = client or self.client_for(None)
        return client.post("/api/register", json={
            "ma_cbsv": self.codes[key], "ho_ten": f"Người {key}", "email": f"{self.codes[key].lower()}@example.com",
            "event_id": self.event_id,
        })

    def registration(self, key):
        with app.app_context():
            item = Registration.query.filter_by(event_id=self.event_id, ma_cbsv=self.codes[key]).first()
            return None if item is None else {"trang_thai": item.trang_thai, "ly_do": item.ly_do_huy,
                                              "chan": item.chan_dang_ky_lai, "huy_boi": item.huy_boi}

    def count(self):
        with app.app_context():
            return db.session.get(Event, self.event_id).registration_count

    def export_codes(self):
        response = self.client_for("admin").get(f"/api/admin/events/{self.event_id}/export-registrations")
        self.assertEqual(response.status_code, 200)
        sheet = load_workbook(BytesIO(response.data)).active
        return {str(cell.value) for row in sheet.iter_rows() for cell in row if cell.value}

    def page_rows(self):
        page = self.client_for("admin").get(f"/admin/events/{self.event_id}").get_data(as_text=True)
        raw = page.split('<script type="application/json" id="regData">', 1)[1].split("</script>", 1)[0]
        return {row["ma_cbsv"]: row for row in json.loads(raw)}

    def audit(self, action):
        with app.app_context():
            rows = AuditLog.query.filter_by(action=action, target_id=str(self.event_id)).order_by(AuditLog.id).all()
            return [json.loads(row.detail or "{}") for row in rows]

    # ---- quyền ----
    def test_staff_gets_403_and_no_button(self):
        staff = self.client_for("staff")
        self.assertEqual(self.cancel("A", client=staff).status_code, 403)
        self.assertEqual(self.restore("A", client=staff).status_code, 403)
        self.assertEqual(self.registration("A")["trang_thai"], "active")
        # staff không vào được trang chi tiết admin; trang staff không có nút xóa
        self.assertNotIn("registrations/cancel", staff.get(f"/staff/events/{self.event_id}").get_data(as_text=True))
        admin_page = self.client_for("admin").get(f"/admin/events/{self.event_id}").get_data(as_text=True)
        self.assertIn('const CAN_DELETE = true', admin_page)
        self.assertIn('id="bulkBar"', admin_page)

    def test_anonymous_cannot_cancel(self):
        self.assertEqual(self.cancel("A", client=self.client_for(None)).status_code, 401)

    # ---- xóa 1 người ----
    def test_cancel_one_disappears_everywhere_and_frees_seat(self):
        self.assertEqual(self.count(), 4)
        self.assertIn(self.codes["A"], self.export_codes())
        response = self.cancel("A", reason="  Đăng ký   ảo ", block=False)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        data = response.get_json()
        self.assertEqual([item["code"] for item in data["cancelled"]], [self.codes["A"]])
        self.assertEqual(data["registration_count"], 3)
        self.assertEqual(self.count(), 3)
        row = self.registration("A")
        self.assertEqual((row["trang_thai"], row["ly_do"], row["chan"]), ("cancelled", "Đăng ký ảo", False))
        self.assertEqual(row["huy_boi"], self.accounts["admin"][0])
        self.assertNotIn(self.codes["A"], self.export_codes())
        # vẫn còn dòng trong DB + người trong bảng users (không xóa thông tin người)
        with app.app_context():
            self.assertIsNotNone(db.session.get(User, self.codes["A"]))
        # trang chi tiết: có ở mục Đã hủy, không tính vào số liệu
        page = self.client_for("admin").get(f"/admin/events/{self.event_id}").get_data(as_text=True)
        self.assertIn('<strong id="statRegs">3</strong>', page)
        self.assertIn('data-count="cancelled">1<', page)
        # trang staff không còn người này
        self.assertNotIn(self.codes["A"], self.client_for("staff").get(f"/staff/events/{self.event_id}").get_data(as_text=True))

    def test_full_event_frees_seat_for_someone_else(self):
        with app.app_context():
            db.session.add(User(ma_cbsv=self.codes["E"], ho_ten="Người E", email="e@example.com"))
            db.session.commit()
        response = self.register("E")
        self.assertEqual(response.status_code, 400)
        self.assertIn("đủ số lượng", response.get_json()["message"])
        self.cancel("A")
        response = self.register("E")
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(self.count(), 4)

    def test_cancelled_person_can_register_again(self):
        self.cancel("A", reason="nhầm")
        response = self.register("A")
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        row = self.registration("A")
        self.assertEqual((row["trang_thai"], row["ly_do"], row["huy_boi"]), ("active", None, None))
        with app.app_context():
            self.assertEqual(Registration.query.filter_by(event_id=self.event_id, ma_cbsv=self.codes["A"]).count(), 1)
        self.assertTrue(self.audit("registration.reregister"))
        # đăng ký lần nữa thì bị từ chối như thường (sự kiện đủ chỗ -> báo đủ chỗ trước; không tạo dòng mới)
        self.assertNotEqual(self.register("A").status_code, 200)
        self.assertEqual(self.count(), 4)

    def test_blocked_code_cannot_register_again(self):
        self.cancel("A", reason="đăng ký ảo", block=True)
        response = self.register("A")
        self.assertEqual(response.status_code, 403)
        self.assertIn("không thể đăng ký sự kiện này", response.get_json()["message"])
        self.assertEqual(self.registration("A")["trang_thai"], "cancelled")
        self.restore("A")                                   # khôi phục = gỡ chặn
        self.assertFalse(self.registration("A")["chan"])

    # ---- người đã check-in ----
    def test_checked_in_person_cancelled_gets_no_certificate(self):
        with app.app_context():
            self.assertIn(self.codes["B"], mailer.select_targets(self.event_id))
        self.assertEqual(self.cancel("B").status_code, 200)
        with app.app_context():
            self.assertNotIn(self.codes["B"], mailer.select_targets(self.event_id))          # không gửi chứng chỉ
            self.assertFalse(validate_certificate_eligibility(self.codes["B"], self.event_id)[0])
            self.assertEqual(CheckinRecord.query.filter_by(event_id=self.event_id, patron_code=self.codes["B"]).count(), 1)
        admin = self.client_for("admin")
        rows = admin.get(f"/api/admin/events/{self.event_id}/checkins").get_json()["rows"]
        self.assertNotIn(self.codes["B"], {row["patron_code"] for row in rows})            # không hiện ở danh sách check-in
        # quét check-in lại: coi như chưa đăng ký
        response = admin.post("/api/checkin", json={"ma_cbsv": self.codes["B"], "event_id": self.event_id})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.audit("registration.cancel")[-1]["da_check_in"], [self.codes["B"]])

    # ---- bị chặn ----
    def test_certificate_and_lucky_winner_are_blocked(self):
        response = self.cancel("C")
        self.assertEqual(response.status_code, 409)
        self.assertIn("đã được cấp chứng chỉ, cần thu hồi chứng chỉ trước", response.get_json()["message"])
        response = self.cancel("D")
        self.assertEqual(response.status_code, 409)
        self.assertIn("trúng thưởng", response.get_json()["message"])
        self.assertEqual((self.registration("C")["trang_thai"], self.registration("D")["trang_thai"]), ("active", "active"))
        # trang chi tiết đánh dấu sẵn lý do để giao diện báo trước
        rows = self.page_rows()
        self.assertIn("cần thu hồi chứng chỉ trước", rows[self.codes["C"]]["cancel_blocked"])
        self.assertIn("trúng thưởng", rows[self.codes["D"]]["cancel_blocked"])
        self.assertEqual(rows[self.codes["A"]]["cancel_blocked"], "")

    def test_cancelled_lucky_winner_no_longer_blocks(self):
        with app.app_context():
            LuckyWinner.query.filter_by(event_id=self.event_id).update({"trang_thai": "cancelled", "hieu_luc": None})
            db.session.commit()
        self.assertEqual(self.cancel("D").status_code, 200)

    def test_bulk_skips_blocked_and_cancels_rest(self):
        response = self.cancel("ABCD", reason="dọn đăng ký ảo")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual({item["code"] for item in data["cancelled"]}, {self.codes["A"], self.codes["B"]})
        skipped = {item["code"]: item["reason"] for item in data["skipped"]}
        self.assertEqual(set(skipped), {self.codes["C"], self.codes["D"]})
        self.assertIn("chứng chỉ", skipped[self.codes["C"]])
        self.assertIn("trúng thưởng", skipped[self.codes["D"]])
        self.assertEqual(self.count(), 2)
        log = self.audit("registration.cancel_bulk")[-1]
        self.assertEqual(set(log["ma_cbsv"]), {self.codes["A"], self.codes["B"]})
        self.assertEqual(log["ly_do"], "dọn đăng ký ảo")
        self.assertEqual({item["ma_cbsv"] for item in log["bo_qua"]}, {self.codes["C"], self.codes["D"]})

    # ---- khôi phục ----
    def test_restore_brings_back_with_checkin(self):
        self.cancel("AB")
        response = self.restore("AB")
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(set(response.get_json()["restored"]), {self.codes["A"], self.codes["B"]})
        self.assertEqual(self.count(), 4)
        self.assertIn(self.codes["A"], self.export_codes())
        with app.app_context():
            self.assertIn(self.codes["B"], mailer.select_targets(self.event_id))           # check-in cũ tính lại
        self.assertEqual(set(self.audit("registration.restore")[-1]["ma_cbsv"]), {self.codes["A"], self.codes["B"]})
        self.assertEqual(self.restore("A").status_code, 409)                                # không còn gì để khôi phục

    def test_restore_over_capacity_warns(self):
        with app.app_context():
            db.session.add(User(ma_cbsv=self.codes["E"], ho_ten="Người E", email="e@example.com"))
            db.session.commit()
        self.cancel("A")
        self.assertEqual(self.register("E").status_code, 200)       # chỗ của A đã có người khác
        response = self.restore("A")
        self.assertEqual(response.status_code, 200)
        self.assertIn("vượt số lượng tối đa", response.get_json()["warning"])

    def test_audit_log_single_cancel(self):
        self.cancel("A", reason="đăng ký ảo", block=True)
        log = self.audit("registration.cancel")[-1]
        self.assertEqual(log["ma_cbsv"], self.codes["A"])
        self.assertEqual(log["ly_do"], "đăng ký ảo")
        self.assertTrue(log["chan_dang_ky_lai"])
        self.assertIn("Sự kiện thử xóa đăng ký", log["ten_su_kien"])
