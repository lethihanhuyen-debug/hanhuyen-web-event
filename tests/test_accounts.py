"""Bước (d): quản lý tài khoản, mật khẩu tạm / đổi mật khẩu, nhật ký hoạt động, xóa sự kiện (delete-impact)."""
import json
import re
from datetime import datetime, timedelta

from tests.base import AppTestCase, TEST_PASSWORD, app, db

from event_checkin import security
from event_checkin.models.admin import Admin
from event_checkin.models.audit_log import AuditLog
from event_checkin.models.checkin_record import CheckinRecord
from event_checkin.models.event import Event
from event_checkin.models.registration import Registration
from event_checkin.models.user import User
from event_checkin.utils.timezone import now_vn_naive


def audit_rows(action, since=None, **filters):
    with app.app_context():
        query = AuditLog.query.filter_by(action=action, **filters)
        if since:
            query = query.filter(AuditLog.created_at >= since)
        return query.order_by(AuditLog.id.asc()).all()


class AccountManagementTest(AppTestCase):
    def new_username(self, tag):
        return f"t_{tag}_{self.suffix}"

    def create(self, client, tag, role="staff", email=None):
        payload = {"username": self.new_username(tag), "role": role}
        if email:
            payload["email"] = email
        response = client.post("/api/admin/accounts", json=payload)
        if response.status_code == 201:
            self.extra_admin_ids.append(response.get_json()["data"]["id"])
        return response

    def login(self, username, password):
        client = app.test_client()
        return client, client.post("/api/admin/login", json={"username": username, "password": password})

    # ---- quyền truy cập ---------------------------------------------------------------------------------
    def test_only_super_admin_can_manage_accounts_and_see_audit(self):
        for role in ("admin", "staff"):
            c = self.client_for(role)
            for method, url in (("get", "/api/admin/accounts"), ("post", "/api/admin/accounts"),
                                ("put", "/api/admin/accounts/1"), ("post", "/api/admin/accounts/1/lock"),
                                ("post", "/api/admin/accounts/1/unlock"), ("delete", "/api/admin/accounts/1"),
                                ("post", "/api/admin/accounts/1/reset-password"), ("get", "/api/admin/audit-logs")):
                self.assertEqual(getattr(c, method)(url).status_code, 403, (role, url))
            for url in ("/admin/accounts", "/admin/audit-log"):
                self.assertEqual(c.get(url).status_code, 302, (role, url))
        anon = self.client_for(None)
        self.assertEqual(anon.get("/api/admin/accounts").status_code, 401)
        super_client = self.client_for("super_admin")
        for url in ("/admin/accounts", "/admin/audit-log", "/api/admin/accounts", "/api/admin/audit-logs"):
            self.assertEqual(super_client.get(url).status_code, 200, url)

    def test_hub_cards_only_for_super_admin(self):
        self.assertIn("Quản lý tài khoản", self.client_for("super_admin").get("/admin").get_data(as_text=True))
        self.assertIn("Nhật ký hoạt động", self.client_for("super_admin").get("/admin").get_data(as_text=True))
        admin_html = self.client_for("admin").get("/admin").get_data(as_text=True)
        self.assertNotIn("Quản lý tài khoản", admin_html)
        self.assertNotIn("Nhật ký hoạt động", admin_html)

    # ---- tạo tài khoản + mật khẩu tạm ----------------------------------------------------------------
    def test_create_account_temp_password_and_forced_change(self):
        sup = self.client_for("super_admin")
        r = self.create(sup, "n1", "staff", email=f"n1_{self.suffix}@example.com")
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        body = r.get_json()
        temp = body["temp_password"]
        self.assertTrue(10 <= len(temp) <= 12, temp)
        self.assertIsNone(security.password_error(temp))
        self.assertTrue(body["data"]["must_change_password"])
        self.assertNotIn("password_hash", json.dumps(body))

        user, login = self.login(self.new_username("n1"), temp)
        data = login.get_json()
        self.assertEqual(login.status_code, 200)
        self.assertTrue(data["must_change_password"])
        self.assertEqual(data["home_path"], "/admin/change-password")

        # Chưa đổi mật khẩu thì không vào được trang nào khác
        for url in ("/staff/events", "/admin", "/checkin", "/staff/events/1"):
            r = user.get(url)
            self.assertEqual((r.status_code, r.headers["Location"]), (302, "/admin/change-password"), url)
        r = user.get("/api/lookup/ABC")
        self.assertEqual((r.status_code, r.get_json().get("code")), (403, "must_change_password"))
        self.assertEqual(user.post("/api/checkin", json={"ma_cbsv": "x", "event_id": 1}).status_code, 403)
        self.assertEqual(user.get("/admin/change-password").status_code, 200)
        self.assertEqual(user.post("/api/admin/logout").status_code, 200)   # vẫn đăng xuất được

    def test_change_password_rules_and_session_invalidation(self):
        sup = self.client_for("super_admin")
        temp = self.create(sup, "n2", "staff").get_json()["temp_password"]
        username = self.new_username("n2")
        first, _ = self.login(username, temp)
        other, _ = self.login(username, temp)              # thiết bị thứ hai

        def change(client, **payload):
            return client.post("/api/admin/change-password", json=payload)

        self.assertEqual(change(first, current_password="sai", new_password="Moi12345", confirm_password="Moi12345").status_code, 400)
        for weak in ("ngan1", "chicoChuCaiNhe", "123456789"):
            r = change(first, current_password=temp, new_password=weak, confirm_password=weak)
            self.assertEqual(r.status_code, 400, weak)
            self.assertIn("Mật khẩu tối thiểu 8 ký tự", r.get_json()["message"])
        self.assertEqual(change(first, current_password=temp, new_password="Moi12345", confirm_password="Khac12345").status_code, 400)
        self.assertEqual(change(first, current_password=temp, new_password=temp, confirm_password=temp).status_code, 400)

        ok = change(first, current_password=temp, new_password="Moi12345", confirm_password="Moi12345")
        self.assertEqual(ok.status_code, 200, ok.get_data(as_text=True))
        self.assertEqual(ok.get_json()["home_path"], "/staff/events")
        self.assertEqual(first.get("/staff/events").status_code, 200)                 # phiên đang đổi mật khẩu được giữ lại
        old_session = other.get("/staff/events")                                       # phiên ở thiết bị khác bị đăng xuất
        self.assertEqual(old_session.status_code, 302)
        self.assertTrue(old_session.headers["Location"].startswith("/admin/login"))
        self.assertEqual(self.login(username, temp)[1].status_code, 401)               # mật khẩu tạm hết dùng được
        again, login = self.login(username, "Moi12345")
        self.assertEqual(login.status_code, 200)
        self.assertFalse(login.get_json()["must_change_password"])
        self.assertEqual(again.get("/staff/events").status_code, 200)
        with app.app_context():
            account_id = Admin.query.filter_by(username=username).first().id
        self.assertEqual(len(audit_rows("password.change", admin_id=account_id)), 1)

    # ---- kiểm tra dữ liệu đầu vào + trùng ------------------------------------------------------------------
    def test_create_validation(self):
        sup = self.client_for("super_admin")
        post = lambda **p: sup.post("/api/admin/accounts", json=p)  # noqa: E731
        self.assertEqual(post(username="ab", role="staff").status_code, 400)            # quá ngắn
        self.assertEqual(post(username="co dau cach", role="staff").status_code, 400)
        self.assertEqual(post(username=self.new_username("v"), role="boss").status_code, 400)
        self.assertEqual(post(username=self.new_username("v"), role="staff", email="khong-phai-email").status_code, 400)
        self.assertEqual(self.create(sup, "dup", "staff", email=f"dup_{self.suffix}@example.com").status_code, 201)
        self.assertEqual(self.create(sup, "dup", "admin").status_code, 409)             # trùng tên đăng nhập
        self.assertEqual(post(username=self.new_username("dup2"), role="staff", email=f"DUP_{self.suffix}@example.com").status_code, 409)  # trùng email (không phân biệt hoa thường)

    def test_list_and_search(self):
        sup = self.client_for("super_admin")
        self.create(sup, "find", "admin")
        data = sup.get("/api/admin/accounts", query_string={"q": f"find_{self.suffix}"}).get_json()["data"]
        self.assertEqual([a["username"] for a in data], [self.new_username("find")])
        everyone = sup.get("/api/admin/accounts").get_json()["data"]
        me = [a for a in everyone if a["is_self"]]
        self.assertEqual([a["username"] for a in me], [self.accounts["super_admin"][1]])
        self.assertNotIn("password_hash", json.dumps(everyone))

    # ---- đổi vai trò / email ------------------------------------------------------------------------
    def test_role_change_logs_target_out_immediately(self):
        sup = self.client_for("super_admin")
        temp = self.create(sup, "r1", "staff").get_json()["temp_password"]
        account = sup.get("/api/admin/accounts", query_string={"q": self.new_username("r1")}).get_json()["data"][0]
        # đăng nhập + đổi mật khẩu để dùng được
        client, _ = self.login(self.new_username("r1"), temp)
        client.post("/api/admin/change-password", json={"current_password": temp, "new_password": "Moi12345", "confirm_password": "Moi12345"})
        self.assertEqual(client.get("/staff/events").status_code, 200)

        r = sup.put(f"/api/admin/accounts/{account['id']}", json={"role": "admin", "email": f"r1_{self.suffix}@example.com"})
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        self.assertEqual(r.get_json()["data"]["role"], "admin")
        self.assertEqual(client.get("/staff/events").status_code, 302)                  # phiên cũ mất hiệu lực ngay
        relog, login = self.login(self.new_username("r1"), "Moi12345")
        self.assertEqual(login.get_json()["admin"]["role"], "admin")
        self.assertEqual(relog.get("/admin").status_code, 200)

        changes = audit_rows("account.role_change", target_id=str(account["id"]))
        self.assertEqual(len(changes), 1)
        self.assertEqual(json.loads(changes[0].detail)["from"], "staff")
        self.assertEqual(json.loads(changes[0].detail)["to"], "admin")

        self.assertEqual(sup.put(f"/api/admin/accounts/{account['id']}", json={"role": "boss"}).status_code, 400)
        self.assertEqual(sup.put(f"/api/admin/accounts/{account['id']}", json={"email": "sai-dinh-dang"}).status_code, 400)
        self.assertEqual(sup.put("/api/admin/accounts/99999999", json={"role": "staff"}).status_code, 404)

    def test_cannot_change_own_role_lock_delete_or_reset_self(self):
        sup = self.client_for("super_admin")
        me = self.accounts["super_admin"][0]
        self.assertEqual(sup.put(f"/api/admin/accounts/{me}", json={"role": "staff"}).status_code, 409)
        self.assertEqual(sup.post(f"/api/admin/accounts/{me}/lock").status_code, 409)
        self.assertEqual(sup.delete(f"/api/admin/accounts/{me}").status_code, 409)
        self.assertEqual(sup.post(f"/api/admin/accounts/{me}/reset-password").status_code, 409)
        self.assertEqual(sup.get("/api/admin/accounts").status_code, 200)               # vẫn đăng nhập bình thường

    def test_last_active_super_admin_is_protected(self):
        from event_checkin.controllers.account_controller import _is_last_active_super_admin
        with app.app_context():
            supers = Admin.query.filter_by(role="super_admin", is_active=True).all()
            target = next(a for a in supers if a.id == self.accounts["super_admin"][0])
            others = [a.id for a in supers if a.id != target.id]
            self.assertTrue(others, "DB thử nên còn super_admin khác")
            self.assertFalse(_is_last_active_super_admin(target))                       # còn người khác
        with app.app_context():
            Admin.query.filter(Admin.id.in_(others)).update({"is_active": False}, synchronize_session=False)
            db.session.commit()
        try:
            with app.app_context():
                target = db.session.get(Admin, self.accounts["super_admin"][0])
                self.assertTrue(_is_last_active_super_admin(target))                    # giờ là người cuối cùng
                staff = db.session.get(Admin, self.accounts["staff"][0])
                self.assertFalse(_is_last_active_super_admin(staff))
        finally:
            with app.app_context():
                Admin.query.filter(Admin.id.in_(others)).update({"is_active": True}, synchronize_session=False)
                db.session.commit()

    # ---- khóa / mở khóa / đặt lại mật khẩu / xóa -------------------------------------------------------
    def test_lock_unlock(self):
        sup = self.client_for("super_admin")
        temp = self.create(sup, "l1", "admin").get_json()["temp_password"]
        username = self.new_username("l1")
        acc = sup.get("/api/admin/accounts", query_string={"q": username}).get_json()["data"][0]
        client, _ = self.login(username, temp)
        client.post("/api/admin/change-password", json={"current_password": temp, "new_password": "Moi12345", "confirm_password": "Moi12345"})
        self.assertEqual(client.get("/api/admin/events").status_code, 200)

        self.assertEqual(sup.post(f"/api/admin/accounts/{acc['id']}/lock").status_code, 200)
        self.assertEqual(client.get("/api/admin/events").status_code, 401)             # bị khóa: văng ngay
        self.assertEqual(self.login(username, "Moi12345")[1].status_code, 401)        # và không đăng nhập lại được
        self.assertEqual(sup.post(f"/api/admin/accounts/{acc['id']}/unlock").status_code, 200)
        self.assertEqual(self.login(username, "Moi12345")[1].status_code, 200)
        self.assertEqual(len(audit_rows("account.lock", target_id=str(acc["id"]))), 1)
        self.assertEqual(len(audit_rows("account.unlock", target_id=str(acc["id"]))), 1)

    def test_reset_password_by_super_admin(self):
        sup = self.client_for("super_admin")
        temp = self.create(sup, "p1", "staff").get_json()["temp_password"]
        username = self.new_username("p1")
        acc = sup.get("/api/admin/accounts", query_string={"q": username}).get_json()["data"][0]
        client, _ = self.login(username, temp)
        client.post("/api/admin/change-password", json={"current_password": temp, "new_password": "Moi12345", "confirm_password": "Moi12345"})
        self.assertEqual(client.get("/staff/events").status_code, 200)

        r = sup.post(f"/api/admin/accounts/{acc['id']}/reset-password")
        self.assertEqual(r.status_code, 200)
        new_temp = r.get_json()["temp_password"]
        self.assertNotEqual(new_temp, temp)
        self.assertIsNone(security.password_error(new_temp))
        self.assertEqual(client.get("/staff/events").status_code, 302)                 # phiên đang mở bị đăng xuất
        self.assertEqual(self.login(username, "Moi12345")[1].status_code, 401)         # mật khẩu cũ hết dùng được
        _, login = self.login(username, new_temp)
        self.assertTrue(login.get_json()["must_change_password"])                      # buộc đổi lại
        self.assertEqual(len(audit_rows("account.reset_password", target_id=str(acc["id"]))), 1)

    def test_delete_account(self):
        sup = self.client_for("super_admin")
        self.create(sup, "d1", "staff")
        acc = sup.get("/api/admin/accounts", query_string={"q": self.new_username("d1")}).get_json()["data"][0]
        r = sup.delete(f"/api/admin/accounts/{acc['id']}")
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        self.assertEqual(sup.get("/api/admin/accounts", query_string={"q": self.new_username("d1")}).get_json()["data"], [])
        self.assertEqual(sup.delete(f"/api/admin/accounts/{acc['id']}").status_code, 404)
        deleted = audit_rows("account.delete", target_id=str(acc["id"]))
        self.assertEqual(json.loads(deleted[0].detail)["username"], self.new_username("d1"))   # nhật ký vẫn nhớ tên dù đã xóa

    def test_cannot_delete_account_with_related_data(self):
        sup = self.client_for("super_admin")
        self.create(sup, "d2", "staff")
        acc = sup.get("/api/admin/accounts", query_string={"q": self.new_username("d2")}).get_json()["data"][0]
        with app.app_context():
            child = Admin(username=self.new_username("d2child"), password_hash="x", role="staff", created_by=acc["id"])
            db.session.add(child)
            db.session.commit()
            self.extra_admin_ids.append(child.id)
        r = sup.delete(f"/api/admin/accounts/{acc['id']}")
        self.assertEqual(r.status_code, 409)
        self.assertIn("khóa tài khoản", r.get_json()["message"])
        still = sup.get("/api/admin/accounts", query_string={"q": self.new_username("d2")}).get_json()["data"]
        self.assertEqual([a["username"] for a in still], [self.new_username("d2")])      # vẫn còn nguyên


