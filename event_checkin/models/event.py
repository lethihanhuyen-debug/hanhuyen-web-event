from datetime import datetime, timedelta

from flask import current_app

from event_checkin.models import db
from event_checkin.utils.timezone import now_vn_naive


class Event(db.Model):
    __tablename__ = "events"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    ten_su_kien = db.Column(db.String(255), nullable=False)
    hinh = db.Column(db.String(255))
    mo_ta = db.Column(db.Text)
    dia_diem = db.Column(db.String(255))
    co_so = db.Column(db.String(50))  # "Thủ Đức" | "Đinh Tiên Hoàng" | "Khác" -- dùng để lọc, khác với dia_diem (phòng/hội trường cụ thể)
    so_luong_toi_da = db.Column(db.Integer)  # số người tối đa được đăng ký -- None nghĩa là không giới hạn
    ngay_bat_dau = db.Column(db.DateTime, nullable=False)
    ngay_ket_thuc = db.Column(db.DateTime, nullable=False)
    thang = db.Column(db.Integer, nullable=False)
    nam = db.Column(db.Integer, nullable=False)
    thoi_gian_mo_dang_ky = db.Column(db.DateTime, nullable=False)
    thoi_gian_dong_dang_ky = db.Column(db.DateTime, nullable=False)
    trang_thai = db.Column(db.String(50), nullable=False, default="upcoming")
    certificate_enabled = db.Column(db.Boolean, nullable=False, default=True)
    certificate_template = db.Column(db.String(255))
    certificate_layout = db.Column(db.Text)
    # Ô "câu hỏi" tuỳ chọn ở form đăng ký (m005): công tắc theo từng sự kiện + tiêu đề admin tự đặt
    cho_phep_cau_hoi = db.Column(db.Boolean, nullable=False, default=False)
    tieu_de_cau_hoi = db.Column(db.String(255))
    created_by = db.Column(db.Integer, db.ForeignKey("admins.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime)
    # Ai sửa gần nhất (m006); NULL với sự kiện chưa từng sửa sau khi có phân quyền.
    updated_by = db.Column(db.Integer, db.ForeignKey("admins.id"))

    DEFAULT_QUESTION_TITLE = "Câu hỏi bạn muốn gửi đến diễn giả"

    @property
    def question_title(self):
        """Tiêu đề hiển thị của ô câu hỏi: admin tự đặt, trống thì dùng mặc định."""
        return (self.tieu_de_cau_hoi or "").strip() or self.DEFAULT_QUESTION_TITLE

    @property
    def computed_status(self):
        """Live event status derived from the schedule, not the stored `trang_thai`
        column (which is only a best-effort snapshot) -- always reflects "now".
        """
        now = now_vn_naive()
        if now < self.ngay_bat_dau:
            return "upcoming"
        if now <= self.ngay_ket_thuc:
            return "ongoing"
        return "ended"

    @staticmethod
    def _clock_label(moment):
        """"HH:mm" nếu cùng ngày hôm nay, ngược lại "HH:mm dd/mm/YYYY" (giờ Việt Nam)."""
        label = moment.strftime("%H:%M")
        if moment.date() != now_vn_naive().date():
            label += " " + moment.strftime("%d/%m/%Y")
        return label

    @property
    def checkin_deadline(self):
        """Mốc cuối staff còn check-in được = giờ kết thúc + CHECKIN_GRACE_HOURS (config.py)."""
        hours = current_app.config.get("CHECKIN_GRACE_HOURS", 2)
        return self.ngay_ket_thuc + timedelta(hours=hours)

    @property
    def checkin_state(self):
        """Trạng thái check-in cho staff, MỘT quy tắc dùng chung cho server và giao diện:
        'upcoming' chưa bắt đầu | 'open' đang diễn ra | 'grace' đã kết thúc nhưng còn trong thời gian cho phép |
        'closed' quá mốc, chỉ admin thêm tay."""
        now = now_vn_naive()
        if now < self.ngay_bat_dau:
            return "upcoming"
        if now <= self.ngay_ket_thuc:
            return "open"
        if now <= self.checkin_deadline:
            return "grace"
        return "closed"

    @property
    def ended_label(self):
        return self._clock_label(self.ngay_ket_thuc)

    @property
    def checkin_deadline_label(self):
        return self._clock_label(self.checkin_deadline)

    @property
    def started_label(self):
        return self._clock_label(self.ngay_bat_dau)

    @property
    def registration_count(self):
        """Số người đã đăng ký (số dòng Registration, mỗi mã CB/SV chỉ đăng ký
        được 1 lần cho 1 sự kiện nhờ unique constraint -- xem models/registration.py).
        Import cục bộ để tránh phụ thuộc vòng giữa event.py và registration.py."""
        from event_checkin.models.registration import Registration
        return Registration.query.filter_by(event_id=self.id).count()

    @property
    def registration_block_reason(self):
        """None if registration is currently allowed, otherwise a Vietnamese
        message explaining why (event ended / registration window not open)."""
        if self.computed_status == "ended":
            return "Sự kiện đã kết thúc, không thể đăng ký."
        now = now_vn_naive()
        if now < self.thoi_gian_mo_dang_ky:
            return "Chưa đến thời gian mở đăng ký cho sự kiện này."
        if now > self.thoi_gian_dong_dang_ky:
            return "Đã hết thời gian đăng ký cho sự kiện này."
        if self.so_luong_toi_da and self.registration_count >= self.so_luong_toi_da:
            return "Sự kiện đã đủ số lượng đăng ký."
        return None

    @property
    def is_registration_open(self):
        return self.registration_block_reason is None
