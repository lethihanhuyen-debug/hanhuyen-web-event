from event_checkin.models import db


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    ma_cbsv = db.Column(db.String(50), unique=True, nullable=False, index=True)
    ho_ten = db.Column(db.String(255), nullable=False)
    don_vi = db.Column(db.String(255))
    chuc_vu = db.Column(db.String(255))
    so_dien_thoai = db.Column(db.String(50))
    email = db.Column(db.String(255))

    def to_dict(self):
        return {
            "id": self.id,
            "ma_cbsv": self.ma_cbsv,
            "ho_ten": self.ho_ten,
            "don_vi": self.don_vi,
            "chuc_vu": self.chuc_vu,
            "so_dien_thoai": self.so_dien_thoai,
            "email": self.email,
        }
