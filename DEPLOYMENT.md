# Triển khai production trên Windows Server 2019 + IIS + SSL

Hướng dẫn này giả định bạn thao tác trực tiếp trên Windows Server 2019 (qua UltraViewer), với quyền Administrator, đã có domain trỏ DNS (bản ghi A) về IP public của server.

## 0. Kiến trúc

```
Internet --443/80--> IIS (SSL termination, reverse proxy, ARR + URL Rewrite)
                         |
                         v  http://127.0.0.1:8000  (chỉ nội bộ, không public)
                      waitress (WSGI server, chạy như Windows Service qua NSSM)
                         |
                         v
                      Flask app (wsgi.py -> app.py)
                         |
                         v  127.0.0.1:3307 (chỉ nội bộ)
                      MariaDB Server (Windows Service)
```

IIS không chạy Python trực tiếp — nó chỉ nhận traffic HTTPS rồi chuyển tiếp (reverse proxy) sang `waitress` chạy nội bộ. Đây là cách chuẩn cho Flask trên Windows Server (gunicorn không chạy trên Windows).

## 1. Cài các thành phần cần thiết trên server

Chạy PowerShell **với quyền Administrator**:

```powershell
# Windows features cho IIS
Install-WindowsFeature -Name Web-Server, Web-Http-Redirect, Web-Mgmt-Console -IncludeManagementTools

# winget (thường có sẵn trên Server 2019 mới; nếu chưa có, cài Python/Git thủ công từ python.org / git-scm.com)
winget install --id Python.Python.3.13 -e --accept-package-agreements --accept-source-agreements
winget install --id Git.Git -e --accept-package-agreements --accept-source-agreements
```

