"""Ảnh (banner) sự kiện: kiểm tra/thu nhỏ/nén khi tải lên, kích thước trong DB (m008), hiển thị, giới hạn dung lượng.

Ảnh nằm ở thư mục tạm (tests/base.py: TEST_IMAGE_DIR), không đụng static/events thật."""
import os
from datetime import datetime, timedelta
from io import BytesIO

from PIL import Image
from sqlalchemy import text

from event_checkin import schema_status
from event_checkin.migrations import m008_event_image_size as m008
from event_checkin.models import db
from event_checkin.models.event import Event
from event_checkin.utils import event_image as event_images
from tests.base import TEST_IMAGE_BACKUP_DIR, TEST_IMAGE_DIR, AppTestCase, app


def make_image(width, height, fmt="PNG", noise=False, exif_orientation=None):
    if noise:
        image = Image.frombytes("RGB", (width, height), os.urandom(width * height * 3))
    else:
        image = Image.new("RGB", (width, height), (25, 118, 184))
        image.paste((46, 154, 95), (0, 0, width // 4, height))     # dải xanh lá bên trái: phân biệt chiều ảnh
    buffer = BytesIO()
    if exif_orientation:
        exif = Image.Exif()
        exif[0x0112] = exif_orientation
        image.save(buffer, fmt, exif=exif)
    else:
        image.save(buffer, fmt)
    return buffer.getvalue()


def size_in_db(event_id):
    with app.app_context():
        row = db.session.execute(text("SELECT hinh, hinh_width, hinh_height FROM events WHERE id = :id"), {"id": event_id}).first()
    return row


class EventImageTest(AppTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        now = datetime.utcnow()
        with app.app_context():
            ids = []
            for name in ("ảnh", "không ảnh"):
                event = Event(
                    ten_su_kien=f"Sự kiện thử {name} {cls.suffix}", ngay_bat_dau=now + timedelta(days=1),
                    ngay_ket_thuc=now + timedelta(days=1, hours=2), thang=now.month, nam=now.year,
                    thoi_gian_mo_dang_ky=now - timedelta(days=1), thoi_gian_dong_dang_ky=now + timedelta(days=1),
                    created_by=cls.accounts["super_admin"][0],
                )
                db.session.add(event)
                db.session.flush()
                ids.append(event.id)
            db.session.commit()
        cls.event_id, cls.plain_event_id = ids

    @classmethod
    def tearDownClass(cls):
        with app.app_context():
            Event.query.filter(Event.id.in_([cls.event_id, cls.plain_event_id])).delete(synchronize_session=False)
            db.session.commit()
        super().tearDownClass()

    def upload(self, data, filename="banner.png", client=None):
        client = client or self.client_for("admin")
        return client.post(f"/api/admin/events/{self.event_id}/image",
                           data={"event_image": (BytesIO(data), filename)}, content_type="multipart/form-data")

    # ---------- Tải lên ----------

    def test_large_image_is_resized_and_size_saved(self):
        response = self.upload(make_image(3000, 1000))
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        hinh, width, height = size_in_db(self.event_id)
        self.assertEqual((width, height), (2000, 667))
        stored = TEST_IMAGE_DIR / hinh.split("/", 1)[1]
        with Image.open(stored) as image:
            self.assertEqual(image.size, (2000, 667))
        data = response.get_json()["data"]
        self.assertEqual((data["hinh_width"], data["hinh_height"]), (2000, 667))

    def test_new_upload_gets_new_name_and_removes_old_file(self):
        self.upload(make_image(800, 600))
        first = TEST_IMAGE_DIR / size_in_db(self.event_id).hinh.split("/", 1)[1]
        self.assertTrue(first.is_file())
        self.upload(make_image(600, 600))
        second = TEST_IMAGE_DIR / size_in_db(self.event_id).hinh.split("/", 1)[1]
        self.assertNotEqual(first.name, second.name)      # tên mới -> trình duyệt không hiện ảnh cũ trong cache
        self.assertFalse(first.exists())
        self.assertEqual(size_in_db(self.event_id)[1:], (600, 600))

    def test_small_image_is_kept_byte_for_byte(self):
        data = make_image(1080, 1920, fmt="JPEG")
        self.upload(data, "doc.jpg")
        stored = TEST_IMAGE_DIR / size_in_db(self.event_id).hinh.split("/", 1)[1]
        self.assertEqual(stored.read_bytes(), data)
        self.assertEqual(size_in_db(self.event_id)[1:], (1080, 1920))

    def test_phone_photo_is_rotated_by_exif(self):
        self.upload(make_image(400, 200, fmt="JPEG", exif_orientation=6), "dien-thoai.jpg")
        self.assertEqual(size_in_db(self.event_id)[1:], (200, 400))

    def test_heavy_png_photo_becomes_jpeg(self):
        response = self.upload(make_image(2400, 1400, noise=True), "anh-chup.png")
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        hinh, width, height = size_in_db(self.event_id)
        self.assertTrue(hinh.endswith(".jpg"), hinh)
        self.assertEqual(width, 2000)
        self.assertLessEqual((TEST_IMAGE_DIR / hinh.split("/", 1)[1]).stat().st_size, event_images.MAX_BYTES)

    def test_fake_image_is_rejected(self):
        before = size_in_db(self.event_id).hinh
        for data in (b"day khong phai anh" * 50, make_image(300, 200)[:200]):   # file chữ, ảnh bị cắt cụt
            response = self.upload(data, "gia.png")
            self.assertEqual(response.status_code, 400)
            self.assertIn("không phải ảnh hợp lệ", response.get_json()["message"])
        self.assertEqual(size_in_db(self.event_id).hinh, before)

    def test_too_large_request_returns_vietnamese_message(self):
        saved = app.config["MAX_CONTENT_LENGTH"]
        app.config["MAX_CONTENT_LENGTH"] = 2000
        try:
            client = self.client_for("admin")
            response = self.upload(make_image(800, 600, noise=True), client=client)
            self.assertEqual(response.status_code, 413)
            self.assertIn("File quá lớn", response.get_json()["message"])
            # cùng giới hạn cho chỗ tải file khác (mẫu chứng chỉ)
            response = client.post(f"/api/admin/events/{self.event_id}/certificate-template",
                                   data={"certificate_template": (BytesIO(b"x" * 5000), "mau.png")},
                                   content_type="multipart/form-data")
            self.assertEqual(response.status_code, 413)
            self.assertIn("File quá lớn", response.get_json()["message"])
        finally:
            app.config["MAX_CONTENT_LENGTH"] = saved

    def test_default_limit_is_15mb(self):
        self.assertEqual(app.config["MAX_CONTENT_LENGTH"], 15 * 1024 * 1024)

    # ---------- Hiển thị ----------

    def test_pages_render_full_image_with_size(self):
        self.upload(make_image(1920, 600))
        client = self.client_for()
        page = client.get(f"/events/{self.event_id}/register").get_data(as_text=True)
        self.assertIn("event-media--detail", page)
        self.assertIn('width="1920" height="600"', page)
        home = client.get("/").get_data(as_text=True)
        self.assertIn("event-media--card", home)
        self.assertIn("event-media__backdrop", home)
        admin_page = self.client_for("admin").get("/admin/events").get_data(as_text=True)
        self.assertIn('width="1920" height="600"', admin_page)

    def test_event_without_image_shows_default(self):
        page = self.client_for().get(f"/events/{self.plain_event_id}/register").get_data(as_text=True)
        self.assertIn("images/event-default.svg", page)
        self.assertIn("event-media--default", page)

    def test_missing_m008_keeps_pages_and_blocks_only_upload(self):
        saved = app.extensions[schema_status.EXTENSION_KEY]
        app.extensions[schema_status.EXTENSION_KEY] = {"m008": ["thiếu cột events.hinh_width"]}
        try:
            response = self.client_for().get(f"/events/{self.event_id}/register")
            self.assertEqual(response.status_code, 200)
            self.assertNotIn('width="', response.get_data(as_text=True).split("event-media__img", 1)[1].split(">", 1)[0])
            response = self.upload(make_image(800, 600))
            self.assertEqual(response.status_code, 503)
            self.assertIn("m008", response.get_json()["message"])
        finally:
            app.extensions[schema_status.EXTENSION_KEY] = saved


class M008Test(AppTestCase):
    """m008 trên thư mục ảnh tạm: bản gốc chép trước khi sửa/xóa, dry-run không đổi gì, chạy lại an toàn."""

    def setUp(self):
        now = datetime.utcnow()
        for path in TEST_IMAGE_DIR.iterdir():
            path.unlink()
        with app.app_context():
            ids = []
            for name, data in (("ngang", make_image(4000, 1250)), ("png-nang", make_image(2400, 1400, noise=True))):
                event = Event(ten_su_kien=f"m008 {name}", ngay_bat_dau=now, ngay_ket_thuc=now, thang=now.month,
                              nam=now.year, thoi_gian_mo_dang_ky=now, thoi_gian_dong_dang_ky=now,
                              created_by=self.accounts["super_admin"][0])
                db.session.add(event)
                db.session.flush()
                filename = f"event_{event.id}_image.png"
                (TEST_IMAGE_DIR / filename).write_bytes(data)
                event.hinh = f"events/{filename}"
                ids.append(event.id)
            db.session.commit()
            for event_id in ids:
                db.session.execute(text("UPDATE events SET hinh_width = NULL, hinh_height = NULL WHERE id = :id"),
                                   {"id": event_id})
            db.session.commit()
        self.ids = ids
        (TEST_IMAGE_DIR / "event_999999_image.jpg").write_bytes(make_image(100, 100, fmt="JPEG"))  # ảnh thừa
        self.originals = {path.name: path.stat().st_size for path in TEST_IMAGE_DIR.iterdir()}

    def tearDown(self):
        with app.app_context():
            Event.query.filter(Event.id.in_(self.ids)).delete(synchronize_session=False)
            db.session.commit()

    def test_dry_run_changes_nothing(self):
        with app.app_context():
            lines = m008.migrate(dry_run=True)
        self.assertTrue(any("thu nhỏ/nén" in line and "4000x1250" in line for line in lines), lines)
        self.assertTrue(any("event_999999_image.jpg" in line for line in lines), lines)
        self.assertEqual({path.name: path.stat().st_size for path in TEST_IMAGE_DIR.iterdir()}, self.originals)
        self.assertEqual(size_in_db(self.ids[0])[1:], (None, None))

    def test_migrate_backs_up_then_shrinks_and_cleans(self):
        with app.app_context():
            self.assertTrue(m008.problems())
            m008.migrate()
            self.assertEqual(m008.problems(), [])
            self.assertEqual(m008.migrate(), [])                          # chạy lại: không còn gì để làm
        backup = TEST_IMAGE_BACKUP_DIR / "events"
        for name, size in self.originals.items():                          # mọi file bị sửa/xóa đều có bản gốc
            self.assertEqual((backup / name).stat().st_size, size, name)
        self.assertFalse((TEST_IMAGE_DIR / "event_999999_image.jpg").exists())
        hinh, width, height = size_in_db(self.ids[0])
        self.assertEqual((width, height), (2000, 625))
        with Image.open(TEST_IMAGE_DIR / hinh.split("/", 1)[1]) as image:
            self.assertEqual(image.size, (2000, 625))
        hinh, width, _height = size_in_db(self.ids[1])                      # PNG ảnh chụp nặng -> JPEG, tên mới
        self.assertTrue(hinh.endswith(".jpg"), hinh)
        self.assertTrue((TEST_IMAGE_DIR / hinh.split("/", 1)[1]).is_file())
        self.assertFalse((TEST_IMAGE_DIR / f"event_{self.ids[1]}_image.png").exists())
        self.assertEqual(width, 2000)
