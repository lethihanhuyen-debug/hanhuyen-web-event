"""Migration 001: tạo bảng checkin_records và chuyển dữ liệu từ bảng checkins cũ.

Chạy tại thư mục gốc của app (nơi có app.py), bằng python của venv:

    python -m event_checkin.migrations.m001_checkin_records --dry-run   # xem trước, không ghi gì
    python -m event_checkin.migrations.m001_checkin_records             # chạy thật
    python -m event_checkin.migrations.m001_checkin_records --print-sql # in câu CREATE TABLE cho MySQL

- Bảng mới được tạo bằng db.create_all() (chỉ tạo bảng còn thiếu, không đụng bảng
  khác) -- giống cách app tự tạo bảng khi khởi động.
- Bảng `checkins` cũ được GIỮ NGUYÊN làm dự phòng, không xoá/sửa.
- Chạy lại nhiều lần vẫn an toàn: mã đã có trong bảng mới cho sự kiện đó thì bỏ qua.
- Giờ cũ lưu UTC được đổi sang giờ Việt Nam (UTC+7) khi chép sang.
- Trạng thái gửi lấy từ email_logs: lần gửi gần nhất sau lúc check-in thành công
  -> 'sent', lỗi -> 'failed', chưa có -> 'pending'.
"""
import argparse
import sys

from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateIndex, CreateTable


def _vn_naive(dt):
    from event_checkin.utils.timezone import utc_to_vn

    return utc_to_vn(dt).replace(tzinfo=None) if dt else None


def migrate(dry_run=False):
    from event_checkin.models import db
    from event_checkin.models.checkin import CheckIn
    from event_checkin.models.checkin_record import CheckinRecord
    from event_checkin.models.email_log import EmailLog
    from event_checkin.models.user import User

    db.create_all()

    existing = {
        (event_id, code)
        for event_id, code in db.session.query(CheckinRecord.event_id, CheckinRecord.patron_code).distinct()
    }

    logs_by_key = {}
    for log in (
        EmailLog.query
        .filter_by(email_type="checkin_certificate")
        .order_by(EmailLog.sent_at.asc(), EmailLog.id.asc())
        .all()
    ):
        logs_by_key.setdefault((log.event_id, log.ma_cbsv), []).append(log)

    counts = {"pending": 0, "sent": 0, "failed": 0, "skipped": 0}
    for old in CheckIn.query.order_by(CheckIn.thoi_gian_checkin.asc()).all():
        key = (old.event_id, old.ma_cbsv)
        if key in existing:
            counts["skipped"] += 1
            continue

        logs = [log for log in logs_by_key.get(key, []) if log.sent_at >= old.thoi_gian_checkin]
        latest = logs[-1] if logs else None
        successes = [log for log in logs if log.trang_thai == "success"]
        user = User.query.get(old.ma_cbsv)

        record = CheckinRecord(
            event_id=old.event_id,
            patron_code=old.ma_cbsv,
            checkin_at=_vn_naive(old.thoi_gian_checkin),
            cert_status="pending",
            send_count=len(successes),
        )
        if successes:
            record.cert_status = "sent"
            record.cert_sent_at = _vn_naive(successes[-1].sent_at)
        elif latest and latest.trang_thai == "failed":
            record.cert_status = "failed"
        if latest:
            record.patron_name = user.ho_ten if user else None
            record.patron_email = latest.email_to or None
            if latest.trang_thai == "failed":
                record.error_msg = latest.error_message

        counts[record.cert_status] += 1
        if not dry_run:
            db.session.add(record)

    if dry_run:
        db.session.rollback()
    else:
        db.session.commit()
    return counts


def print_mysql_ddl():
    from event_checkin.models.checkin_record import CheckinRecord

    table = CheckinRecord.__table__
    print(str(CreateTable(table).compile(dialect=mysql.dialect())).strip() + ";")
    for index in sorted(table.indexes, key=lambda item: item.name):
        print(str(CreateIndex(index).compile(dialect=mysql.dialect())).strip() + ";")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="chỉ đếm, không ghi vào database")
    parser.add_argument("--print-sql", action="store_true", help="in câu SQL tạo bảng cho MySQL rồi thoát")
    args = parser.parse_args()

    if args.print_sql:
        print_mysql_ddl()
        return 0

    from app import app

    with app.app_context():
        counts = migrate(dry_run=args.dry_run)

    prefix = "[DRY RUN] Sẽ chuyển" if args.dry_run else "Đã chuyển"
    total = counts["pending"] + counts["sent"] + counts["failed"]
    print(
        f"{prefix} {total} lượt check-in sang checkin_records "
        f"(sent: {counts['sent']}, failed: {counts['failed']}, pending: {counts['pending']}); "
        f"bỏ qua {counts['skipped']} lượt đã có sẵn."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
