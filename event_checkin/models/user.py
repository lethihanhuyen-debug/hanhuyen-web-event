from datetime import datetime

from event_checkin.models import db


class User(db.Model):
    __tablename__ = "users"

    ma_cbsv = db.Column(db.String(50), primary_key=True)
    ho_ten = db.Column(db.String(255), nullable=False)
    don_vi_id = db.Column(db.Integer, db.ForeignKey("don_vi.id"))
    chuc_vu = db.Column(db.String(100))
    so_dien_thoai = db.Column(db.String(20))
    email = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime)

    don_vi = db.relationship("DonVi", lazy="joined")

    @property
    def ten_don_vi(self):
        return self.don_vi.ten_don_vi if self.don_vi else ""

    def to_dict(self):
        return {
            "ma_cbsv": self.ma_cbsv,
            "ho_ten": self.ho_ten,
            "don_vi_id": self.don_vi_id,
            "don_vi": self.ten_don_vi,
            "chuc_vu": self.chuc_vu,
            "so_dien_thoai": self.so_dien_thoai,
            "email": self.email,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
