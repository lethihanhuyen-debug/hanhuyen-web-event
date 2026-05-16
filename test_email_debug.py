import logging

logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(name)s - %(message)s')

from app import app

client = app.test_client()

print("=" * 70)
print("TEST: Lê Thị Hạnh Uyên (Mã: 1111)")
print("=" * 70)
print()

# Step 1: Register
print("1️⃣  REGISTER")
print("-" * 70)
r = client.post('/register', json={
    'ma_cbsv': '1111',
    'ho_ten': 'Lê Thị Hạnh Uyên',
    'don_vi': '',
    'email': '2200005635@nttu.edu.vn'
})
print(f"Status: {r.status_code}")
print(f"Success: {r.json['success']}")
print(f"Message: {r.json['message']}")
print()

# Step 2: Check-in
print("2️⃣  CHECK-IN")
print("-" * 70)
r2 = client.post('/api/checkin', json={'ma_cbsv': '1111'})
print(f"Status: {r2.status_code}")
print(f"Success: {r2.json['success']}")
print(f"Message: {r2.json['message']}")
print(f"Thời gian: {r2.json['thoi_gian']}")
print()

# Step 3: Email info
print("3️⃣  EMAIL DETAILS")
print("-" * 70)
print(f"From: hanhuyenxinchao@gmail.com")
print(f"To: 2200005635@nttu.edu.vn")
print(f"Subject: Xác nhận tham gia sự kiện")
print(f"Body: Cảm ơn Lê Thị Hạnh Uyên đã tham gia sự kiện...")
print()
print("✓ Nếu không có lỗi LOG ở trên -> email đã gửi")
print("✓ Kiểm tra: Inbox + Spam folder của 2200005635@nttu.edu.vn")
print("=" * 70)
