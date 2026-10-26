# Hướng dẫn admin: Check-in và gửi chứng chỉ

Tài liệu này dành cho cán bộ quản trị sự kiện. Mọi thao tác dưới đây cần **đăng nhập admin** trước.

## 1. Luồng làm việc

1. **Trong sự kiện:** người tham dự quét/nhập mã SV/CB ở trang **Check-in**. Màn hình báo
   *"Check-in thành công! Chứng chỉ sẽ được gửi qua email sau sự kiện."* — lúc này **chưa gửi email**.
2. **Sau sự kiện:** admin vào **Danh sách check-in**, kiểm tra, lọc trùng, xem trước chứng chỉ.
3. Admin bấm **Gửi chứng chỉ**. Hệ thống gửi lần lượt từng người, mỗi email cách nhau 2 giây.
4. Xử lý các dòng lỗi trong bảng **CẦN XỬ LÝ THỦ CÔNG**.

> Người tham dự phải **đăng ký sự kiện trên web** trước thì mới check-in được (họ tên và email lấy từ thông tin đăng ký).

## 2. Mở trang Danh sách check-in

- Trang **Quản trị** → nút **Danh sách check-in**, hoặc
- Trang chi tiết một sự kiện → nút xanh lá **Danh sách check-in**.

Chọn sự kiện ở ô **Sự kiện** dưới tiêu đề. Bốn ô số phía trên cho biết: đã check-in (số người), chưa gửi, đã gửi, lỗi.

**Lọc theo trạng thái** bằng các nút: Tất cả · Chưa gửi · Đã gửi · Lỗi · Trùng.

| Trạng thái | Ý nghĩa |
|---|---|
| Chưa gửi | Đã check-in, chưa gửi chứng chỉ |
| Đã gửi | Đã gửi email chứng chỉ thành công |
| Lỗi | Gửi không được — xem cột *Ghi chú lỗi* |
| Trùng | Lượt quét lặp lại của cùng một người — **không** được gửi |

Tên/email chữ mờ là thông tin tạm lấy theo đăng ký; sẽ được ghi chính thức khi gửi chứng chỉ.

## 3. Các nút thao tác

| Nút | Dùng khi |
|---|---|
| **Gửi chứng chỉ** | Gửi cho tất cả người đang *Chưa gửi*. Nếu đã tick chọn dòng, nút đổi thành **Gửi lại các dòng đã chọn** |
| **Lọc trùng** | Một người quét nhiều lần: giữ lần sớm nhất, các lần sau chuyển *Trùng* (không xóa) |
| **Thêm thủ công** | Thêm check-in cho người quên quét. Giờ mặc định là hiện tại, sửa được |
| **Xóa** | Xóa các dòng đã tick (check-in nhầm). Không hoàn tác được |
| **Tải file về** | Xuất Excel đúng danh sách đang hiển thị (theo bộ lọc) |

Không cần bấm **Lọc trùng** trước khi gửi: mỗi mã chỉ được gửi một lần trong mỗi đợt.

### Nhập cả danh sách check-in từ file Excel

Bấm **Thêm thủ công** (hoặc nút tròn xanh **+** cạnh bộ lọc) → phần **Nhập cả danh sách từ file Excel**:

1. Bấm **Tải file mẫu** để có đúng định dạng: cột **Mã CB/SV** (bắt buộc) và **Thời gian check-in** (`dd/MM/yyyy HH:mm`, giờ Việt Nam; để trống = giờ lúc nhập).
2. Bấm **+ Chọn file Excel** (.xlsx) — chọn được **nhiều file một lúc** (tối đa 20), bấm lại để thêm file. Chọn nhầm thì bấm **✕** cạnh tên file để bỏ ra.
3. Bấm **Kiểm tra file**. Hệ thống báo số dòng hợp lệ và liệt kê dòng lỗi kèm tên file, số dòng, lý do (thiếu mã, chưa đăng ký sự kiện, giờ sai định dạng hoặc ở tương lai…). Bước này **chưa lưu gì**.
4. Bấm **Nhập N dòng** để đưa các dòng hợp lệ vào danh sách (trạng thái *Chưa gửi*); dòng lỗi bị bỏ qua. **Nhập file không gửi email** — vẫn bấm Lọc trùng rồi Gửi chứng chỉ như bình thường.

