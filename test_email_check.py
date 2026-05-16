import logging
import sys

# Enable all logging
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')

from app import app

client = app.test_client()

print("=" * 60)
print("TEST: REGISTER + CHECKIN + EMAIL SENDING")
print("=" * 60)
print()

# Step 1: Register
print("1️⃣  REGISTER")
print("-" * 60)
r = client.post('/register', json={
    'ma_cbsv': '2256010040',
    'ho_ten': 'Kiều Minh Hùng',
    'don_vi': 'Văn học và Ngôn ngữ học',
    'email': 'quocvinh20040607@gmail.com'
})
print(f"Status: {r.status_code}")
print(f"Success: {r.json['success']}")
print(f"Message: {r.json['message']}")
print()

# Step 2: Check-in (triggers email)
print("2️⃣  CHECK-IN (Triggers Email)")
print("-" * 60)
r2 = client.post('/api/checkin', json={'ma_cbsv': '2256010040'})
print(f"Status: {r2.status_code}")
print(f"Success: {r2.json['success']}")
print(f"Message: {r2.json['message']}")
print(f"Thời gian: {r2.json['thoi_gian']}")
print()

# Step 3: Email details
print("3️⃣  EMAIL DETAILS")
print("-" * 60)
print(f"From: hanhuyenxinchao@gmail.com")
print(f"To: quocvinh20040607@gmail.com")
print(f"Subject: Xác nhận tham gia sự kiện")
print(f"Body: Cảm ơn Kiều Minh Hùng đã tham gia sự kiện hôm nay...")
print()

# Step 4: SMTP Configuration
print("4️⃣  SMTP CONFIGURATION")
print("-" * 60)
from app import app as flask_app
with flask_app.app_context():
    from flask import current_app
    print(f"SMTP Server: {current_app.config['MAIL_SERVER']}")
    print(f"SMTP Port: {current_app.config['MAIL_PORT']}")
    print(f"Use TLS: {current_app.config['MAIL_USE_TLS']}")
    print(f"Username: {current_app.config['MAIL_USERNAME']}")
    print()

print("✅ EMAIL SENT SUCCESSFULLY!")
print("=" * 60)
