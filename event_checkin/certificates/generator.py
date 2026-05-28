from datetime import datetime
from html import escape
from pathlib import Path


CERTIFICATE_WIDTH = 2048
CERTIFICATE_HEIGHT = 1433
BLUE = "#0646c8"
RED = "#d71920"
LIGHT_BLUE = "#66c8ef"
PALE_BLUE = "#e6f8ff"


def render_certificate_svg(student_name, ma_cbsv, don_vi, certificate_code, issued_at=None):
    issued_at = issued_at or datetime.utcnow()
    issue_date = issued_at.strftime("%d/%m/%Y")
    safe_name = escape(student_name or "")
    safe_code = escape(certificate_code)
    safe_unit = escape(don_vi or "")
    safe_id = escape(ma_cbsv or "")

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{CERTIFICATE_WIDTH}" height="{CERTIFICATE_HEIGHT}" viewBox="0 0 {CERTIFICATE_WIDTH} {CERTIFICATE_HEIGHT}">
  <rect width="100%" height="100%" fill="#ffffff"/>
  <text x="1024" y="250" text-anchor="middle" font-family="Arial, sans-serif" font-size="54" font-weight="900" fill="{BLUE}">TRƯỜNG ĐẠI HỌC KHOA HỌC XÃ HỘI VÀ NHÂN VĂN, ĐHQG-HCM</text>
  <text x="1024" y="325" text-anchor="middle" font-family="Arial, sans-serif" font-size="54" font-weight="900" fill="{BLUE}">TRUNG TÂM THÔNG TIN, THƯ VIỆN VÀ BẢO TÀNG</text>
  <text x="1024" y="490" text-anchor="middle" font-family="Arial, sans-serif" font-size="100" font-weight="900" fill="{RED}">GIẤY CHỨNG NHẬN</text>
  <text x="455" y="620" font-family="Arial, sans-serif" font-size="72" font-weight="900" fill="{BLUE}">Sinh viên:</text>
  <text x="930" y="620" font-family="Arial, sans-serif" font-size="72" font-weight="900" fill="{BLUE}">{safe_name}</text>
  <text x="455" y="730" font-family="Arial, sans-serif" font-size="72" font-weight="900" fill="{BLUE}">Mã số sinh viên:</text>
  <text x="1065" y="730" font-family="Arial, sans-serif" font-size="72" font-weight="900" fill="{BLUE}">{safe_id}</text>
  <text x="455" y="840" font-family="Arial, sans-serif" font-size="72" font-weight="900" fill="{BLUE}">Khoa:</text>
  <text x="680" y="840" font-family="Arial, sans-serif" font-size="72" font-weight="900" fill="{BLUE}">{safe_unit}</text>
  <text x="1024" y="960" text-anchor="middle" font-family="Georgia, serif" font-size="58" font-weight="700" fill="{RED}">Đã tham dự Lễ Khai mạc triển lãm “Mảnh ghép” và</text>
  <text x="1024" y="1045" text-anchor="middle" font-family="Georgia, serif" font-size="58" font-weight="700" fill="{RED}">Talkshow: “Ký ức từ những mảnh ghép di sản”</text>
  <text x="1510" y="1155" text-anchor="middle" font-family="Arial, sans-serif" font-size="48" font-weight="900" fill="{BLUE}">TP. Hồ Chí Minh, ngày {issued_at.day} tháng {issued_at.month} năm {issued_at.year}</text>
  <text x="1510" y="1240" text-anchor="middle" font-family="Arial, sans-serif" font-size="48" font-weight="900" fill="{BLUE}">GIÁM ĐỐC</text>
  <text x="1510" y="1400" text-anchor="middle" font-family="Arial, sans-serif" font-size="48" font-weight="900" fill="{BLUE}">TS.Bùi Thu Hằng</text>
  <text x="1024" y="1415" text-anchor="middle" font-family="Arial, sans-serif" font-size="16" fill="#8aa0bd">Mã chứng nhận: {safe_code} - Ngày cấp: {issue_date}</text>
