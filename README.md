# Event Check-in & Chứng chỉ

Web quản lý đăng ký sự kiện, check-in và cấp chứng chỉ tự động, xây dựng bằng Flask + MySQL.

## Lưu ý về cấu trúc repo

Nhánh `main` của repo này **chỉ chứa thư mục `event_checkin/`** (controllers, models, views, static, certificates, utils) — tức phần mã nguồn chính của ứng dụng Flask. Hai file khởi chạy `app.py` và `config.py`, cùng với file `.env` chứa cấu hình (DB, SMTP...), **không nằm trong repo này** — bạn cần có sẵn 2 file đó ở thư mục cha của `event_checkin/` (ngang hàng với nó) để chạy được ứng dụng. Nếu clone repo về máy mới hoàn toàn, bạn cần tự thêm lại `app.py`/`config.py`/`.env` trước khi chạy.

## Yêu cầu

- Python 3.10+
- MySQL 8.0+ đang chạy
- Các gói Python: `flask`, `flask-sqlalchemy`, `flask-mail`, `flask-wtf`, `python-dotenv`, `Pillow`, `PyMySQL`

## Cài đặt & chạy

1. **Tạo database rỗng** (chưa cần tạo bảng — app tự tạo bảng khi khởi động lần đầu):
   ```sql
   CREATE DATABASE IF NOT EXISTS checkin_event
     CHARACTER SET utf8mb4
     COLLATE utf8mb4_unicode_ci;
   ```

2. **Tạo file `.env`** ở thư mục gốc (ngang hàng `event_checkin/`), tham khảo các biến sau:
   ```env
   SECRET_KEY=doi-thanh-chuoi-bi-mat-cua-ban
   MYSQL_HOST=127.0.0.1
   MYSQL_PORT=3306
   MYSQL_USER=root
   MYSQL_PASSWORD=mat-khau-mysql
   MYSQL_DATABASE=checkin_event

   MAIL_SERVER=smtp.gmail.com
   MAIL_PORT=587
   MAIL_USERNAME=email-gui@gmail.com
   MAIL_PASSWORD=app-password-cua-gmail
   MAIL_USE_TLS=true
   MAIL_USE_SSL=false
   MAIL_SENDER=email-gui@gmail.com

   ADMIN_DEFAULT_USERNAME=admin
   ADMIN_DEFAULT_PASSWORD=admin123
   ```
   Nếu không cấu hình `MAIL_USERNAME`/`MAIL_PASSWORD`, app vẫn chạy bình thường — chỉ riêng bước gửi email xác nhận sau khi check-in sẽ bị bỏ qua (ghi log lỗi, không làm crash check-in).

3. **Cài thư viện và chạy**:
   ```bash
   pip install flask flask-sqlalchemy flask-mail flask-wtf python-dotenv Pillow PyMySQL
   python app.py
   ```
   Lần chạy đầu tiên, app tự tạo toàn bộ bảng trong database và seed sẵn:
   - 1 tài khoản admin mặc định (`ADMIN_DEFAULT_USERNAME` / `ADMIN_DEFAULT_PASSWORD`, mặc định `admin` / `admin123`)
   - 1 sự kiện mặc định để test nhanh

4. Mở trình duyệt tại **http://127.0.0.1:5000**

## Hướng dẫn sử dụng

### Phía người tham gia sự kiện
- **Trang chủ (`/`)**: xem danh sách sự kiện đang mở đăng ký, đăng ký tham gia bằng mã CB/SV.
- **Trang check-in (`/checkin`)**: nhập mã CB/SV để điểm danh. Check-in thành công sẽ:
  - Cộng điểm rèn luyện, hiển thị thông báo xác nhận.
  - Tự động tạo chứng chỉ (PDF) nếu sự kiện có bật cấp chứng chỉ và đã có mẫu chứng chỉ.
  - Gửi email xác nhận kèm file chứng chỉ đính kèm (nếu đã cấu hình SMTP).

### Phía quản trị viên (`/admin`)
- **Đăng nhập**: `/admin/login`, dùng tài khoản admin đã seed sẵn hoặc tài khoản admin đã tạo.
- **Danh sách sự kiện**: thêm/sửa/xóa sự kiện, tải hình đại diện sự kiện.
- **Thiết lập chứng chỉ**: bấm nút "Chứng chỉ" ở mỗi sự kiện để mở trình thiết kế mẫu chứng chỉ — tải ảnh nền (tự động gợi ý crop nếu ảnh không đúng tỉ lệ 2000×1414), kéo-thả 5 trường thông tin (họ tên, mã CB/SV, đơn vị, ngày cấp, mã chứng nhận) vào đúng vị trí trên ảnh nền, chỉnh cỡ chữ/màu/căn lề/font riêng cho từng trường, rồi bấm "Lưu vị trí".
- **Chi tiết sự kiện**: xem danh sách đăng ký/check-in của từng sự kiện, check-in thủ công hoặc xóa check-in, xem/tải chứng chỉ đã cấp.
- **Quản lý đơn vị**: bấm biểu tượng bánh răng ở góc phải thanh điều hướng khi đang ở khu vực quản trị.
- **Xuất CSV / Reset dữ liệu**: có trong trang quản trị để xuất báo cáo hoặc xóa toàn bộ dữ liệu đăng ký/check-in/chứng chỉ khi cần làm lại từ đầu.

## Lưu ý kỹ thuật
- Toàn bộ thời gian hệ thống lưu trong database theo **UTC**; các trang admin/email/chứng chỉ tự động hiển thị theo giờ Việt Nam (UTC+7) qua `event_checkin/utils/timezone.py`. Riêng lịch trình sự kiện (ngày bắt đầu, thời gian mở/đóng đăng ký) do admin tự nhập nên hiển thị đúng nguyên giá trị đã nhập, không quy đổi múi giờ.
- Chứng chỉ được sinh lại (render mới) mỗi khi có người xem/tải, luôn khớp với mẫu và vị trí mới nhất đã lưu trong trình thiết kế.
