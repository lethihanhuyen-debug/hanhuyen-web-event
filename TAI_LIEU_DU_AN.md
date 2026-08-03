# Tài liệu tổng hợp dự án — Event Check-in & Chứng chỉ (USSH)

> Tài liệu này tổng hợp chức năng và cơ sở dữ liệu của dự án, được tạo ra bằng cách đọc toàn bộ mã nguồn.

## 1. Tổng quan dự án

Ứng dụng Flask quản lý **đăng ký sự kiện – điểm danh (check-in) – cấp chứng chỉ tự động** cho Trường Đại học Khoa học Xã hội và Nhân văn (ĐHQG-HCM).

**Stack công nghệ**:
- Backend: Flask + Flask-SQLAlchemy (MySQL qua PyMySQL)
- Email: Flask-Mail
- Sinh chứng chỉ: Pillow (vẽ text lên ảnh nền → PDF/PNG), có fallback SVG
- Giao diện: Jinja2 templates (server-rendered) cho trang admin/công khai
- Có thêm một bản giao diện thiết kế chứng chỉ song song bằng React (`frontend/src/CertificateLayoutDesigner.jsx`), độc lập với bản vanilla JS nhúng trong `admin/index.html`

### Cấu trúc thư mục chính

```
app.py                     # application factory, tự tạo/vá schema, seed admin & event mặc định
config.py                  # cấu hình từ biến môi trường (.env)
database/schema.sql        # schema SQL chuẩn (MySQL)
event_checkin/
  models/                  # các model SQLAlchemy (1 file/bảng)
  controllers/             # blueprint Flask: admin, certificate, checkin, register
  certificates/            # logic sinh chứng chỉ (service.py, generator.py, fonts.py, validators.py)
  utils/email_service.py   # gửi email qua Flask-Mail
  views/                   # templates Jinja2 (admin, register, checkin, certificates/verify)
  static/                  # css/js, events/ (ảnh sự kiện), certificates/{templates,fonts,generated}
frontend/                  # bản React song song cho trình thiết kế chứng chỉ
seed/                      # seed_data.py + data.json để nạp dữ liệu users/don_vi ban đầu
```

## 2. Cơ sở dữ liệu (MySQL, database `checkin_event`)

8 bảng, khớp giữa `database/schema.sql` và các model SQLAlchemy trong `event_checkin/models/`.

### `admins` — tài khoản quản trị
| Cột | Kiểu | Ghi chú |
|---|---|---|
| id | INT PK, auto increment | |
| username | VARCHAR(100) | UNIQUE, NOT NULL |
| password_hash | VARCHAR(255) | NOT NULL |
| role | VARCHAR(50) | `super_admin` \| `admin` |
| is_active | BOOLEAN | mặc định TRUE |
| created_by | INT | FK → `admins.id` (tự tham chiếu, ON DELETE SET NULL) |
| created_at | DATETIME | NOT NULL |
| updated_at | DATETIME | nullable |

### `don_vi` — đơn vị / khoa
| Cột | Kiểu | Ghi chú |
|---|---|---|
| id | INT PK, auto increment | |
| ten_don_vi | VARCHAR(255) | UNIQUE, NOT NULL |
| is_active | BOOLEAN | mặc định TRUE (dùng để xóa mềm) |

### `users` — cán bộ / sinh viên
| Cột | Kiểu | Ghi chú |
|---|---|---|
| ma_cbsv | VARCHAR(50) PK | mã CB/SV, không auto-increment |
| ho_ten | VARCHAR(255) | NOT NULL |
| don_vi_id | INT | FK → `don_vi.id`, ON DELETE SET NULL |
| chuc_vu | VARCHAR(100) | chức vụ |
| so_dien_thoai | VARCHAR(20) | |
| email | VARCHAR(255) | |
| created_at / updated_at | DATETIME | |

