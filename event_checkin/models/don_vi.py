from event_checkin.models import db


class DonVi(db.Model):
    __tablename__ = "don_vi"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    ten_don_vi = db.Column(db.String(255), unique=True, nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    def to_dict(self):
        return {
            "id": self.id,
            "ten_don_vi": self.ten_don_vi,
            "is_active": self.is_active,
        }
