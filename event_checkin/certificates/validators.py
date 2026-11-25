from event_checkin.models.checkin_record import CheckinRecord
from event_checkin.models.registration import Registration


def find_registration(ma_cbsv, event_id=1):
    # Đăng ký đã hủy coi như chưa đăng ký: không tạo/gửi chứng chỉ (dù còn dòng check-in cũ)
    return Registration.active().filter_by(ma_cbsv=ma_cbsv, event_id=event_id).first()


def has_successful_checkin(registration):
    if not registration:
        return False
    return CheckinRecord.query.filter_by(
        patron_code=registration.ma_cbsv,
        event_id=registration.event_id,
    ).first() is not None


def validate_certificate_eligibility(ma_cbsv, event_id=1):
    registration = find_registration(ma_cbsv, event_id)
    if not registration:
        return False, "Mã CB/SV chưa đăng ký sự kiện này.", None
    if not has_successful_checkin(registration):
        return False, "Mã CB/SV chưa check-in thành công.", registration
    return True, "", registration
