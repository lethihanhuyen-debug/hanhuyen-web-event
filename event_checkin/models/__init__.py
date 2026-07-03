from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()

from event_checkin.models.admin import Admin  # noqa: E402,F401
from event_checkin.models.certificate import Certificate  # noqa: E402,F401
from event_checkin.models.checkin import CheckIn  # noqa: E402,F401
from event_checkin.models.don_vi import DonVi  # noqa: E402,F401
from event_checkin.models.email_log import EmailLog  # noqa: E402,F401
from event_checkin.models.event import Event  # noqa: E402,F401
from event_checkin.models.registration import Registration  # noqa: E402,F401
from event_checkin.models.user import User  # noqa: E402,F401