### `events` — sự kiện
| Cột | Kiểu | Ghi chú |
|---|---|---|
| id | INT PK, auto increment | |
| ten_su_kien | VARCHAR(255) | NOT NULL |
| hinh | VARCHAR(255) | đường dẫn ảnh sự kiện |
| mo_ta | TEXT | mô tả |
| dia_diem | VARCHAR(255) | địa điểm |
| ngay_bat_dau / ngay_ket_thuc | DATETIME | NOT NULL |
| thang, nam | INT | NOT NULL, suy ra từ ngày bắt đầu |
| thoi_gian_mo_dang_ky / thoi_gian_dong_dang_ky | DATETIME | NOT NULL |
| trang_thai | VARCHAR(50) | mặc định `upcoming`; `upcoming\|ongoing\|closed` |
| certificate_enabled | BOOLEAN | mặc định TRUE |
| certificate_template | VARCHAR(255) | đường dẫn ảnh mẫu chứng chỉ đã upload |
| certificate_layout | TEXT | JSON mô tả vị trí/font từng trường trên chứng chỉ |
| created_by / updated_by | INT | FK → `admins.id` |
| created_at / updated_at | DATETIME | |

> `app.py` có hàm `ensure_schema_upgrades()` tự chạy `ALTER TABLE` (idempotent) để thêm 3 cột chứng chỉ ở trên nếu database cũ chưa có — dự án không dùng Alembic/migration chính thức.

### `registrations` — đăng ký tham dự
| Cột | Kiểu | Ghi chú |
|---|---|---|
| id | INT PK, auto increment | |
| ma_cbsv | VARCHAR(50) | FK → `users.ma_cbsv`, NOT NULL, indexed |
| event_id | INT | FK → `events.id`, NOT NULL, indexed |
| thoi_gian_dang_ky | DATETIME | NOT NULL |
| UNIQUE (ma_cbsv, event_id) | | mỗi người chỉ đăng ký 1 lần / sự kiện |

### `checkins` — điểm danh
| Cột | Kiểu | Ghi chú |
|---|---|---|
| id | INT PK, auto increment | |
| ma_cbsv | VARCHAR(50) | FK → `users.ma_cbsv`, NOT NULL, indexed |
| event_id | INT | FK → `events.id`, NOT NULL, indexed |
| thoi_gian_checkin | DATETIME | NOT NULL |
| UNIQUE (ma_cbsv, event_id) | | mỗi người chỉ check-in 1 lần / sự kiện |

### `certificates` — chứng chỉ đã cấp
| Cột | Kiểu | Ghi chú |
|---|---|---|
| id | INT PK, auto increment | |
| ma_cbsv | VARCHAR(50) | FK → `users.ma_cbsv`, NOT NULL, indexed |
| event_id | INT | FK → `events.id`, NOT NULL, mặc định 1, indexed |
| certificate_code | VARCHAR(100) | UNIQUE, NOT NULL — dạng `USSH-{năm}-EVENT{event_id:03d}-{seq:06d}` |
| file_url | VARCHAR(255) | URL công khai của file đã sinh |
| file_type | VARCHAR(20) | `pdf` \| `png` \| `svg` |
| status | VARCHAR(50) | mặc định `generated` |
| issued_at / created_at | DATETIME | |
| UNIQUE (ma_cbsv, event_id) | | mỗi người chỉ có 1 chứng chỉ / sự kiện |

### `email_logs` — nhật ký gửi email
| Cột | Kiểu | Ghi chú |
|---|---|---|
| id | INT PK, auto increment | |
| ma_cbsv | VARCHAR(50) | FK → `users.ma_cbsv`, NOT NULL, indexed |
| event_id | INT | FK → `events.id`, NOT NULL, indexed |
| email_to | VARCHAR(255) | NOT NULL |
| email_type | VARCHAR(50) | mặc định `checkin_certificate` |
| subject | VARCHAR(255) | NOT NULL |
| certificate_code | VARCHAR(100) | FK → `certificates.certificate_code`, ON DELETE SET NULL |
| attachment_path | VARCHAR(255) | nullable |
| trang_thai | VARCHAR(20) | `success` \| `failed` |
| error_message | TEXT | nullable |
| sent_at | DATETIME | NOT NULL |

### Sơ đồ quan hệ (tóm tắt)
```
admins ──(created_by, tự tham chiếu)──> admins
don_vi ──< users
admins ──< events (created_by, updated_by)
users ──< registrations >── events
users ──< checkins >── events
users ──< certificates >── events
users ──< email_logs >── events
certificates ──< email_logs (certificate_code)
```

> Ghi chú: `event_checkin/database/event.db` (SQLite) còn tồn tại trên đĩa nhưng là artifact cũ không còn dùng — MySQL (`SQLALCHEMY_DATABASE_URI` trong `config.py`) mới là nguồn dữ liệu chính thức.

