# So do database

Du an hien dung MySQL qua Flask-SQLAlchemy va PyMySQL.

Schema chinh nam tai:

`database/schema.sql`

Database mac dinh:

`checkin_event`

## Bang chinh

- `admins`
- `don_vi`
- `users`
- `events`
- `registrations`
- `checkins`
- `certificates`
- `email_logs`

## Quan he chinh

- `users.don_vi_id` -> `don_vi.id`
- `events.created_by` -> `admins.id`
- `events.updated_by` -> `admins.id`
- `registrations.ma_cbsv` -> `users.ma_cbsv`
- `registrations.event_id` -> `events.id`
- `checkins.ma_cbsv` -> `users.ma_cbsv`
- `checkins.event_id` -> `events.id`
- `certificates.ma_cbsv` -> `users.ma_cbsv`
- `certificates.event_id` -> `events.id`
- `email_logs.ma_cbsv` -> `users.ma_cbsv`
- `email_logs.event_id` -> `events.id`

## Ghi chu

Du an khong con dung SQLite. Khong tao hoac doc `event.db` nua.
