import logging
import sys

# Enable debug logging
logging.basicConfig(level=logging.DEBUG, format='%(name)s - %(levelname)s - %(message)s')

from app import app

client = app.test_client()

# Test check-in mã 1234
print("=== TEST CHECK-IN MA 1234 ===\n")

# Kiểm tra user 1234 có tồn tại không
r = client.get('/api/lookup/1234')
print(f"Lookup mã 1234: {r.status_code}")
print(f"Response: {r.json if r.status_code == 200 else 'Không tìm thấy'}\n")

# Nếu không có, tạo mới
if r.status_code != 200:
    print("Mã 1234 không tồn tại, tạo mới...")
    r = client.post('/register', json={
        'ma_cbsv': '1234',
        'ho_ten': 'Test User 1234',
        'don_vi': 'Test Dept',
        'email': '1234@test.local'
    })
    print(f"Register: {r.status_code} - {r.json}\n")

# Test check-in
print("Thực hiện check-in mã 1234...")
r2 = client.post('/api/checkin', json={'ma_cbsv': '1234'})
print(f"\nCheck-in Response Code: {r2.status_code}")
print(f"Response JSON: {r2.json}")

if r2.json.get('success'):
    print("\n✓ Check-in THÀNH CÔNG")
    print(f"  - Người: {r2.json.get('ho_ten')}")
    print(f"  - Email: {r2.json.get('email')}")
    print(f"  - Thời gian: {r2.json.get('thoi_gian')}")
    print("\nEmail xác nhận đã gửi (kiểm tra log trên)")
else:
    print(f"\n✗ Check-in THẤT BẠI: {r2.json.get('message')}")