Cài thêm (bắt buộc thao tác qua trình cài .msi/.exe, không có gói winget ổn định):
- **URL Rewrite module**: https://www.iis.net/downloads/microsoft/url-rewrite
- **Application Request Routing (ARR) 3.0**: https://www.iis.net/downloads/microsoft/application-request-routing
- **NSSM** (chạy waitress như Windows Service): https://nssm.cc/download — giải nén, đặt `nssm.exe` vào ví dụ `C:\tools\nssm\nssm.exe`
- **win-acme** (SSL Let's Encrypt miễn phí): https://www.win-acme.com/ — giải nén, ví dụ `C:\tools\win-acme\wacs.exe`

Sau khi cài ARR, bật tính năng proxy cấp server (một lần duy nhất), đồng thời bảo ARR gửi IP thật của người dùng
trong header `X-Forwarded-For` và **không gắn kèm cổng** (nếu ARR ghi `IP:cổng` thì mỗi kết nối một cổng khác nhau,
các giới hạn theo IP mất tác dụng; app có tự bỏ cổng nhưng nên tắt ngay từ ARR):
```powershell
& "$env:windir\system32\inetsrv\appcmd.exe" set config -section:system.webServer/proxy /enabled:"True" /xForwardedForHeaderName:"X-Forwarded-For" /includePortInXForwardedFor:"False" /commit:apphost
```
Hoặc trong IIS Manager: chọn tên máy chủ → **Application Request Routing Cache** → **Server Proxy Settings...** → tích
**Preserve client IP in the following header** = `X-Forwarded-For`, **bỏ tích** **Include TCP port from client IP** → Apply.
App chỉ tin header này khi `APP_ENV=production` và request đến từ chính máy này (127.0.0.1, tức IIS) — xem
`TrustedLocalProxyFix` trong `app.py`.

## 2. Cài MariaDB Server (giống máy dev nhưng lần này đăng ký Service thật vì có quyền admin)

```powershell
winget install --id MariaDB.Server -e --accept-package-agreements --accept-source-agreements

$dataDir = "C:\ProgramData\MariaDB\data"
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null

& "C:\Program Files\MariaDB 12.3\bin\mariadb-install-db.exe" `
  --datadir="$dataDir" --service=MariaDB --port=3306 `
  --password="<MAT_KHAU_ROOT_MANH>" --default-user

Start-Service MariaDB
Set-Service MariaDB -StartupType Automatic
```

> Ghi chú: khi chạy với quyền Administrator thật, bước `--service=MariaDB` sẽ đăng ký thành Windows Service hoàn chỉnh (khác với máy dev không có quyền admin nên phải chạy `mariadbd.exe` thủ công).

### 2.1 Tạo user riêng cho app (không dùng root)

```powershell
& "C:\Program Files\MariaDB 12.3\bin\mariadb.exe" -u root -p -e @"
CREATE DATABASE IF NOT EXISTS checkin_event CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'checkin_app'@'localhost' IDENTIFIED BY '<MAT_KHAU_APP_MANH>';
GRANT SELECT, INSERT, UPDATE, DELETE, INDEX, CREATE, ALTER, REFERENCES ON checkin_event.* TO 'checkin_app'@'localhost';
FLUSH PRIVILEGES;
"@
```

Dùng user `checkin_app` (không phải `root`) trong `.env` production — giảm rủi ro nếu app bị khai thác lỗ hổng thì kẻ tấn công chỉ có quyền trên đúng 1 database, không có quyền quản trị toàn bộ MariaDB.

### 2.2 Bind MySQL chỉ ở localhost + tối ưu buffer pool

Sửa `C:\Program Files\MariaDB 12.3\data\my.ini`:
```ini
[mysqld]
datadir=C:/ProgramData/MariaDB/data
port=3306
bind-address=127.0.0.1
innodb_buffer_pool_size=<~50-70% RAM server, ví dụ 4G nếu server có 8GB RAM>
max_connections=150
```
`bind-address=127.0.0.1` đảm bảo MySQL không nghe trên network interface public — kể cả nếu quên đóng firewall, DB vẫn không thể bị truy cập từ ngoài.

Restart service sau khi sửa: `Restart-Service MariaDB`

### 2.3 Backup tự động hằng ngày

Tạo script `C:\tools\backup-db.ps1`:
```powershell
$date = Get-Date -Format "yyyyMMdd_HHmmss"
$out = "C:\backups\checkin_event_$date.sql"
& "C:\Program Files\MariaDB 12.3\bin\mariadb-dump.exe" -u root -p"<MAT_KHAU_ROOT>" checkin_event > $out
# Xóa backup cũ hơn 30 ngày
Get-ChildItem "C:\backups\checkin_event_*.sql" | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } | Remove-Item
```
Đăng ký Task Scheduler chạy hằng ngày (ví dụ 2h sáng):
```powershell
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -File C:\tools\backup-db.ps1"
$trigger = New-ScheduledTaskTrigger -Daily -At 2am
Register-ScheduledTask -TaskName "CheckinEvent-DB-Backup" -Action $action -Trigger $trigger -RunLevel Highest
```
**File chứng chỉ** (từ bản m007) nằm ở `C:\apps\eventcheckin\instance\certificates` (hoặc `CERTIFICATE_STORAGE_DIR`
trong `.env`), không nằm trong DB nên phải sao lưu riêng. Thêm vào cuối `backup-db.ps1`:
```powershell
robocopy "C:\apps\eventcheckin\instance\certificates" "C:\backups\certificates" /MIR /R:1 /W:1 | Out-Null
```

Khuyến nghị: định kỳ copy thư mục `C:\backups` ra ngoài server (Google Drive, OneDrive, ổ ngoài...) — backup nằm chung server sẽ mất luôn nếu server hỏng/bị mã hoá.

## 3. Deploy code lên server

Copy thủ công (USB / ổ mạng chia sẻ / kéo-thả qua UltraViewer file transfer) toàn bộ thư mục dự án từ máy dev sang server, đích ví dụ `C:\apps\eventcheckin\`.

**Chỉ copy những gì cần** — không copy các thư mục sau (không cần thiết, có cái còn gây lỗi vì venv Windows không portable giữa 2 máy):
- `.venv\` — sẽ tạo venv mới trên server ở bước 3.1
- `__pycache__\`, mọi `*.pyc`
- `.uv-cache\`
- `.git\` — không cần vì không dùng git để deploy đợt này
- `flask_stdout.log`, `flask_stderr.log`, `logs\` — log của máy dev, không cần mang theo
- `database\` — dữ liệu Excel/dump cũ của máy dev, không phải nguồn dữ liệu production (DB thật sẽ được tạo mới trên server ở Mục 2)

**Cần copy đầy đủ**: `event_checkin\` (toàn bộ, gồm cả `static\certificates\templates` và `fonts`), `instance\certificates\` (chứng chỉ đã tạo, nếu chuyển từ máy khác), `app.py`, `config.py`, `requirements.txt`, `wsgi.py`, `README.md`.

**Không copy `.env` của máy dev sang thẳng** — tạo `.env` **mới** riêng cho production ở bước bên dưới (đổi `SECRET_KEY`, mật khẩu DB, mật khẩu admin — không dùng lại giá trị dev).

Tạo `.env` production tại `C:\apps\eventcheckin\.env`:
```env
APP_ENV=production
SECRET_KEY=<CHUOI_NGAU_NHIEN_MANH_TOI_THIEU_32_KY_TU>
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=checkin_app
MYSQL_PASSWORD=<MAT_KHAU_APP_MANH>
MYSQL_DATABASE=checkin_event

MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USERNAME=<email-that>
MAIL_PASSWORD=<app-password-that>
MAIL_USE_TLS=true
MAIL_USE_SSL=false
MAIL_SENDER=<email-that>

ADMIN_DEFAULT_USERNAME=admin
ADMIN_DEFAULT_PASSWORD=<MAT_KHAU_ADMIN_MANH_KHONG_PHAI_admin123>
```

**Quan trọng**: sinh `SECRET_KEY` ngẫu nhiên thật (không dùng giá trị mẫu), ví dụ:
```powershell
& "C:\apps\eventcheckin\.venv\Scripts\python.exe" -c "import secrets; print(secrets.token_hex(32))"
```
Và **bắt buộc đổi** `ADMIN_DEFAULT_PASSWORD` khỏi `admin123` — nếu để mặc định, bất kỳ ai biết URL `/admin/login` đều đăng nhập được.

### 3.1 Cài venv + thư viện

```powershell
& "C:\Program Files\Python313\python.exe" -m venv "C:\apps\eventcheckin\.venv"
& "C:\apps\eventcheckin\.venv\Scripts\python.exe" -m pip install --upgrade pip
& "C:\apps\eventcheckin\.venv\Scripts\python.exe" -m pip install -r "C:\apps\eventcheckin\requirements.txt"
```

### 3.2 Chạy thử 1 lần bằng tay để kiểm tra app khởi động, tự tạo bảng + index

```powershell
Set-Location "C:\apps\eventcheckin"
& ".venv\Scripts\python.exe" wsgi.py
```
Kỳ vọng: log "Serving on http://127.0.0.1:8000", không lỗi kết nối DB. Nhấn Ctrl+C dừng lại sau khi xác nhận OK — bước tiếp theo sẽ chạy nó như Windows Service.

## 4. Đăng ký waitress làm Windows Service (qua NSSM)

```powershell
$nssm = "C:\tools\nssm\nssm.exe"
$python = "C:\apps\eventcheckin\.venv\Scripts\python.exe"
$wsgi = "C:\apps\eventcheckin\wsgi.py"

& $nssm install EventCheckinApp $python $wsgi
& $nssm set EventCheckinApp AppDirectory "C:\apps\eventcheckin"
& $nssm set EventCheckinApp AppStdout "C:\apps\eventcheckin\logs\service-stdout.log"
& $nssm set EventCheckinApp AppStderr "C:\apps\eventcheckin\logs\service-stderr.log"
& $nssm set EventCheckinApp AppRotateFiles 1
& $nssm set EventCheckinApp Start SERVICE_AUTO_START
& $nssm set EventCheckinApp AppExit Default Restart

Start-Service EventCheckinApp
Get-Service EventCheckinApp
```

Kiểm tra: `Invoke-WebRequest http://127.0.0.1:8000/` từ chính server phải trả về 200.

## 5. Cấu hình IIS

### 5.1 Tạo Site

IIS Manager → Sites → Add Website:
- Site name: `EventCheckin`
- Physical path: bất kỳ thư mục rỗng, ví dụ `C:\apps\eventcheckin\iis-site` (chỉ chứa `web.config`, không phục vụ file tĩnh trực tiếp qua đây — mọi request đều được proxy sang waitress)
- Binding: `http`, port `80`, Host name: `<domain-cua-ban>`

### 5.2 `web.config` — reverse proxy sang waitress + ép HTTPS

Tạo `C:\apps\eventcheckin\iis-site\web.config`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
  <system.webServer>
    <rewrite>
      <rules>
        <rule name="RedirectToHTTPS" stopProcessing="true">
          <match url="(.*)" />
          <conditions>
            <add input="{HTTPS}" pattern="^OFF$" />
          </conditions>
          <action type="Redirect" url="https://{HTTP_HOST}/{R:1}" redirectType="Permanent" />
        </rule>
        <!-- Chứng chỉ cũ từng nằm trong static (ai đoán tên file là tải được): chặn hẳn, kể cả khi thư mục còn sót file -->
        <rule name="BlockLegacyCertificateFiles" stopProcessing="true">
          <match url="^static/certificates/generated/.*" />
          <action type="CustomResponse" statusCode="404" statusReason="Not Found" statusDescription="Not Found" />
        </rule>
        <rule name="StaticFilesPassThrough" stopProcessing="true">
          <match url="^static/.*" />
          <action type="None" />
        </rule>
        <rule name="ReverseProxyToWaitress" stopProcessing="true">
          <match url="(.*)" />
          <serverVariables>
            <set name="HTTP_X_FORWARDED_PROTO" value="https" />
            <set name="HTTP_X_FORWARDED_HOST" value="{HTTP_HOST}" />
          </serverVariables>
          <action type="Rewrite" url="http://127.0.0.1:8000/{R:1}" />
        </rule>
      </rules>
      <allowedServerVariables>
        <add name="HTTP_X_FORWARDED_PROTO" />
        <add name="HTTP_X_FORWARDED_HOST" />
      </allowedServerVariables>
    </rewrite>
  </system.webServer>
</configuration>
```
Rule đầu ép mọi request HTTP sang HTTPS trước. Rule thứ hai để `/static/...` đi qua bình thường (`action type="None"`) thay vì bị proxy sang waitress — kết hợp với virtual directory `static` trỏ thẳng vào thư mục static thật (xem mục 5.3), để IIS tự phục vụ CSS/JS/ảnh/chứng chỉ trực tiếp, nhanh hơn và không tốn luồng xử lý của app Python. Rule thứ ba (chỉ chạy được khi đã là HTTPS, và không phải `/static/...`) mới proxy tiếp sang waitress kèm header `X-Forwarded-Proto: https` — Flask (qua `ProxyFix` đã thêm trong `app.py`) đọc header này để biết request gốc là HTTPS, nhờ vậy cookie `Secure` và link tuyệt đối (`url_for(_external=True)`, dùng khi gửi email chứng chỉ) mới đúng.

### 5.3 Virtual Directory cho `/static` (để IIS phục vụ trực tiếp)

Trong IIS Manager, chuột phải vào site `EventCheckin` → **Add Virtual Directory...**:
- Alias: `static`
- Physical path: `C:\apps\eventcheckin\event_checkin\static`

OK. IIS giờ sẽ tự phục vụ mọi request `/static/...` (CSS, JS, ảnh sự kiện, font) trực tiếp từ ổ đĩa, không đi qua app Python nữa. Vì vậy **không được để file có dữ liệu cá nhân trong `static`**: chứng chỉ đã tạo nằm ở `instance\certificates` (ngoài `static`) và chỉ tải được qua route của app; rule `BlockLegacyCertificateFiles` ở mục 5.2 chặn thêm đường dẫn cũ `/static/certificates/generated/`.

## 6. SSL miễn phí với win-acme (Let's Encrypt)

```powershell
Set-Location "C:\tools\win-acme"
.\wacs.exe
```
Chọn theo thứ tự trong menu tương tác:
1. `N` (create new certificate) → `1` (single binding of an IIS site)
2. Chọn site `EventCheckin`
3. Để mặc định các bước còn lại (win-acme tự tạo HTTPS binding 443 cho site, tự cấu hình gia hạn qua Scheduled Task riêng của nó — mặc định chạy 2 lần/ngày, tự gia hạn khi cert còn ~30 ngày)

Sau khi xong, IIS site sẽ có thêm binding `https` port `443` gắn cert Let's Encrypt. Vào lại binding port 80, đảm bảo vẫn tồn tại (để rule redirect ở bước 5.2 hoạt động và để win-acme gia hạn được bằng HTTP validation).

## 7. Windows Firewall

```powershell
New-NetFirewallRule -DisplayName "HTTP" -Direction Inbound -Protocol TCP -LocalPort 80 -Action Allow
New-NetFirewallRule -DisplayName "HTTPS" -Direction Inbound -Protocol TCP -LocalPort 443 -Action Allow
```
**Không** tạo rule mở port 3306 (MariaDB) hay 8000 (waitress) ra ngoài — hai port này chỉ cần truy cập được từ `127.0.0.1`, không có lý do nào để public.

## 8. Checklist kiểm thử sau triển khai

- [ ] `https://<domain>/` load được, có ổ khoá SSL hợp lệ (không cảnh báo trình duyệt)
- [ ] `http://<domain>/` tự động redirect sang `https://`
- [ ] Đăng nhập `/admin/login` bằng tài khoản admin đã đổi mật khẩu (không phải `admin123`)
- [ ] Đăng ký thử 1 sự kiện bằng mã CB/SV test, check-in thử tại `/checkin`
- [ ] `python -m event_checkin.migrations.m005_cau_hoi_dang_ky --check` báo `OK` (sau khi chạy m005)
- [ ] Menu **Quay số may mắn** (`/admin/lucky-draw`) mở được; thiết lập thử 1 sự kiện (giải + ảnh nền), quay thử, Lưu, rồi xóa thiết lập thử (sau khi chạy m004)
- [ ] Chứng chỉ PDF/PNG tạo và tải được sau check-in (nếu event bật cấp chứng chỉ)
- [ ] Email xác nhận gửi được (kiểm tra hộp thư, và `C:\apps\eventcheckin\logs\app.log` không có lỗi SMTP)
- [ ] `Restart-Service EventCheckinApp` xong app tự chạy lại bình thường (không cần thao tác thêm)
- [ ] Khởi động lại server (`Restart-Computer`) xong, cả MariaDB, EventCheckinApp, IIS đều tự chạy lại không cần can thiệp tay
- [ ] Sau ~1 phút kiểm tra `C:\backups\` có file backup mới nhất đúng lịch (chạy thử task ngay: `Start-ScheduledTask -TaskName "CheckinEvent-DB-Backup"`)

## 9. Vận hành lâu dài

- **Log ứng dụng**: `C:\apps\eventcheckin\logs\app.log` (tự xoay vòng, tối đa 5 file x 5MB, cấu hình trong `app.py`). Log service (stdout/stderr) tại `C:\apps\eventcheckin\logs\service-*.log`.
- **Cập nhật code**: `git pull` trong `C:\apps\eventcheckin`, `pip install -r requirements.txt` nếu có thư viện mới, rồi `Restart-Service EventCheckinApp`. App tự chạy `ensure_schema_upgrades()`/`db.create_all()` mỗi lần khởi động nên các thay đổi schema nhỏ (thêm cột/index) tự áp dụng, không cần chạy migration thủ công.
- **Ngoại lệ — bản cập nhật check-in/gửi chứng chỉ (10/2026)**: thêm bảng/cột mà `db.create_all()` không tự thêm vào bảng đã có. Sao lưu database, chép code mới, `Restart-Service EventCheckinApp`, rồi chạy **ngay** theo thứ tự (chạy lại nhiều lần vẫn an toàn):
  ```powershell
  .venv\Scripts\python -m event_checkin.migrations.m001_checkin_records --dry-run   # xem trước
  .venv\Scripts\python -m event_checkin.migrations.m001_checkin_records             # tạo bảng checkin_records + chuyển check-in cũ
  .venv\Scripts\python -m event_checkin.migrations.m002_cert_display_name
  .venv\Scripts\python -m event_checkin.migrations.m003_email_override
  ```
  Thiếu m002/m003 thì mọi trang dùng check-in sẽ lỗi. Hướng dẫn sử dụng cho admin: `HUONG_DAN_ADMIN.md`.
- **Bản cập nhật quay số may mắn (10/2026)**: thêm 3 bảng mới `lucky_configs`, `lucky_prizes`, `lucky_winners` (không sửa/xóa bảng hay dữ liệu cũ). **Sao lưu database trước** (`Start-ScheduledTask -TaskName "CheckinEvent-DB-Backup"`), chép code mới, rồi chạy (chạy lại nhiều lần vẫn an toàn):
  ```powershell
  .venv\Scripts\python -m event_checkin.migrations.m004_lucky_draw
  Restart-Service EventCheckinApp
  ```
  Muốn xem trước câu SQL: thêm `--print-sql`. Lưu ý app có `db.create_all()` lúc khởi động nên 3 bảng này có thể đã được tự tạo; khi đó m004 báo "đã có sẵn" và không làm gì thêm.
  - **Kiểm tra bảng cũ (bản thử trước 26/10/2026 thiếu cột `phien_ban`, `created_at`, `updated_at`)**: nếu m004 báo *"Bảng lucky_configs đang có là bản cũ"*, hoặc bạn đã từng chạy thử trên máy dev, kiểm tra rồi xóa 3 bảng (đang rỗng hoặc chỉ có dữ liệu thử) và chạy lại m004:
    ```sql
    -- MySQL/MariaDB:
    SHOW TABLES LIKE 'lucky%';
    SELECT COUNT(*) FROM lucky_winners;      -- nếu > 0 là dữ liệu thử, cân nhắc trước khi xóa
    SET FOREIGN_KEY_CHECKS=0;
    DROP TABLE IF EXISTS lucky_winners, lucky_prizes, lucky_configs;
    SET FOREIGN_KEY_CHECKS=1;
    ```
    Với SQLite xem thử (`instance/preview.db`): `sqlite3 instance/preview.db ".tables"`, rồi `DROP TABLE lucky_winners; DROP TABLE lucky_prizes; DROP TABLE lucky_configs;`. Sau đó chạy lại `python -m event_checkin.migrations.m004_lucky_draw`.
  - Ảnh nền do admin tải lên được lưu ở `event_checkin\static\lucky\uploads\` — tài khoản chạy service `EventCheckinApp` cần có quyền ghi thư mục này (và nên đưa vào lịch sao lưu cùng `static\events`). Hướng dẫn cho admin: mục 8 của `HUONG_DAN_ADMIN.md`.
- **Bản cập nhật ô "câu hỏi" ở form đăng ký (11/2026)**: thêm 3 cột mới (`events.cho_phep_cau_hoi`, `events.tieu_de_cau_hoi`, `registrations.cau_hoi`), không sửa/xóa dữ liệu cũ; sự kiện cũ mặc định tắt, đăng ký cũ có câu hỏi rỗng. **Làm đúng thứ tự** (đừng khởi động lại app trước khi chạy m005 — code mới đọc các cột này, thiếu cột thì app không khởi động được):
  1. **Backup database**: `Start-ScheduledTask -TaskName "CheckinEvent-DB-Backup"`, rồi kiểm tra `C:\backups\` có file `checkin_event_<ngày>.sql` mới nhất.
  2. **Chép code mới**: `git pull` trong `C:\apps\eventcheckin` (app đang chạy vẫn dùng code cũ, chưa ảnh hưởng).
  3. **Chạy m005** (chạy lại nhiều lần vẫn an toàn):
     ```powershell
     .venv\Scripts\python -m event_checkin.migrations.m005_cau_hoi_dang_ky
     ```
  4. **Khởi động lại app**: `Restart-Service EventCheckinApp`.

  **Kiểm tra m005 đã chạy thành công** (mã thoát `0` và dòng bắt đầu bằng `OK` là đạt; nếu in `CHƯA ĐỦ` thì quay lại bước 3):
  ```powershell
  .venv\Scripts\python -m event_checkin.migrations.m005_cau_hoi_dang_ky --check
  ```
  Hoặc kiểm tra trực tiếp trong MySQL/MariaDB (phải thấy đủ 3 dòng):
  ```sql
  SELECT TABLE_NAME, COLUMN_NAME FROM information_schema.COLUMNS
   WHERE TABLE_SCHEMA = DATABASE()
     AND ((TABLE_NAME = 'events' AND COLUMN_NAME IN ('cho_phep_cau_hoi', 'tieu_de_cau_hoi'))
       OR (TABLE_NAME = 'registrations' AND COLUMN_NAME = 'cau_hoi'));
  ```
  Câu hỏi có thể chứa emoji: cột/bảng cần bộ ký tự `utf8mb4` (mặc định của MySQL 8 và `?charset=utf8mb4` trong chuỗi kết nối). Kiểm tra: `SHOW FULL COLUMNS FROM registrations LIKE 'cau_hoi';` cột `Collation` phải bắt đầu bằng `utf8mb4`.
- **Bản cập nhật phân quyền 3 cấp (11/2026, đang triển khai theo từng bước — đợt này mới có migration m006 + model)**: thêm cột `admins.email/must_change_password/session_version/last_login_at`, `events.updated_by`, `checkin_records.checked_in_by` và 2 bảng `audit_logs`, `password_resets`; không sửa/xóa dữ liệu cũ. Tài khoản hiện có mà `role` không thuộc `super_admin/admin/staff` được gán `super_admin`. Làm đúng thứ tự như m005 (backup DB → `git pull` → chạy m006 → `Restart-Service EventCheckinApp`; **không khởi động lại app trước khi chạy m006**):
  ```powershell
  .venv\Scripts\python -m event_checkin.migrations.m006_phan_quyen
  .venv\Scripts\python -m event_checkin.migrations.m006_phan_quyen --check   # mã thoát 0 + dòng "OK" là đạt
  ```
  - **Tài khoản thử và sự kiện thử chỉ dùng trên DB THỬ (`checkin_event_test`), KHÔNG tạo trên DB thật `checkin_event`.** Gồm tài khoản `nv_staff`, `nv_admin` (mật khẩu thử đơn giản), sự kiện `[DEMO] Sự kiện thử phân quyền` và các mã `DEMO001`–`DEMO003`. Test tự động (`tests/`) cũng tự từ chối chạy nếu tên DB không kết thúc bằng `_test`. Trên DB thật chỉ tạo tài khoản thật, mật khẩu mạnh, bằng `scripts\tao_tai_khoan.py` (có in tên DB đang dùng; kiểm tra kỹ trước khi nhấn Enter) hoặc, sau khi xong bước (d), bằng trang Quản lý tài khoản.
  - Sau khi nâng cấp, **mọi phiên đăng nhập cũ bị đăng xuất một lần** (phiên mới lưu thêm `session_version`); admin chỉ cần đăng nhập lại.
  - Từ bước (c): `/checkin`, `/checkin/<id>`, `/api/checkin` **bắt buộc đăng nhập** (staff trở lên); người tham dự không tự check-in. Trang đăng ký sự kiện vẫn công khai.
  - **Thời gian check-in sau khi sự kiện kết thúc**: biến `CHECKIN_GRACE_HOURS` trong `.env` (mặc định `5` giờ; muốn khác thì đặt ví dụ `CHECKIN_GRACE_HOURS=2`). Trong khoảng này staff vẫn thấy nút Check-in và check-in được; quá mốc thì staff chỉ xem danh sách, admin thêm check-in tay. Đổi giá trị xong cần `Restart-Service EventCheckinApp`.
  - Chạy test (trên máy dev, DB thử): `$env:MYSQL_DATABASE = "checkin_event_test"` rồi `.venv\Scripts\python -m unittest discover -s . -t . -p "test_*.py" -v`.
- **Bản cập nhật bảo mật chứng chỉ (11/2026, migration m007)**: file chứng chỉ chuyển từ `event_checkin\static\certificates\generated` (IIS phục vụ thẳng, ai đoán tên file là tải được) sang `instance\certificates`; mỗi chứng chỉ có token ngẫu nhiên, link mới `/c/<token>`, `/c/<token>/view`, `/verify/t/<token>`. Link cũ trong email đã gửi (`/verify/<mã>`, `/api/certificates/<mã>`) vẫn mở được nhưng muốn tải file phải nhập đúng mã CB/SV. Làm **đúng thứ tự** (không khởi động lại app trước bước 4):
  1. Sao lưu DB (`Start-ScheduledTask -TaskName "CheckinEvent-DB-Backup"`) **và sao lưu thư mục chứng chỉ cũ**: bản cập nhật gỡ thư mục này khỏi git nên `git pull` có thể xóa các file trong đó.
     ```powershell
     robocopy "C:\apps\eventcheckin\event_checkin\static\certificates\generated" "C:\backups\certificates_truoc_m007" /E
     (Get-ChildItem "C:\backups\certificates_truoc_m007" -Recurse -File).Count   # ghi lại con số này
     ```
  2. `git pull`. Nếu git báo lỗi vì file trong `static\certificates\generated` khác bản trên repo: chạy `git checkout -- event_checkin/static/certificates/generated` rồi `git pull` lại (đã có bản sao ở bước 1).
  3. Chép lại các file có thể đã bị `git pull` xóa, không ghi đè file đang có: `robocopy "C:\backups\certificates_truoc_m007" "C:\apps\eventcheckin\event_checkin\static\certificates\generated" /E /XC /XN /XO`
  4. Chạy m007 rồi khởi động lại:
     ```powershell
     .venv\Scripts\python -m event_checkin.migrations.m007_certificate_token --dry-run   # xem trước
     .venv\Scripts\python -m event_checkin.migrations.m007_certificate_token             # thực hiện (chạy lại nhiều lần vẫn an toàn)
     .venv\Scripts\python -m event_checkin.migrations.m007_certificate_token --check     # mã thoát 0 + dòng "OK" là đạt
     Restart-Service EventCheckinApp
     ```
     So số file: `(Get-ChildItem C:\apps\eventcheckin\instance\certificates -Recurse -File).Count` phải bằng số chứng chỉ có file (trên DB: `SELECT COUNT(*) FROM certificates WHERE file_url IS NOT NULL AND file_url <> '';`, trừ các dòng m007 cảnh báo "không còn file"). m007 cũng liệt kê các file "không thuộc chứng chỉ nào" (ảnh xem trước, chứng chỉ đã xóa): những file này không được chép.
  5. Cập nhật `C:\apps\eventcheckin\iis-site\web.config` theo mục 5.2 (thêm rule `BlockLegacyCertificateFiles`), bật `X-Forwarded-For` không kèm cổng theo mục 1, rồi `iisreset`. Kiểm tra từ máy khác: mở `https://<domain>/static/certificates/generated/2026/<tên một file có thật>` phải ra **404**.
  6. Sau khi kiểm tra web chạy đúng (tải chứng chỉ bằng link mới, admin xem/tải ZIP được), xóa file cũ: `.venv\Scripts\python -m event_checkin.migrations.m007_certificate_token --remove-old` (chỉ xóa khi `--check` đạt). Giữ `C:\backups\certificates_truoc_m007` thêm một thời gian rồi xóa.
  7. Thêm `instance\certificates` vào backup hằng ngày (mục 2.3).
  - `.env` có thể đặt `CERTIFICATE_STORAGE_DIR` (thư mục khác, ví dụ trên ổ D:) và `CERT_PUBLIC_RATE_LIMIT` (số request mỗi phút cho mỗi IP vào các trang chứng chỉ công khai, mặc định `120` vì cả trường dùng chung IP Wi-Fi; đếm trong bộ nhớ, khởi động lại app thì về 0). Nhập sai mã CB/SV ở link cũ: tối đa 5 lần / 15 phút cho mỗi mã chứng chỉ và mỗi IP.
  - Kiểm tra IP thật: sau khi bật `X-Forwarded-For`, đăng nhập từ một máy khác rồi xem **Quản trị → Nhật ký hoạt động**: cột IP phải là IP của máy đó (không phải `127.0.0.1`). Nếu vẫn là `127.0.0.1`: kiểm tra `APP_ENV=production` trong `.env` và cấu hình ARR ở mục 1. IP này dùng cho nhật ký, giới hạn quên mật khẩu và các giới hạn chứng chỉ.
- **Gia hạn SSL**: tự động qua Scheduled Task của win-acme, không cần làm gì thêm trừ khi domain đổi hoặc chứng chỉ gặp lỗi (kiểm tra bằng `wacs.exe` → renew manually nếu nghi ngờ).
- **Giám sát**: định kỳ xem `Get-Service EventCheckinApp, MariaDB, W3SVC` để chắc cả 3 đang `Running`.

- **Tạo tài khoản đầu tiên / khôi phục super_admin (bước d phân quyền)**:
  - Sau khi chạy m006, tài khoản cũ tự thành `super_admin`. Có thể tạo thêm tài khoản ngay trong web: đăng nhập super_admin → **Quản trị → Quản lý tài khoản**.
  - Tạo tài khoản bằng dòng lệnh khi cần: `.venv\Scripts\python scripts\tao_tai_khoan.py <tên> <staff|admin|super_admin>` (tự in tên DB đang dùng; không có `--password` thì sinh mật khẩu ngẫu nhiên in một lần).
  - **Super_admin quên mật khẩu hoặc bị khóa**: chạy trên máy chủ `.venv\Scripts\python scripts\reset-superadmin.py <tên_đăng_nhập>` — đặt mật khẩu tạm (in một lần), bật buộc đổi mật khẩu, mở khóa, đăng xuất mọi phiên cũ và ghi nhật ký.
  - **Quên mật khẩu qua email** dùng đúng cấu hình gửi thư sẵn có (`MAIL_USERNAME`, `MAIL_PASSWORD` trong `.env`). Chưa cấu hình thì người dùng vẫn thấy câu "Đã gửi liên kết đặt lại mật khẩu…" nhưng không có thư nào được gửi; khi đó dùng chức năng "Đặt lại mật khẩu" của super_admin. Ở môi trường dev (không phải production) liên kết đặt lại được in vào cửa sổ log để thử.
  - Đường dẫn trong thư là địa chỉ tuyệt đối dựng từ domain mà người dùng đang truy cập; sau IIS/ARR cần giữ cấu hình `X-Forwarded-Proto/Host` hiện có thì liên kết mới đúng `https://…`.
  - Chỉ mục `audit_logs (action, created_at)` dùng cho giới hạn quên mật khẩu **đã có sẵn trong m006**.
