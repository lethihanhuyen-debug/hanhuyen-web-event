"""Nền chung cho test: CHỈ chạy trên DB có tên kết thúc bằng "_test" (chặn chạy nhầm lên DB thật).

Cách chạy (PowerShell, tại thư mục gốc dự án):
    $env:MYSQL_DATABASE = "checkin_event_test"
    .venv\\Scripts\\python -m unittest discover -s . -t . -p "test_*.py" -v
"""
import secrets
import sys
import unittest
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

from config import Config

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # console Windows mặc định không in được tiếng Việt

if not Config.MYSQL_DATABASE.endswith("_test"):
    raise SystemExit(
        f"DỪNG: test chỉ chạy trên DB tên kết thúc bằng '_test' (đang trỏ tới '{Config.MYSQL_DATABASE}'). "
        "Đặt $env:MYSQL_DATABASE = 'checkin_event_test' rồi chạy lại."
    )

from app import app  # noqa: E402  (phải import SAU khi kiểm tra tên DB)
from event_checkin.models import db  # noqa: E402
from event_checkin.models.admin import Admin  # noqa: E402
from event_checkin.models.audit_log import AuditLog  # noqa: E402
from event_checkin.models.password_reset import PasswordReset  # noqa: E402

TEST_PASSWORD = "Test1234x"

# File chứng chỉ do test tạo ra nằm ở thư mục tạm riêng, không lẫn vào thư mục chứng chỉ thật (instance/certificates)
import atexit  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

TEST_CERT_DIR = Path(tempfile.mkdtemp(prefix="cert_test_"))
app.config["CERTIFICATE_STORAGE_DIR"] = TEST_CERT_DIR
atexit.register(shutil.rmtree, TEST_CERT_DIR, True)


class AppTestCase(unittest.TestCase):
    """Tạo 3 tài khoản thử (super_admin / admin / staff) cho cả lớp test, xóa khi xong."""

    accounts = {}

    @classmethod
    def setUpClass(cls):
        cls.app = app
        cls.suffix = secrets.token_hex(3)
        cls.accounts = {}
        cls.extra_admin_ids = []          # tài khoản tạo thêm trong test, xóa ở tearDownClass
        cls.started_at = datetime.utcnow() - timedelta(seconds=2)
        with app.app_context():
            for role in ("super_admin", "admin", "staff"):
                username = f"t_{role}_{cls.suffix}"
                admin = Admin(username=username, password_hash=generate_password_hash(TEST_PASSWORD), role=role, is_active=True)
                db.session.add(admin)
                db.session.flush()
                cls.accounts[role] = (admin.id, username)
            db.session.commit()

    @classmethod
    def tearDownClass(cls):
        with app.app_context():
            ids = [admin_id for admin_id, _username in cls.accounts.values()] + list(cls.extra_admin_ids)
            PasswordReset.query.filter(PasswordReset.admin_id.in_(ids)).delete(synchronize_session=False)
            # tài khoản do tài khoản khác tạo trỏ created_by về nhau: gỡ liên kết trước khi xóa
            Admin.query.filter(Admin.created_by.in_(ids)).update({"created_by": None}, synchronize_session=False)
            Admin.query.filter(Admin.id.in_(ids)).delete(synchronize_session=False)
            AuditLog.query.filter(AuditLog.created_at >= cls.started_at).delete(synchronize_session=False)  # dọn nhật ký do test sinh ra
            db.session.commit()

    def client_for(self, role=None):
        """test_client đã đăng nhập bằng API thật (cùng đường đi như trình duyệt). role=None -> chưa đăng nhập."""
        client = app.test_client()
        if role:
            response = client.post("/api/admin/login", json={"username": self.accounts[role][1], "password": TEST_PASSWORD})
            self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return client

    def set_admin(self, account, **fields):
        """Sửa trực tiếp trong DB tài khoản thử `account` (tên vai trò lúc tạo), vd. set_admin('admin', role='staff')."""
        with app.app_context():
            Admin.query.filter_by(id=self.accounts[account][0]).update(fields)
            db.session.commit()