class AuditAndEventDeleteTest(AppTestCase):
    def make_event(self, client, name):
        start = (now_vn_naive() + timedelta(days=3)).replace(microsecond=0, second=0)
        payload = {
            "ten_su_kien": name, "dia_diem": "Phòng thử",
            "ngay_bat_dau": start.isoformat(), "ngay_ket_thuc": (start + timedelta(hours=2)).isoformat(),
            "thoi_gian_mo_dang_ky": (now_vn_naive() + timedelta(hours=1)).replace(microsecond=0).isoformat(),
            "thoi_gian_dong_dang_ky": (start - timedelta(hours=1)).isoformat(),
        }
        return client.post("/api/admin/events", json=payload), payload

    def test_login_logout_failure_are_logged(self):
        marker = datetime.utcnow() - timedelta(seconds=1)
        username = self.accounts["staff"][1]
        staff_id = self.accounts["staff"][0]
        logins_before = len(audit_rows("auth.login", admin_id=staff_id))
        logouts_before = len(audit_rows("auth.logout", admin_id=staff_id))
        bad = app.test_client().post("/api/admin/login", json={"username": username, "password": "sai-mat-khau"})
        self.assertEqual(bad.status_code, 401)
        client = self.client_for("staff")
        client.post("/api/admin/logout")
        failed = audit_rows("auth.login_failed", marker)
        self.assertTrue(any(r.username == username and r.ip for r in failed))
        self.assertNotIn("sai-mat-khau", "".join(r.detail or "" for r in failed))        # không ghi mật khẩu
        ok = audit_rows("auth.login", admin_id=staff_id)
        self.assertEqual(len(ok), logins_before + 1)
        self.assertEqual(ok[-1].username, username)
        self.assertEqual(len(audit_rows("auth.logout", admin_id=staff_id)), logouts_before + 1)

    def test_event_lifecycle_audited_with_updated_by_and_delete_impact(self):
        marker = datetime.utcnow() - timedelta(seconds=1)
        admin, sup = self.client_for("admin"), self.client_for("super_admin")
        r, payload = self.make_event(admin, f"Sự kiện nhật ký {self.suffix}")
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        event_id = r.get_json()["data"]["id"]
        try:
            created = audit_rows("event.create", marker, target_id=str(event_id))
            self.assertEqual((len(created), created[0].admin_id), (1, self.accounts["admin"][0]))

            payload["ten_su_kien"] += " (sửa)"
            self.assertEqual(admin.put(f"/api/admin/events/{event_id}", json=payload).status_code, 200)
            self.assertEqual(len(audit_rows("event.update", marker, target_id=str(event_id))), 1)
            with app.app_context():
                self.assertEqual(db.session.get(Event, event_id).updated_by, self.accounts["admin"][0])   # ai sửa gần nhất

            # dữ liệu để đo "sẽ mất gì": 2 đăng ký, 3 lượt check-in của 2 người
            with app.app_context():
                for code in (f"IA{self.suffix}".upper(), f"IB{self.suffix}".upper()):
                    db.session.add(User(ma_cbsv=code, ho_ten="Người thử", email=f"{code.lower()}@example.com"))
                    db.session.flush()
                    db.session.add(Registration(ma_cbsv=code, event_id=event_id))
                db.session.add_all([
                    CheckinRecord(event_id=event_id, patron_code=f"IA{self.suffix}".upper()),
                    CheckinRecord(event_id=event_id, patron_code=f"IA{self.suffix}".upper()),
                    CheckinRecord(event_id=event_id, patron_code=f"IB{self.suffix}".upper()),
                ])
                db.session.commit()

            # admin KHÔNG xóa được và không xem được số liệu xóa; bị từ chối thì không có dòng nhật ký xóa
            self.assertEqual(admin.get(f"/api/admin/events/{event_id}/delete-impact").status_code, 403)
            self.assertEqual(admin.delete(f"/api/admin/events/{event_id}").status_code, 403)
            self.assertEqual(self.client_for("staff").get(f"/api/admin/events/{event_id}/delete-impact").status_code, 403)
            self.assertEqual(audit_rows("event.delete", marker, target_id=str(event_id)), [])

            impact = sup.get(f"/api/admin/events/{event_id}/delete-impact").get_json()["data"]
            self.assertEqual((impact["registrations"], impact["checkin_records"], impact["checkin_people"]), (2, 3, 2))
            self.assertEqual(sup.get("/api/admin/events/99999999/delete-impact").status_code, 404)

            self.assertEqual(sup.delete(f"/api/admin/events/{event_id}").status_code, 200)
            deleted = audit_rows("event.delete", marker, target_id=str(event_id))
            detail = json.loads(deleted[0].detail)
            self.assertEqual((len(deleted), detail["registrations"], detail["checkin_records"], detail["checkin_people"]), (1, 2, 3, 2))
            self.assertIn("(sửa)", detail["ten_su_kien"])                                # nhật ký nhớ tên dù sự kiện đã mất
        finally:
            with app.app_context():
                CheckinRecord.query.filter_by(event_id=event_id).delete()
                Registration.query.filter_by(event_id=event_id).delete()
                User.query.filter(User.ma_cbsv.in_([f"IA{self.suffix}".upper(), f"IB{self.suffix}".upper()])).delete(synchronize_session=False)
                Event.query.filter_by(id=event_id).delete()
                db.session.commit()

    def test_export_is_logged_and_failure_is_not(self):
        marker = datetime.utcnow() - timedelta(seconds=1)
        admin = self.client_for("admin")
        with app.app_context():
            event_id = Registration.query.first().event_id      # sự kiện có người đăng ký (xuất rỗng bị từ chối 400)
        self.assertEqual(admin.get(f"/api/admin/events/{event_id}/export-registrations").status_code, 200)
        self.assertEqual(admin.get("/admin/export/csv").status_code, 200)
        self.assertEqual(len(audit_rows("export.registrations", marker, target_id=str(event_id))), 1)
        self.assertEqual(len(audit_rows("export.csv", marker)), 1)
        # 403 (staff) không để lại dòng nhật ký xuất dữ liệu
        self.client_for("staff").get(f"/api/admin/events/{event_id}/export-registrations")
        self.assertEqual(len(audit_rows("export.registrations", marker, target_id=str(event_id))), 1)
        # 404 cũng không ghi
        admin.get("/api/admin/events/99999999/export-registrations")
        self.assertEqual(len(audit_rows("export.registrations", marker, target_id="99999999")), 0)

    def test_audit_api_filters_pagination_and_vn_time(self):
        sup = self.client_for("super_admin")
        staff_name = self.accounts["staff"][1]
        self.client_for("staff")                                                          # tạo dòng auth.login của staff
        body = sup.get("/api/admin/audit-logs", query_string={"user": staff_name, "action": "auth.login"}).get_json()
        self.assertTrue(body["success"])
        self.assertGreaterEqual(body["total"], 1)
        row = body["data"][0]
        self.assertEqual((row["username"], row["action"], row["action_label"]), (staff_name, "auth.login", "Đăng nhập"))
        self.assertRegex(row["time"], r"^\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}$")
        # giờ hiển thị = giờ VN (UTC+7): so với đồng hồ VN hiện tại lệch không quá vài phút
        shown = datetime.strptime(row["time"], "%d/%m/%Y %H:%M:%S")
        self.assertLess(abs((now_vn_naive() - shown).total_seconds()), 300)

        today = now_vn_naive().strftime("%Y-%m-%d")
        tomorrow = (now_vn_naive() + timedelta(days=1)).strftime("%Y-%m-%d")
        in_today = sup.get("/api/admin/audit-logs", query_string={"user": staff_name, "from": today, "to": today}).get_json()["total"]
        self.assertGreaterEqual(in_today, 1)
        self.assertEqual(sup.get("/api/admin/audit-logs", query_string={"user": staff_name, "from": tomorrow}).get_json()["total"], 0)
        self.assertEqual(sup.get("/api/admin/audit-logs", query_string={"user": "khong-co-nguoi-nay-xyz"}).get_json()["total"], 0)
        page2 = sup.get("/api/admin/audit-logs", query_string={"page": 2}).get_json()
        self.assertEqual((page2["page"], page2["page_size"]), (2, 50))
        self.assertLessEqual(len(page2["data"]), 50)
        # sắp xếp mới nhất trước
        ids = [r["id"] for r in sup.get("/api/admin/audit-logs").get_json()["data"]]
        self.assertEqual(ids, sorted(ids, reverse=True))

    def test_audit_log_has_no_edit_or_delete_endpoints(self):
        sup = self.client_for("super_admin")
        for method in ("put", "post", "delete", "patch"):
            self.assertIn(getattr(sup, method)("/api/admin/audit-logs").status_code, (404, 405), method)


class PageScriptOrderTest(AppTestCase):
    """main.js được nạp kiểu `defer` nên chạy SAU script nội tuyến cuối trang: lệnh tải dữ liệu ban đầu dùng
    apiFetch/apiFetchQuiet (định nghĩa trong main.js) phải đợi DOMContentLoaded, nếu không trang kẹt ở "Đang tải…"."""

    def test_initial_load_waits_for_dom_ready(self):
        for name in ("accounts", "audit_log"):
            html = self.client_for("super_admin").get("/admin/accounts" if name == "accounts" else "/admin/audit-log").get_data(as_text=True)
            script = html.split("<script>")[-1]
            self.assertIn("addEventListener('DOMContentLoaded', load)", script, name)
            self.assertNotRegex(script, r"(?m)^\s*load\(\);\s*$", name + ": còn gọi load() ngay lúc nạp trang")
