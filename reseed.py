import sys
import json

sys.path.insert(0, '.')

from config import Config
from event_checkin.models import db
from event_checkin.models.user import User
from event_checkin.models.registration import Registration
from event_checkin.models.checkin import CheckIn
from app import app

with app.app_context():
    # Xóa tất cả dữ liệu cũ
    CheckIn.query.delete()
    Registration.query.delete()
    User.query.delete()
    db.session.commit()
    
    # Load new data
    with open('seed/data.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Insert
    for record in data:
        user = User(
            ma_cbsv=record['ma_cbsv'],
            ho_ten=record['ho_ten'],
            don_vi=record['don_vi'],
            chuc_vu=record.get('chuc_vu', ''),
            so_dien_thoai=record.get('so_dien_thoai', ''),
            email=record.get('email', '')
        )
        db.session.add(user)
    
    db.session.commit()
    print(f'✓ Đã nạp {len(data)} bản ghi vào bảng users')
    print(f'✓ Email mẫu: {data[0]["email"]}')

