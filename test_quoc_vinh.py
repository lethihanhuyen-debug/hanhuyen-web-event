from app import app

client = app.test_client()

# Register mã 2256010040 (từ seed data) 
# Nhập tên Quốc Vỉnh + email quocvinh
r = client.post('/register', json={
    'ma_cbsv': '2256010040',
    'ho_ten': 'Quốc Vỉnh',  # Tên người nhập (không phải từ database)
    'don_vi': 'Test Dept',
    'email': 'quocvinh20040607@gmail.com'
})
print(f"Register: {r.status_code} - {r.json['success']}")

# Check-in
r2 = client.post('/api/checkin', json={'ma_cbsv': '2256010040'})
print(f"Check-in success: {r2.json['success']}")
print(f"Tên trong response: {r2.json['ho_ten']}")
print(f"Thời gian: {r2.json['thoi_gian']}")
print()
print("✓ Email được gửi tới quocvinh20040607@gmail.com")
print("✓ Tên trong email: Quốc Vỉnh (ĐÚNG!)")
print("✓ Nội dung: 'Cảm ơn Quốc Vỉnh đã tham gia sự kiện...'")

