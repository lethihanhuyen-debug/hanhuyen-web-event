# Danh sách chức năng giao diện & phân công kiểm tra trước khi deploy

Tài liệu cho 2 người kiểm tra. Mỗi người làm hết phần của mình, tick vào ô khi đã thử **đúng** (không lỗi, không tràn ngang, không lỗi đỏ trong Console F12), ghi lỗi vào cột "Ghi chú".

## Cách thử chung
- Chạy web, đăng nhập admin (tài khoản trong `.env`).
- Thử **3 cỡ màn hình**: máy tính (≥1280px), máy tính bảng (~768px), điện thoại (~390px). Dùng F12 → biểu tượng điện thoại.
- Mỗi chức năng thử cả **trường hợp đúng** lẫn **trường hợp sai** (bỏ trống, nhập sai, mất mạng).
- Kiểm tra: không tràn ngang trang, nút bấm đủ lớn trên điện thoại, chữ tiếng Việt có dấu, ngày giờ dạng `dd/mm/yyyy hh:mm`, không chữ đen/nền đen.
- Sau khi sửa: Ctrl + F5. **Không push lên main khi chưa báo người phụ trách.**

---

## NGƯỜI 1 — Trang công khai, check-in, đăng nhập, danh sách sự kiện, chi tiết sự kiện

### 1. Đầu trang & menu (mọi trang)
- [ ] Tên trường / tên trung tâm viết hoa, không đè lên menu ở 1000px, 1280px, 1920px
- [ ] Menu: Đăng ký, Quản trị (chỉ khi đã đăng nhập); góc phải: chữ "Đăng nhập" (chưa đăng nhập) hoặc icon đăng xuất có hộp xác nhận (đã đăng nhập); điện thoại: nằm cạnh nút ☰
- [ ] Điện thoại: nút ☰ mở/đóng menu, bấm ra ngoài thì đóng
- [ ] Nút "Quay lại đầu trang" ở cuối trang

### 2. Trang chủ / Đăng ký sự kiện (`/`, `/events/<id>/register`)
- [ ] Băng chiếu (slide) sự kiện: nút ‹ ›, chấm tròn, tự chạy
- [ ] Tìm sự kiện theo tên (có bỏ dấu), nhóm theo tháng, "Xem thêm"
- [ ] Lọc/nhãn trạng thái: Sắp diễn ra, Đang diễn ra, Đã kết thúc
- [ ] Sự kiện chưa mở / đã đóng đăng ký: hiện thông báo đúng, không gửi được
- [ ] Biểu mẫu đăng ký: Mã CB/SV (tự điền họ tên/đơn vị khi tra mã), Họ tên, Email, Số điện thoại, Chức vụ, Đơn vị
- [ ] Báo lỗi từng ô (bỏ trống, email sai, SĐT sai), đăng ký trùng, hết chỗ
- [ ] Đăng ký thành công: thông báo + nút "Chọn sự kiện khác"
- [ ] Hiệu ứng mở đầu (intro) không che nội dung

### 3. Check-in (`/checkin`, `/checkin/<id>`)
- [ ] Trang "Chọn sự kiện": danh sách đúng, bấm vào mở đúng sự kiện
- [ ] Ô nhập/quét Mã CB/SV: Enter hoặc máy quét → check-in, ô tự xóa và focus lại
- [ ] Các kết quả: thành công, đã check-in rồi, chưa đăng ký, mã sai — mỗi loại hiện thông báo rõ màu/chữ
- [ ] Nút "← Quay lại"
- [ ] Thử bằng điện thoại thật (camera/máy quét nếu có)

### 4. Đăng nhập admin (`/admin/login`)
- [ ] Đăng nhập đúng → vào danh sách sự kiện
- [ ] Sai mật khẩu / bỏ trống → báo lỗi đỏ, nút hiện trạng thái đang xử lý
- [ ] Chưa đăng nhập mà vào `/admin` → bị chuyển về đăng nhập, đăng nhập xong quay lại đúng trang
- [ ] Đăng xuất (icon góc phải header) → các trang admin không vào được nữa