## 3. Chức năng theo module (Blueprint)

### 3.1 trang chủ công khai — `register_bp`
- `GET /` — trang chủ, danh sách sự kiện.
- `GET /events/<event_id>/register` — trang đăng ký cho một sự kiện cụ thể.
- `GET /api/lookup/<ma_cbsv>` — tra cứu sự kiện theo tên.t
- `GET /api/events` — danh sách sự kiện (JSON công khai).
- `GET /api/don-vi` — danh sách đơn vị đang hoạt động (JSON).
- `POST /register` / `POST /api/register` — đăng ký tham dự: tạo/cập nhật `User`, tự tạo `DonVi` mới nếu chưa có, validate email, chặn đăng ký trùng (unique ma_cbsv + event_id).

### 3.2 Điểm danh — `checkin_bp`
- `GET /checkin` — điều hướng về `/admin`.
- `POST /api/checkin` — luồng điểm danh chính:
  1. Kiểm tra `ma_cbsv` tồn tại và đã đăng ký sự kiện.
  2. Nếu đã check-in rồi → trả thông báo kèm thời gian đã check-in trước đó.
  3. Nếu chưa → tạo bản ghi `CheckIn`, **tự sinh chứng chỉ PDF**, gửi email xác nhận kèm chứng chỉ, ghi log vào `email_logs`.
  - Không có quét QR bằng camera thực sự — ô nhập mã hoạt động như đầu đọc mã vạch (gõ bàn phím).

### 3.3 Quản trị — `admin_bp` (yêu cầu đăng nhập qua session, decorator `admin_required`)

**Xác thực**
- `GET /admin/login`, `POST /api/admin/login` (kiểm tra mật khẩu bằng `werkzeug.security`, hỗ trợ "ghi nhớ đăng nhập"), `POST /api/admin/logout`, `GET /api/admin/me`.

**Dashboard**
- `GET /admin` — trang quản trị chính (danh sách sự kiện + form thêm/sửa + trình thiết kế chứng chỉ).
- `GET /admin/events/<event_id>` — chi tiết 1 sự kiện: danh sách đăng ký/điểm danh/chứng chỉ.
- `GET /api/admin/summary` — số liệu tổng hợp (tổng đăng ký, check-in hôm nay, số chứng chỉ, số sự kiện...).
- `GET /api/admin/events` — danh sách sự kiện (JSON cho admin).

**CRUD đơn vị**
- `GET/POST /api/admin/don-vi`, `PUT/PATCH /api/admin/don-vi/<id>`, `DELETE /api/admin/don-vi/<id>` (xóa mềm bằng `is_active=False`).

**CRUD sự kiện & hình ảnh**
- `POST /api/admin/events` — tạo sự kiện (kiểm tra thứ tự ngày hợp lệ).
- `PUT/PATCH /api/admin/events/<id>` — cập nhật sự kiện.
- `DELETE /api/admin/events/<id>` — xóa sự kiện (chặn nếu đã có đăng ký/check-in/chứng chỉ/email log, trả lỗi 409).
- `POST /api/admin/events/<id>/image` — upload ảnh bìa sự kiện (png/jpg/jpeg/webp).

**Thiết kế mẫu chứng chỉ (canvas)**
- `POST /api/admin/events/<id>/certificate-template` — upload ảnh nền chứng chỉ.
- `GET /api/admin/events/<id>/certificate-layout` — lấy layout hiện tại (kèm `font_url` từng trường).
- `POST /api/admin/events/<id>/certificate-layout` — lưu layout JSON: vị trí `x`, `y`, căn lề (`align`), cỡ chữ (`size`, 10–200), màu (`color`, hex), `bold` cho từng trường (`student_name`, `ma_cbsv`, `don_vi`, `issue_date`, `certificate_code`) + `_meta` (kích thước canvas thiết kế để scale đúng tỉ lệ).
- `POST /api/admin/events/<id>/certificate-font` — upload font riêng (.ttf/.otf) cho từng trường.
- `DELETE /api/admin/events/<id>/certificate-font/<field>` — xóa font riêng của 1 trường.

**Quản lý điểm danh / báo cáo**
- `DELETE /api/admin/events/<id>/checkins/<ma_cbsv>` — xóa 1 lượt check-in (kèm xóa chứng chỉ đã sinh và email log liên quan).
- `GET /admin/export/csv` — xuất CSV đăng ký/điểm danh trong ngày.
- `POST /admin/reset` — xóa toàn bộ dữ liệu demo (`email_logs`, `certificates`, `checkins`, `registrations`), yêu cầu `confirm=true`.

