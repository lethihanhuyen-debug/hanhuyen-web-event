import json

# Tạo fake email đơn giản (không gửi email thực)
with open('seed/data.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Restore email = ma_cbsv@test.local (fake domain)
for i, record in enumerate(data):
    record['email'] = f"{record['ma_cbsv']}@test.local"

with open('seed/data.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f'✓ Restore {len(data)} email: ma_cbsv@test.local')
print('✓ Email giả tạo không gửi được (chỉ test SMTP không báo lỗi)')