### 5. Trang Quản trị (`/admin`) và danh sách sự kiện (`/admin/events`)
- [ ] `/admin` hiện 3 thẻ (Sự kiện, Quay số may mắn, Quản lý đơn vị), mỗi thẻ mở đúng trang; các trang con có nút ← Quay lại về `/admin`
- [ ] Đăng nhập xong vào `/admin`
- [ ] Số liệu tổng quan, chip lọc (Tất cả / Sắp diễn ra / Đang diễn ra / Đã kết thúc) + số đếm
- [ ] Ô tìm kiếm sự kiện (bỏ dấu), thông báo khi không có kết quả
- [ ] Nút "Thêm sự kiện": biểu mẫu đủ ô (tên, cơ sở, địa chỉ, ngày bắt đầu, mở đăng ký, ngày kết thúc, đóng đăng ký, số lượng, mô tả, hình)
- [ ] Kiểm tra hợp lệ ngày (kết thúc trước bắt đầu, đóng trước mở…), tải ảnh sai định dạng/quá lớn
- [ ] Nút Sửa (điền sẵn dữ liệu, lưu được), Xóa (hộp xác nhận, xóa xong dữ liệu liên quan mất đúng)
- [ ] Bấm vào thẻ sự kiện → mở trang chi tiết
- [ ] Điện thoại: thẻ sự kiện không tràn, nút đủ lớn

### 6. Chi tiết sự kiện (`/admin/events/<id>`)
- [ ] 4 thẻ thống kê: Đã đăng ký, Đã check-in, Chưa check-in, Đã gửi chứng chỉ — số khớp với bảng
- [ ] Nút: ← Quay lại, Check-in (mở tab mới), Danh sách check-in, Quay số trúng thưởng, Xuất Excel, Gửi chứng nhận hàng loạt
- [ ] Bảng "Danh sách tham dự": chip lọc + số đếm, tìm kiếm bỏ dấu
- [ ] Cột Chứng nhận: Chưa gửi → "Gửi"; Đã gửi (xanh); Gửi lỗi (đỏ) + biểu tượng ⓘ hiện lý do + "Gửi lại"
- [ ] Menu ⋯ mỗi dòng: **hiện sát nút ⋯**, đủ mục (Xem chứng nhận, Gửi lại chứng nhận, Xóa check-in / Check-in thủ công), phím mũi tên/Esc
- [ ] Gửi một dòng: hộp xác nhận → báo kết quả, số trên chip cập nhật
- [ ] Xóa check-in, Check-in thủ công cho người chưa check-in
- [ ] Xuất Excel tải về mở được, tiếng Việt đúng
- [ ] Điện thoại: bảng cuộn ngang trong khung, không làm cả trang tràn

### 7. Trang xác thực chứng nhận (`/verify/<mã>`)
- [ ] Mã hợp lệ: "Chứng nhận hợp lệ", thông tin đúng, nút "Tải chứng nhận"
- [ ] Mã sai: thông báo không tìm thấy (không lộ lỗi hệ thống)
- [ ] Mở bằng mã QR/đường dẫn trong email

---

## NGƯỜI 2 — Danh sách check-in, chứng chỉ (thiết kế + gửi mail), quay số, quản lý đơn vị

### 1. Danh sách check-in (`/admin/events/<id>/checkins`, `/admin/checkins`)
- [ ] Chọn sự kiện (khi vào từ `/admin/checkins`), nút ← Quay lại đúng chỗ
- [ ] Thanh nút: ＋ Thêm check-in thủ công, Nhập (file Excel/CSV: tải mẫu, "Kiểm tra file", báo lỗi từng dòng), Xóa (nhiều dòng), Lọc trùng, Gửi chứng chỉ
- [ ] Chip lọc: Tất cả / Chưa gửi / Đã gửi / Gửi lỗi / Trùng + số đếm; tìm kiếm bỏ dấu
- [ ] Chọn dòng, chọn tất cả (chỉ tính dòng đang hiện)
- [ ] Phân trang: ← Trước / Sau →
- [ ] Cột Chứng chỉ: Gửi / Gửi lại (hộp sửa mã, email, tên in trên chứng chỉ), tooltip lỗi
- [ ] Menu ⋯: Xem chứng chỉ, Gửi lại chứng chỉ — **menu hiện sát nút**
- [ ] Gửi hàng loạt: thanh tiến trình, khoảng cách giữa mỗi mail, Hủy, tải lại trang vẫn thấy tiến trình
- [ ] Bảng "email gửi lỗi": Tải danh sách lỗi, gửi lại tất cả lỗi
- [ ] Lưu trữ chứng chỉ trên server: dung lượng, Tải ZIP, Xóa file trên server (hộp xác nhận), Hoàn tác
- [ ] Xem trước chứng chỉ của từng người, chỉnh vị trí/cỡ chữ ("Lưu vị trí & cỡ chữ")
- [ ] **Gửi 1 chứng chỉ thật vào email của chính mình** (nhớ tắt Avast Mail/Web Shield nếu máy dev lỗi SMTP)

