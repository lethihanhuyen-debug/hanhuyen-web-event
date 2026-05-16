from app import app

client = app.test_client()

print('=' * 70)
print('Test user mới - gửi email tới: 2200005635@nttu.edu.vn')
print('=' * 70)
print()

# Register user mới
r = client.post('/register', json={
    'ma_cbsv': '9999',
    'ho_ten': 'Lê Thị Hạnh Uyên TEST',
    'don_vi': 'Test Dept',
    'email': '2200005635@nttu.edu.vn'
})
print(f"1. Register mã 9999")
print(f"   Status: {r.status_code} - {r.json['success']}")
print()

# Check-in (gửi email)
r2 = client.post('/api/checkin', json={'ma_cbsv': '9999'})
print(f"2. Check-in mã 9999 (gửi email)")
print(f"   Status: {r2.status_code} - {r2.json['success']}")
print(f"   Message: {r2.json['message']}")
print()

print("3. Email gửi tới:")
print(f"   Địa chỉ: 2200005635@nttu.edu.vn")
print(f"   Từ: hanhuyenxinchao@gmail.com")
print(f"   Tên: Lê Thị Hạnh Uyên TEST")
print()
print("✓ Nếu trên không có lỗi -> email đã gửi")
print("✓ Kiểm tra: Inbox/Spam của 2200005635@nttu.edu.vn")
print("=" * 70)
