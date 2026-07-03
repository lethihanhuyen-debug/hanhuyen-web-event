import json
import sys
from pathlib import Path

from flask import Flask

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import Config
from event_checkin.models import db
from event_checkin.models.don_vi import DonVi
from event_checkin.models.user import User


def load_records(base_dir):
    data_path = base_dir / "seed" / "data.json"
    if not data_path.exists():
        return []
    return json.loads(data_path.read_text(encoding="utf-8"))


def get_or_create_don_vi(name):
    name = (name or "").strip()
    if not name:
        return None
    don_vi = DonVi.query.filter_by(ten_don_vi=name).first()
    if not don_vi:
        don_vi = DonVi(ten_don_vi=name, is_active=True)
        db.session.add(don_vi)
        db.session.flush()
    return don_vi


def main():
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)

    records = load_records(ROOT_DIR)
    with app.app_context():
        db.create_all()
        for item in records:
            don_vi = get_or_create_don_vi(item.get("don_vi"))
            user = User.query.filter_by(ma_cbsv=item["ma_cbsv"]).first()
            if not user:
                user = User(ma_cbsv=item["ma_cbsv"], ho_ten=item["ho_ten"])
                db.session.add(user)
            user.ho_ten = item["ho_ten"]
            user.don_vi_id = don_vi.id if don_vi else None
            user.chuc_vu = item.get("chuc_vu")
            user.so_dien_thoai = item.get("so_dien_thoai")
            user.email = item.get("email")
        db.session.commit()
        print(f"Da nap {len(records)} ban ghi vao bang users.")


if __name__ == "__main__":
    main()
