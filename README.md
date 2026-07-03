# hanhuyen-web-event

Event Check-in / Check-in Event

Ứng dụng quản lý đăng ký, check-in và cấp chứng chỉ sự kiện sinh viên, xây dựng bằng Flask, MVC và SQLite/MySQL tuỳ cấu hình.

Kiến trúc chính:

- Backend: Flask API + SQLAlchemy
- Database: SQLite (mặc định) hoặc MySQL
- Frontend: React + Vite (tuỳ phần frontend)
- Email: Flask-Mail, gửi kèm chứng chỉ sau khi check-in

---

## Chuẩn bị database

Nếu dùng MySQL, tạo database:

```sql
CREATE DATABASE checkin_event CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

Hoặc dùng schema có sẵn:

```bash
mysql -u root -p < database/schema.sql
```

Sao chép `.env.example` thành `.env` và chỉnh `DATABASE_URL` hoặc các thông số MySQL/SMTP.

---

## Cài đặt (backend)

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Seed dữ liệu mẫu:

```bash
python seed/seed_data.py
```

Chạy ứng dụng:

```bash
python app.py
```

Backend mặc định chạy tại `http://127.0.0.1:5000`.

---

## Frontend (tuỳ dự án)

Nếu có phần frontend bằng Vite/React:

```bash
cd frontend
npm install
npm run dev
```

Build production:

```bash
cd frontend
npm run build
```

---

## API chính (tóm tắt)

- `POST /api/register`
- `POST /api/checkin`
- `GET /api/admin/summary`
- `POST /api/certificates/generate`
- `GET /api/certificates/:certificateCode`
- `GET /api/users/:ma_cbsv/certificates`

---

Mở trình duyệt tại `http://localhost:5000` sau khi server chạy.
