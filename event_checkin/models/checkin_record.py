from event_checkin.models import db
from event_checkin.utils.timezone import now_vn_naive


CERT_STATUSES = ("pending", "sent", "failed", "duplicate")


class CheckinRecord(db.Model):
    """Mỗi lượt quét check-in là 1 dòng -- cố ý KHÔNG có UNIQUE(event_id, patron_code)
    để check-in chỉ là 1 câu INSERT, không bao giờ bị chặn/đụng khoá vì quét trùng.
    Dòng trùng được xử lý lúc admin gửi chứng chỉ (cert_status = 'duplicate',
    xem certificates/mailer.py).

    Khác bảng `checkins` cũ: mọi cột thời gian ở đây lưu GIỜ VIỆT NAM (UTC+7,
    naive, lấy từ server qua now_vn_naive()), không phải UTC -- hiển thị bằng
    format_local(), KHÔNG dùng format_utc_as_vn().
    """

    __tablename__ = "checkin_records"
    __table_args__ = (
        db.Index("ix_checkin_records_event_patron", "event_id", "patron_code"),
        db.Index("ix_checkin_records_event_status", "event_id", "cert_status"),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=False)
    # Không ràng buộc khoá ngoại sang users: sau này tra Sierra thì người chưa
    # đăng ký trên web vẫn check-in được.
    patron_code = db.Column(db.String(50), nullable=False)
    checkin_at = db.Column(db.DateTime, nullable=False, default=now_vn_naive)
    cert_status = db.Column(db.String(20), nullable=False, default="pending")
    patron_name = db.Column(db.String(255))
    patron_email = db.Column(db.String(255))
    cert_sent_at = db.Column(db.DateTime)
    send_count = db.Column(db.Integer, nullable=False, default=0)
    error_msg = db.Column(db.Text)
    # Họ tên admin sửa tay để in lên chứng chỉ (tên quá dài, sai dấu...). Ưu tiên hơn
    # tên từ Sierra/đăng ký -- xem certificates/service.resolve_display_name().
    cert_display_name = db.Column(db.String(255))
    # Email admin nhập tay cho dòng gửi lỗi (vd. Sierra không có email). Ưu tiên hơn
    # email tra được -- xem certificates/mailer.py.
    email_override = db.Column(db.String(255))

    event = db.relationship("Event", lazy="select")
