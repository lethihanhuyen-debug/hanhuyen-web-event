from app import app

client = app.test_client()

print("=== TEST REGISTER + CHECKIN ===\n")

# Step 1: Register với email thực
print("1. Register mã 2256010040 (Kiều Minh Hùng)")
r = client.post('/register', json={
    'ma_cbsv': '2256010040',
    'ho_ten': 'Kiều Minh Hùng',
    'don_vi': 'Văn học và Ngôn ngữ học',
    'email': 'quocvinh20040607@gmail.com'  # Email thực người nhập
})
print(f"   Status: {r.status_code}")
print(f"   Success: {r.json['success']}")
print(f"   Message: {r.json['message']}\n")

# Step 2: Check-in → gửi email
print("2. Check-in mã 2256010040")
r2 = client.post('/api/checkin', json={'ma_cbsv': '2256010040'})
print(f"   Status: {r2.status_code}")
print(f"   Success: {r2.json['success']}")
print(f"   Message: {r2.json['message']}")
print(f"   Email sent to: quocvinh20040607@gmail.com ✓")