Lưu ý: để cột mã ở dạng **Text** trong Excel, nếu không mã bắt đầu bằng số 0 sẽ bị mất số 0. Mã lặp lại hoặc đã check-in trước vẫn được nhập — bấm **Lọc trùng** sau đó. File `.xls` cũ: mở bằng Excel rồi lưu lại dạng `.xlsx`. Tối đa 20 file, 5MB mỗi file, tổng 5.000 dòng mỗi lần.

## 4. Xem trước và chỉnh chứng chỉ

**Chỉnh cho cả sự kiện** (áp dụng cho mọi chứng chỉ): bấm **Chỉnh mẫu chứng chỉ**.
- Bấm tên trường bên trái để thêm (Họ tên, Mã CB/SV, Đơn vị, Ngày cấp, Mã chứng nhận, Tên sự kiện), kéo thả để đặt vị trí. Trường mới mặc định **căn trái**.
- Thanh công cụ của trường: cỡ chữ, màu, căn lề, đậm, font riêng, **Rộng tối đa** (tên dài sẽ tự thu nhỏ cho vừa).
- **Xem trước bản thật**: xem đúng chứng chỉ sẽ gửi đi, chưa cần lưu.
- **Lưu** để áp dụng. **Khôi phục mặc định** để bỏ thay đổi chưa lưu.
- Trường nào xóa khỏi trình thiết kế sẽ **không** được in lên chứng chỉ.

**Chỉnh cho từng người** (tên quá dài, sai dấu): bấm **Xem trước** ở dòng của người đó → sửa ô họ tên → **Xem lại** → **Lưu**. Bảng hiện dòng *"In: …"*. Bấm **Khôi phục mặc định** để dùng lại tên gốc.

Chứng chỉ gửi thật luôn dùng đúng cấu hình và tên đã lưu ở bước này.

## 5. Gửi chứng chỉ

1. Bấm **Gửi chứng chỉ** → hộp thoại *"Sẽ gửi chứng chỉ cho N người. Tiếp tục?"* → **OK**.
2. Khung theo dõi hiện:
   - Thanh tiến độ **"Đã gửi X / N — Lỗi: Y"**
   - Dòng vàng **"Đang gửi tới: <mã> — <họ tên>"**
   - **Nhật ký gửi**: thời gian, mã, họ tên, email, kết quả ✓ / ✗ kèm lý do
3. Việc gửi chạy trên máy chủ: **đóng tab vẫn gửi tiếp**, mở lại trang sẽ thấy tiến độ. Trong lúc gửi, nút Gửi bị khóa.
4. Xong đợt sẽ có dòng tổng kết số thành công / lỗi.

Email gửi đi ghi họ tên, tên sự kiện và **giờ check-in** của người đó (không phải giờ gửi), kèm file chứng chỉ PDF.

Nếu máy chủ bị khởi động lại giữa chừng: người chưa gửi vẫn ở trạng thái *Chưa gửi* — chỉ cần bấm **Gửi chứng chỉ** lần nữa, người đã nhận sẽ không bị gửi lại.

## 6. Xử lý dòng lỗi

Sau khi gửi, các dòng lỗi hiện trong bảng viền đỏ **CẦN XỬ LÝ THỦ CÔNG** (dòng đã gửi thành công không hiện ở đây).