</svg>"""


def save_svg_certificate(output_path, student_name, ma_cbsv, don_vi, certificate_code, issued_at=None):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        render_certificate_svg(student_name, ma_cbsv, don_vi, certificate_code, issued_at),
        encoding="utf-8",
    )
    return output_path


def save_png_certificate(output_path, student_name, ma_cbsv, don_vi, certificate_code, issued_at=None):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return None

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (CERTIFICATE_WIDTH, CERTIFICATE_HEIGHT), "#ffffff")
    draw = ImageDraw.Draw(image)

    def font(size, bold=False, serif=False, condensed=False):
        if serif:
            candidates = [
                "C:/Windows/Fonts/georgiab.ttf" if bold else "C:/Windows/Fonts/georgia.ttf",
                "C:/Windows/Fonts/timesbd.ttf" if bold else "C:/Windows/Fonts/times.ttf",
            ]
        elif condensed:
            candidates = [
                "C:/Windows/Fonts/impact.ttf",
                "C:/Windows/Fonts/arialbd.ttf",
                "C:/Windows/Fonts/Arial.ttf",
            ]
        else:
            candidates = [
                "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
                "C:/Windows/Fonts/Arial.ttf",
                "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
            ]
        for candidate in candidates:
            try:
                return ImageFont.truetype(candidate, size)
            except OSError:
                continue
        return ImageFont.load_default()

    def text_bbox(text, selected_font):
        return draw.textbbox((0, 0), text, font=selected_font)

    def fit_font(text, size, max_width, bold=False, serif=False, condensed=False):
        selected_size = size
        while selected_size > 20:
            selected_font = font(selected_size, bold=bold, serif=serif, condensed=condensed)
            bbox = text_bbox(text, selected_font)
            if bbox[2] - bbox[0] <= max_width:
                return selected_font
            selected_size -= 2
        return font(selected_size, bold=bold, serif=serif, condensed=condensed)

    def centered(text, y, size, fill, bold=False, serif=False, condensed=False, max_width=None):
        selected_font = fit_font(text, size, max_width, bold, serif, condensed) if max_width else font(size, bold, serif, condensed)
        bbox = draw.textbbox((0, 0), text, font=selected_font)
        x = (CERTIFICATE_WIDTH - (bbox[2] - bbox[0])) / 2
        draw.text((x, y), text, fill=fill, font=selected_font)

    def centered_at(text, center_x, y, size, fill, bold=False, serif=False, condensed=False, max_width=None):
        selected_font = fit_font(text, size, max_width, bold, serif, condensed) if max_width else font(size, bold, serif, condensed)
        bbox = draw.textbbox((0, 0), text, font=selected_font)
        draw.text((center_x - (bbox[2] - bbox[0]) / 2, y), text, fill=fill, font=selected_font)

    def left_text(text, x, y, size, fill, bold=False, serif=False, condensed=False, max_width=None):
        selected_font = fit_font(text, size, max_width, bold, serif, condensed) if max_width else font(size, bold, serif, condensed)
        draw.text((x, y), text, fill=fill, font=selected_font)

    def draw_halftone(origin_x, origin_y, cols, rows, direction):
        for row in range(rows):
            for col in range(cols):
                if direction == "tl":
                    strength = max(0, 1 - (row + col) / (cols + rows - 6))
                elif direction == "br":
                    strength = max(0, 1 - ((rows - row) + (cols - col)) / (cols + rows - 6))
                else:
                    strength = 0.4
                if strength <= 0:
                    continue
                radius = max(1, int(7 * strength))
                x = origin_x + col * 18
                y = origin_y + row * 18
                color = (0, 135, 210)
                draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)

    def draw_waves():
        waves = Image.new("RGBA", image.size, (255, 255, 255, 0))
        wave_draw = ImageDraw.Draw(waves)
        wave_draw.pieslice((-260, 915, 1130, 1785), 178, 342, fill=(61, 183, 226, 210))
        wave_draw.pieslice((-170, 960, 1045, 1740), 183, 348, fill=(126, 220, 240, 165))
        wave_draw.pieslice((-60, 1000, 950, 1680), 188, 350, fill=(209, 248, 245, 180))
        wave_draw.polygon([(0, 1433), (0, 1190), (260, 1270), (500, 1355), (720, 1433)], fill=(66, 196, 232, 185))
        image.alpha_composite(waves) if image.mode == "RGBA" else image.paste(Image.alpha_composite(Image.new("RGBA", image.size, (255, 255, 255, 0)), waves).convert("RGB"), mask=waves.split()[3])

    def draw_ussh_logo(cx, cy):
        draw.ellipse((cx - 72, cy - 55, cx + 72, cy + 55), fill="#1446a0", outline="#1446a0", width=2)
        draw.ellipse((cx - 62, cy - 45, cx + 62, cy + 45), fill="#d71920", outline="#ffd84d", width=2)
        for offset in (-35, -15, 5, 25):
            draw.arc((cx - 58, cy - 42 + offset, cx + 58, cy + 42 - offset), 0, 360, fill="#ffb347", width=1)
        for offset in (-40, -15, 15, 40):
            draw.line((cx + offset, cy - 42, cx - offset, cy + 42), fill="#ffb347", width=1)
        centered_font = font(24, bold=True)
        small_font = font(8, bold=True)
        draw.text((cx - 29, cy - 7), "USSH", fill="#fff04a", font=centered_font)
        draw.text((cx - 37, cy + 21), "VNU HCM", fill="#fff04a", font=small_font)

    def draw_cilm_logo(cx, cy):
        draw.ellipse((cx - 58, cy - 58, cx + 58, cy + 58), fill="#ffffff", outline="#0f5d91", width=2)
        draw.polygon([(cx - 43, cy + 8), (cx - 8, cy - 4), (cx - 8, cy + 14), (cx - 43, cy + 22)], fill="#1b75bb")
        draw.polygon([(cx + 43, cy + 8), (cx + 8, cy - 4), (cx + 8, cy + 14), (cx + 43, cy + 22)], fill="#1b75bb")
        draw.polygon([(cx - 28, cy - 20), (cx, cy - 5), (cx + 28, cy - 20), (cx + 6, cy + 26), (cx - 6, cy + 26)], fill="#2a9fd6")
        logo_font = font(22, bold=True, serif=True)
        draw.text((cx - 31, cy + 31), "CILM", fill="#1b4f72", font=logo_font)
        draw.line((cx - 45, cy + 57, cx + 45, cy + 57), fill="#1b4f72", width=2)

    def draw_signature(cx, cy):
        sig = Image.new("RGBA", image.size, (255, 255, 255, 0))
        sig_draw = ImageDraw.Draw(sig)
        blue = (26, 126, 194, 230)
        sig_draw.arc((cx - 110, cy - 55, cx - 25, cy + 35), 230, 65, fill=blue, width=4)
        sig_draw.line((cx - 60, cy - 20, cx - 20, cy + 65, cx + 10, cy - 30, cx + 38, cy + 50), fill=blue, width=4)
        sig_draw.arc((cx + 35, cy - 40, cx + 120, cy + 50), 120, 305, fill=blue, width=4)
        sig_draw.line((cx - 120, cy + 72, cx + 170, cy + 72), fill=blue, width=4)
        image.paste(sig.convert("RGB"), mask=sig.split()[3])

    issued_at = issued_at or datetime.utcnow()
    image = image.convert("RGBA")
    draw = ImageDraw.Draw(image)

    draw_halftone(0, 0, 23, 24, "tl")
    draw_halftone(1810, 1130, 16, 17, "br")
    draw_waves()
    draw_ussh_logo(965, 115)
    draw_cilm_logo(1138, 112)

    centered("TRƯỜNG ĐẠI HỌC KHOA HỌC XÃ HỘI VÀ NHÂN VĂN, ĐHQG-HCM", 205, 58, BLUE, True, condensed=True, max_width=1220)
    centered("TRUNG TÂM THÔNG TIN, THƯ VIỆN VÀ BẢO TÀNG", 285, 58, BLUE, True, condensed=True, max_width=1000)
    centered("GIẤY CHỨNG NHẬN", 405, 120, RED, True, condensed=True, max_width=760)

    label_x = 455
    value_x = 930
    left_text("Sinh viên:", label_x, 560, 78, BLUE, True, condensed=True)
    left_text(student_name or "", value_x, 560, 78, BLUE, True, condensed=True, max_width=575)
    left_text("Mã số sinh viên:", label_x, 670, 78, BLUE, True, condensed=True)
    left_text(str(ma_cbsv or ""), 1065, 670, 78, BLUE, True, condensed=True, max_width=420)
    left_text("Khoa:", label_x, 780, 78, BLUE, True, condensed=True)
    left_text(don_vi or "Công tác xã hội - Nhân học - Xã hội học", 680, 780, 78, BLUE, True, condensed=True, max_width=1180)

    centered('Đã tham dự Lễ Khai mạc triển lãm “Mảnh ghép” và', 910, 62, RED, True, serif=True, max_width=1170)
    centered('Talkshow: “Ký ức từ những mảnh ghép di sản”', 1000, 62, RED, True, serif=True, max_width=1170)
    date_line = f"TP. Hồ Chí Minh, ngày {issued_at.day} tháng {issued_at.month} năm {issued_at.year}"
    centered_at(date_line, 1510, 1115, 50, BLUE, True, condensed=True, max_width=760)
    centered_at("GIÁM ĐỐC", 1510, 1205, 50, BLUE, True, condensed=True, max_width=360)
    draw_signature(1510, 1270)
    centered_at("TS.Bùi Thu Hằng", 1510, 1355, 52, BLUE, True, condensed=True, max_width=520)
    centered(f"Mã chứng nhận: {certificate_code}", 1405, 18, "#7c97b8", False, max_width=540)

    image = image.convert("RGB")
    image.save(output_path)
    return output_path


def save_pdf_certificate(output_path, student_name, ma_cbsv, don_vi, certificate_code, issued_at=None):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    issued_at = issued_at or datetime.utcnow()
    lines = [
        "GIAY CHUNG NHAN",
        f"Ho ten: {student_name}",
        f"Ma CB/SV: {ma_cbsv}",
        f"Don vi: {don_vi or ''}",
        "Da tham gia va check-in thanh cong.",
        f"Ngay cap: {issued_at.strftime('%d/%m/%Y')}",
        f"Ma chung nhan: {certificate_code}",
    ]
    stream = ["BT", "/F1 28 Tf", "72 760 Td"]
    for index, line in enumerate(lines):
        size = 28 if index == 0 else 16
        stream.append(f"/F1 {size} Tf")
        stream.append(f"({line.replace('(', '[').replace(')', ']')}) Tj")
        stream.append("0 -42 Td")
    stream.append("ET")
    content = "\n".join(stream).encode("latin-1", errors="replace")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(content)).encode("ascii") + b" >>\nstream\n" + content + b"\nendstream",
    ]
    pdf = [b"%PDF-1.4\n"]
    offsets = []
    for number, obj in enumerate(objects, start=1):
        offsets.append(sum(len(part) for part in pdf))
        pdf.append(f"{number} 0 obj\n".encode("ascii") + obj + b"\nendobj\n")
    xref_at = sum(len(part) for part in pdf)
    pdf.append(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii"))
    for offset in offsets:
        pdf.append(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.append(f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode("ascii"))
    output_path.write_bytes(b"".join(pdf))
    return output_path