### 3.4 Chứng chỉ — `certificate_bp`
- `POST /api/certificates/generate` (chỉ admin) — sinh lại chứng chỉ thủ công cho 1 người/sự kiện, chọn `file_type` (mặc định `pdf`).
- `GET /api/certificates/<certificate_code>` — render lại (idempotent) và tải PDF dạng attachment.
- `GET /api/certificates/<certificate_code>/view` — xem trực tiếp (inline), dùng để xem trước.
- `GET /api/users/<ma_cbsv>/certificates` — danh sách chứng chỉ của 1 người dùng.
- `GET /verify/<certificate_code>` — trang xác thực chứng chỉ công khai.

## 4. Các chức năng khác đáng chú ý

- **Pipeline sinh chứng chỉ** (`event_checkin/certificates/`):
  - `service.py`: sinh mã chứng chỉ tuần tự, kiểm tra điều kiện (phải đã đăng ký VÀ đã check-in), lưu file dưới `static/certificates/generated/<năm>/`, sinh lại (ghi đè) mỗi lần tải/generate.
  - `generator.py`: dùng Pillow vẽ chữ lên ảnh mẫu theo tọa độ đã scale từ canvas thiết kế sang kích thước ảnh thật; hỗ trợ font riêng, màu, in đậm, căn lề. Có fallback SVG tĩnh (`save_svg_certificate`) chỉ dùng khi Pillow lỗi.
  - `resolve_font`: thử font upload riêng → font Roboto có sẵn → font hệ thống Windows (Arial) → DejaVu.
  - Bắt buộc phải có ảnh mẫu do admin upload; nếu chưa có sẽ báo lỗi khi sinh chứng chỉ.
- **Trình thiết kế chứng chỉ (canvas)**: bản chính là JS thuần nhúng trong `admin/index.html` (kéo-thả đặt vị trí, resize bằng góc, nút xóa từng trường, có modal crop ảnh về đúng tỉ lệ 2000×1414). Có bản React song song ở `frontend/src/CertificateLayoutDesigner.jsx`.
- **Gửi email**: qua Flask-Mail, đính kèm chứng chỉ + link xác thực, ghi log mọi lần gửi (thành công/thất bại + lỗi) vào `email_logs`.
- **Xác thực quản trị**: session-based, mật khẩu hash bằng `werkzeug.security`, decorator `admin_required` chặn `/admin/*` và `/api/admin/*`. Không thấy cơ chế CSRF token.
- **Validate upload**: ảnh giới hạn `.png/.jpg/.jpeg/.webp`; font giới hạn `.ttf/.otf`; tên file được làm sạch qua `secure_filename`.
- **CORS**: `app.py` cấu hình CORS theo `FRONTEND_ORIGIN` cho frontend React riêng; header no-cache cho mọi route `/admin`.
- **Tự quản lý schema**: không dùng Alembic — `db.create_all()` + `ensure_schema_upgrades()` (ALTER TABLE thủ công) + `ensure_default_records()` (tạo admin mặc định từ `ADMIN_DEFAULT_USERNAME`/`PASSWORD` và sự kiện mặc định id=1 nếu chưa có).
- **Biến môi trường chính** (`config.py`, `.env.example`): `SECRET_KEY`, `MYSQL_HOST/PORT/USER/PASSWORD/DATABASE`, `FRONTEND_ORIGIN`, `ADMIN_DEFAULT_USERNAME/PASSWORD`, `REMEMBER_LOGIN_DAYS`, `MAIL_SERVER/PORT/USERNAME/PASSWORD/USE_TLS/USE_SSL/SENDER/DEFAULT_SENDER`.
- **Seed dữ liệu**: `seed/seed_data.py` nạp `seed/data.json` (ma_cbsv, ho_ten, don_vi, chuc_vu, so_dien_thoai, email) vào bảng `users`/`don_vi`, độc lập với app chính.
- **Không có quét QR bằng camera** — mặc dù giao diện có chữ "Quét hoặc nhập mã CB/SV", thực chất chỉ là ô nhập text, tương thích với máy quét mã vạch kiểu bàn phím ảo (keyboard-wedge).