| Lý do lỗi thường gặp | Cách xử lý |
|---|---|
| Không tìm thấy mã … | Mã bị quét/nhập sai → sửa ô **Mã CB/SV** |
| Thiếu email người nhận | Nhập email vào ô **Email** |
| Email không hợp lệ | Sửa lại email |
| Lỗi gửi email: … | Lỗi máy chủ thư — thử gửi lại sau; nếu vẫn lỗi, báo bộ phận IT |
| Lỗi tạo chứng chỉ: … | Kiểm tra mẫu chứng chỉ của sự kiện |

Sửa xong bấm **Lưu & gửi lại** ở dòng đó. Bấm **Tải danh sách lỗi** để xuất Excel các dòng lỗi.

## 7. Gửi lại khi sinh viên báo không nhận được email

- **Một người:** bấm **Gửi lại** ở dòng của người đó. Hộp thoại hỏi *"Người này đã được gửi X lần, gửi lại?"* và cho **sửa email nhận** (khi sinh viên báo email khác) → **Gửi lại**.
- **Nhiều người:** tick chọn các dòng → bấm **Gửi lại các dòng đã chọn**. Dòng *Trùng* được bỏ qua.

Mỗi lần gửi lại, cột *Số lần gửi* tăng thêm 1. Nên nhắc sinh viên kiểm tra cả thư mục **Spam/Quảng cáo**.

## 8. Quay số trúng thưởng

Quay số ngay trên hệ thống, danh sách quay lấy từ những người **đã check-in** của sự kiện. Mỗi mã CB/SV chỉ có **1 suất** dù quét nhiều lần, và người gửi chứng chỉ lỗi vẫn được quay (lỗi email không liên quan đến việc có mặt).

**Vào trang:** *Chi tiết sự kiện* hoặc *Danh sách check-in* → nút **Quay số trúng thưởng**.

### 8.1. Chuẩn bị (trang quay số của sự kiện)
- **Giải thưởng:** nhập tên giải, số lượng rồi bấm **Thêm giải**. Cột *Thứ tự* quyết định thứ tự hiện trên màn hình. Giải đã có người trúng thì không giảm số lượng xuống dưới số đã trúng và không xoá được.
- **Cho phép một người trúng nhiều giải:** mặc định tắt (người đã trúng bị loại khỏi các lượt sau).
- **Hình nền màn hình quay số:** bấm **Chọn hình mới** (JPG/PNG/WEBP, tối đa 5MB, nên tỉ lệ 16:9). Mỗi sự kiện có hình riêng; chưa chọn thì dùng hình mặc định. **Khôi phục mặc định** sẽ xoá hình riêng.

### 8.2. Quay
1. Bấm **Mở màn hình quay số** (mở ở tab mới), bấm **Toàn màn hình** để chiếu. Màn hình **chỉ hiện mã**, không hiện họ tên.
2. Chọn **Giải** và **Số người mỗi lượt** (từ 1 đến số suất còn lại của giải), rồi bấm **QUAY** (hoặc phím Space).
3. Kết quả hiện ra nhưng chưa chốt: bấm **Lưu** để chốt cả lượt, hoặc **Quay lại** để bỏ cả lượt và quay lại. Đang có kết quả chờ thì không quay thêm được (kể cả ở tab khác); tải lại trang vẫn thấy kết quả đang chờ.
4. Nút **➜** ở góc dưới bên phải xem danh sách người đã trúng theo từng giải.

### 8.3. Người vắng mặt
Ở trang quay số của sự kiện, bấm **Huỷ (vắng mặt)** ở dòng của người đó. Họ được đưa lại vào danh sách quay; giải có thêm 1 suất trống để quay bổ sung. Bản huỷ vẫn được giữ ở mục *Đã huỷ* để đối chiếu.

### 8.4. Xuất kết quả
Bấm **Xuất Excel**: sheet *Trung thuong* gồm mã, họ tên, giờ trúng; sheet *Da huy* (nếu có) liệt kê người đã huỷ. Họ tên lấy theo thứ tự: tên sửa tay cho chứng chỉ → tên lúc check-in → tên đăng ký.
