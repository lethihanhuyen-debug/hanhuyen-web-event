from datetime import datetime

from event_checkin.models import db

STATUS_ACTIVE = "active"
STATUS_CANCELLED = "cancelled"


class Registration(db.Model):
    """Một lượt đăng ký (mã CB/SV, sự kiện). Mỗi mã chỉ có 1 dòng cho 1 sự kiện (UNIQUE).

    Xóa đăng ký là xóa MỀM (m009): trang_thai = 'cancelled' + giờ/người/lý do hủy. Người đã hủy không hiện trong danh
    sách, xuất Excel, check-in, gửi chứng chỉ, quay số và không chiếm chỗ (mọi chỗ đọc đăng ký dùng
    Registration.active()). Đăng ký lại hoặc admin khôi phục thì dùng lại chính dòng này."""

    __tablename__ = "registrations"
    __table_args__ = (
        db.UniqueConstraint("ma_cbsv", "event_id", name="uq_registrations_user_event"),
        db.Index("ix_registrations_event_status", "event_id", "trang_thai"),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    ma_cbsv = db.Column(db.String(50), db.ForeignKey("users.ma_cbsv"), nullable=False, index=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=False, index=True)
    thoi_gian_dang_ky = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    cau_hoi = db.Column(db.Text)  # câu hỏi gửi diễn giả (m005); NULL/rỗng = không hỏi, tối đa 1000 ký tự (kiểm tra ở server)
    # ---- Hủy đăng ký (m009) ----
    trang_thai = db.Column(db.String(20), nullable=False, default=STATUS_ACTIVE, server_default=STATUS_ACTIVE)
    huy_luc = db.Column(db.DateTime)                                  # giờ Việt Nam (now_vn_naive)
    huy_boi = db.Column(db.Integer, db.ForeignKey("admins.id"))
    ly_do_huy = db.Column(db.String(500))
    chan_dang_ky_lai = db.Column(db.Boolean, nullable=False, default=False, server_default="0")

    user = db.relationship("User", lazy="joined")
    event = db.relationship("Event", lazy="joined")
    cancelled_by = db.relationship("Admin", lazy="select", foreign_keys=[huy_boi])

    @classmethod
    def active(cls):
        """Query chỉ gồm đăng ký còn hiệu lực -- dùng cho MỌI chỗ đếm/liệt kê/kiểm tra đã đăng ký."""
        return cls.query.filter(cls.trang_thai == STATUS_ACTIVE)

    @classmethod
    def checkin_not_cancelled(cls):
        """Điều kiện cho query CheckinRecord: bỏ dòng check-in của người đã bị hủy đăng ký sự kiện đó. Dòng check-in
        vẫn giữ trong DB (khôi phục đăng ký thì tính lại), chỉ không hiện/không gửi chứng chỉ/không quay số."""
        from event_checkin.models.checkin_record import CheckinRecord

        return ~db.exists().where(
            cls.ma_cbsv == CheckinRecord.patron_code,
            cls.event_id == CheckinRecord.event_id,
            cls.trang_thai == STATUS_CANCELLED,
        )

    @property
    def is_active(self):
        return self.trang_thai == STATUS_ACTIVE

    def mark_cancelled(self, admin_id, reason, block, at):
        self.trang_thai = STATUS_CANCELLED
        self.huy_luc = at
        self.huy_boi = admin_id
        self.ly_do_huy = reason or None
        self.chan_dang_ky_lai = bool(block)

    def mark_active(self):
        self.trang_thai = STATUS_ACTIVE
        self.huy_luc = None
        self.huy_boi = None
        self.ly_do_huy = None
        self.chan_dang_ky_lai = False

    def to_dict(self):
        return {
            "id": self.id,
            "ma_cbsv": self.ma_cbsv,
            "event_id": self.event_id,
            "ho_ten": self.user.ho_ten if self.user else "",
            "don_vi": self.user.ten_don_vi if self.user else "",
            "email": self.user.email if self.user else "",
            "thoi_gian_dang_ky": self.thoi_gian_dang_ky.isoformat() if self.thoi_gian_dang_ky else None,
            "trang_thai": self.trang_thai,
        }
