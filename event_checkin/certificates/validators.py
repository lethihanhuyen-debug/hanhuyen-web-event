from event_checkin.models.checkin import CheckIn
from event_checkin.models.registration import Registration


def find_registration(ma_cbsv):
    return Registration.query.filter_by(ma_cbsv=ma_cbsv).first()


def has_successful_checkin(registration):
    if not registration:
        return False
    return CheckIn.query.filter_by(registration_id=registration.id).first() is not None


def validate_certificate_eligibility(ma_cbsv):
    registration = find_registration(ma_cbsv)
    if not registration:
        return False, "Ma CB/SV chua dang ky tham gia chuong trinh.", None
    if not has_successful_checkin(registration):
        return False, "Ma CB/SV chua check-in thanh cong.", registration
    return True, "", registration
