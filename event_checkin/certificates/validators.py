from event_checkin.models.checkin import CheckIn
from event_checkin.models.registration import Registration


def find_registration(ma_cbsv, event_id=1):
    return Registration.query.filter_by(ma_cbsv=ma_cbsv, event_id=event_id).first()


def has_successful_checkin(registration):
    if not registration:
        return False
    return CheckIn.query.filter_by(
        ma_cbsv=registration.ma_cbsv,
        event_id=registration.event_id,
    ).first() is not None


def validate_certificate_eligibility(ma_cbsv, event_id=1):
    registration = find_registration(ma_cbsv, event_id)
    if not registration:
        return False, "Mã CB/SV chưa đăng ký sự kiện này.", None
    if not has_successful_checkin(registration):
        return False, "Mã CB/SV chưa check-in thành công.", registration
    return True, "", registration
