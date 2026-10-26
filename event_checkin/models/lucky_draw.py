from event_checkin.models import db
from event_checkin.utils.timezone import now_vn_naive


WINNER_STATUSES = ("pending", "confirmed", "cancelled")


class LuckyConfig(db.Model):
    """Cấu hình quay số của 1 sự kiện (mỗi sự kiện tối đa 1 dòng, tạo khi truy cập lần đầu).
    Dòng này cũng là dòng bị khoá (SELECT ... FOR UPDATE) mỗi khi quay/lưu/huỷ, để hai tab
    hay hai admin bấm cùng lúc không sinh kết quả đúp -- xem controllers/lucky_draw_controller.py."""

    __tablename__ = "lucky_configs"

    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), primary_key=True)
    cho_phep_trung_nhieu_giai = db.Column(db.Boolean, nullable=False, default=False)
    # Đường dẫn ảnh nền màn hình quay (tương đối so với thư mục static); NULL = dùng ảnh mặc định.
    hinh_nen = db.Column(db.String(255))


class LuckyPrize(db.Model):
    __tablename__ = "lucky_prizes"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=False, index=True)
    ten_giai = db.Column(db.String(255), nullable=False)
    so_luong = db.Column(db.Integer, nullable=False, default=1)
    thu_tu = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=now_vn_naive)


class LuckyWinner(db.Model):
    """Một lượt trúng giải. trang_thai: pending (đã quay, chờ Lưu) / confirmed (đã lưu) /
    cancelled (vắng mặt, giữ lại để đối chiếu). `hieu_luc` = 1 khi còn hiệu lực, NULL khi đã
    huỷ -- để UNIQUE chỉ áp cho dòng còn hiệu lực (MySQL cho phép nhiều NULL), nhờ đó người
    bị huỷ vẫn được quay lại vào cùng giải."""

    __tablename__ = "lucky_winners"
    __table_args__ = (
        db.UniqueConstraint("event_id", "prize_id", "patron_code", "hieu_luc", name="uq_lucky_winner_active"),
        db.Index("ix_lucky_winners_event_status", "event_id", "trang_thai"),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=False)
    prize_id = db.Column(db.Integer, db.ForeignKey("lucky_prizes.id"), nullable=False)
    patron_code = db.Column(db.String(50), nullable=False)
    ho_ten = db.Column(db.String(255))
    trang_thai = db.Column(db.String(20), nullable=False, default="pending")
    trung_luc = db.Column(db.DateTime, nullable=False, default=now_vn_naive)
    huy_luc = db.Column(db.DateTime)
    hieu_luc = db.Column(db.SmallInteger, default=1)

    prize = db.relationship("LuckyPrize", lazy="joined")
