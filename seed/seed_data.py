import json
import sys
from pathlib import Path

from flask import Flask

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import Config
from event_checkin.models import db
from event_checkin.models.user import User


def load_records(base_dir):
    data_path = base_dir / "seed" / "data.json"
    if not data_path.exists():
        return []
    return json.loads(data_path.read_text(encoding="utf-8"))


def main():
    base_dir = ROOT_DIR
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)

    records = load_records(base_dir)
    with app.app_context():
        db.create_all()
        db.session.query(User).delete()
        for item in records:
            db.session.add(User(**item))
        db.session.commit()
        print(f"Da nap {len(records)} ban ghi vao bang users.")


if __name__ == "__main__":
    main()