### 2. Thiết lập chứng chỉ (nút "Chứng chỉ" ở thẻ sự kiện trong `/admin/events`)
- [ ] Tải mẫu chứng chỉ, hộp "Cắt ảnh về tỉ lệ 2000×1414" (kéo, thu phóng, Cắt & Tải lên, Hủy)
- [ ] Kéo thả 6 trường: Họ tên, Mã CB/SV, Đơn vị, Ngày cấp, Mã chứng nhận, Tên sự kiện (QR nếu có)
- [ ] Thanh công cụ trường: căn trái/giữa/phải, Đậm, cỡ chữ, font riêng (tải lên / xóa ⟲)
- [ ] Lưu, "Khôi phục", "Xem như khi gửi email" (ảnh server vẽ khớp thiết kế)
- [ ] Đóng hộp có cảnh báo khi còn thay đổi chưa lưu
- [ ] Điện thoại: hộp thiết lập dùng được hoặc có thông báo dùng máy tính

### 3. Quay số may mắn (thẻ Quay số may mắn ở `/admin`)
- [ ] Danh sách (`/admin/lucky-draw`): bảng sự kiện đã thiết lập, "＋ Thiết lập sự kiện mới", ⋯ → Sửa thiết lập / Xóa thiết lập
- [ ] Xóa thiết lập: hộp xác nhận; nếu đã có kết quả phải gõ lại tên sự kiện; sự kiện quay về "chưa thiết lập"
- [ ] Trang thiết lập: chọn sự kiện, tuỳ chọn trùng giải, danh sách giải (thêm, xóa, ▲▼ đổi thứ tự, số suất), ảnh nền (JPG/PNG/WEBP ≤ 5MB, xem trước, đặt lại)
- [ ] Lưu → "Đã lưu"; rời trang khi chưa lưu có cảnh báo; hai tab sửa cùng lúc báo xung đột phiên bản
- [ ] Bảng kết quả: Người trúng / Giải / Giờ trúng, ⋯ → "Hủy (vắng mặt)", bảng đã hủy
- [ ] Xuất Excel kết quả
- [ ] Màn hình quay (`/admin/lucky-draw/<id>/screen`, mở trên máy chiếu/toàn màn hình): chỉ hiện **mã**, nền riêng của sự kiện, viền vàng
- [ ] QUAY → 1 người/lần → Lưu / Quay lại; hết suất, hết người thì báo; không quay trùng người
- [ ] Thử mở 2 tab cùng bấm quay (chỉ 1 thành công)

### 4. Quản lý đơn vị (thẻ Quản lý đơn vị ở `/admin`, trang `/admin/don-vi`)
- [ ] Mở hộp, danh sách đơn vị, **menu ⋯ bấm được và hiện sát nút**
- [ ] Thêm, sửa tên, xóa (hộp xác nhận), ẩn hàng loạt, xóa hàng loạt
- [ ] Đơn vị mới xuất hiện ở ô "Đơn vị" của biểu mẫu đăng ký
- [ ] Điện thoại: mở hộp thì menu ☰ tự đóng

### 5. Mẫu chứng chỉ & chứng nhận (đầu ra)
- [ ] Ảnh chứng chỉ có đúng tên trường/đơn vị, tiếng Việt không vỡ dấu
- [ ] Nội dung email đúng, mở được liên kết xác thực
- [ ] Tải chứng nhận từ trang xác thực (PNG/PDF) mở được

---

## Việc chung cho cả 2 người trước khi deploy
- [ ] `.env` production: `APP_ENV=production`, `MYSQL_*`, mail, mật khẩu admin đổi khác mặc định
- [ ] Chạy migration (m004 quay số) theo `DEPLOYMENT.md`
- [ ] Quét 3 cỡ màn hình cho **mọi** trang trong danh sách trên
- [ ] Console F12 không có lỗi đỏ ở mọi trang
- [ ] Còn tồn: "Gửi hàng loạt" ở trang chi tiết đang dẫn sang trang check-in (TODO); giờ lỗi gửi mail chưa lưu (TODO)
