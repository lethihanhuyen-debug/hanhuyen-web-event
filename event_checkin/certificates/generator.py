from datetime import datetime
from html import escape
from pathlib import Path

from flask import current_app

CERTIFICATE_WIDTH = 2048
CERTIFICATE_HEIGHT = 1433
BLUE = "#0646c8"
RED = "#d71920"
LIGHT_BLUE = "#66c8ef"
PALE_BLUE = "#e6f8ff"


def resolve_font(size, bold=False, font_path=None, static_folder=None):
    try:
        from PIL import ImageFont
    except ImportError as error:
        raise RuntimeError("Pillow chưa được cài đặt, không thể tải font.") from error

    if static_folder is None:
        static_folder = current_app.static_folder

    candidates = []
    if font_path:
        font_path_obj = Path(font_path)
        if not font_path_obj.is_absolute():
            font_path_obj = Path(static_folder) / font_path_obj
        if font_path_obj.exists():
            candidates.append(font_path_obj)

    font_dir = Path(static_folder) / "fonts"
    candidates.append(font_dir / ("Roboto-Bold.ttf" if bold else "Roboto-Regular.ttf"))

    candidates.extend([
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/Arial.ttf",
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
    ])

    tried = []
    for candidate in candidates:
        try:
            tried.append(str(candidate))
            return ImageFont.truetype(str(candidate), size)
        except OSError:
            continue

    raise RuntimeError(
        "Không tìm thấy font Unicode hợp lệ, chữ tiếng Việt có thể hiển thị sai. "
        "Hãy thêm static/fonts/Roboto-Regular.ttf và static/fonts/Roboto-Bold.ttf, hoặc cung cấp font_file hợp lệ. "
        f"Đã thử: {', '.join(tried)}"
    )


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


def save_png_certificate(output_path, student_name, ma_cbsv, don_vi, certificate_code, issued_at=None, template_path=None, layout=None):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return None

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not template_path or not Path(template_path).exists():
        # Không tự tạo nền trắng hoặc đồ họa mẫu nếu không có ảnh nền do người dùng tải lên.
        return None

    image = Image.open(template_path).convert("RGBA")
    draw = ImageDraw.Draw(image)

    def font(size, bold=False, serif=False, condensed=False, font_path=None):
        return resolve_font(size, bold=bold, font_path=font_path, static_folder=current_app.static_folder)

    def text_bbox(text, selected_font):
        return draw.textbbox((0, 0), text, font=selected_font)

    def fit_font(text, size, max_width, bold=False, serif=False, condensed=False, font_path=None):
        selected_size = size
        while selected_size > 20:
            selected_font = font(selected_size, bold=bold, serif=serif, condensed=condensed, font_path=font_path)
            bbox = text_bbox(text, selected_font)
            if bbox[2] - bbox[0] <= max_width:
                return selected_font
            selected_size -= 2
        return font(selected_size, bold=bold, serif=serif, condensed=condensed, font_path=font_path)

    def draw_template_fields(values, layout_config, image_width, image_height):
        layout_meta = layout_config.get("_meta") if isinstance(layout_config, dict) else None
        base_width = int(layout_meta.get("width")) if isinstance(layout_config, dict) and layout_meta.get("width") else CERTIFICATE_WIDTH
        base_height = int(layout_meta.get("height")) if isinstance(layout_config, dict) and layout_meta.get("height") else CERTIFICATE_HEIGHT
        scale_x = image_width / max(base_width, 1)
        scale_y = image_height / max(base_height, 1)

        default_style = {"size": 48, "color": BLUE, "bold": True, "align": "left"}
        anchor_map = {"left": "lt", "center": "mt", "right": "rt"}

        for field, text_value in values.items():
            saved_config = layout_config.get(field)
            if not isinstance(saved_config, dict):
                continue
            if saved_config.get("x") is None or saved_config.get("y") is None:
                continue

            field_config = {**default_style, **saved_config}
            align = str(field_config.get("align", "left")).lower()
            if align not in anchor_map:
                align = "left"

            x = 900
            y = 680
            size = max(20, int(round(field_config.get("size", default_style["size"]) * min(scale_x, scale_y))))
            fill = field_config.get("color", default_style["color"])
            bold_flag = bool(field_config.get("bold", default_style["bold"]))
            font_path = field_config.get("font_path") or field_config.get("font_file")

            selected_font = resolve_font(size, bold=bold_flag, font_path=font_path, static_folder=current_app.static_folder)
            anchor = anchor_map[align]
            draw.text((x, y), text_value, fill=fill, font=selected_font, anchor=anchor)

    issued_at = issued_at or datetime.utcnow()
    values = {
        "student_name": student_name or "",
        "ma_cbsv": str(ma_cbsv or ""),
        "don_vi": don_vi or "",
        "issue_date": f"TP. Hồ Chí Minh, ngày {issued_at.day} tháng {issued_at.month} năm {issued_at.year}",
        "certificate_code": f"Mã chứng nhận: {certificate_code}",
    }
    try:
        draw_template_fields(values, layout or {}, image.width, image.height)
    except RuntimeError as exc:
        current_app.logger.error('Không thể render chứng chỉ với template font: %s', exc, exc_info=True)
        return None

    image.convert("RGB").save(output_path)
    return output_path


def save_pdf_certificate(output_path, student_name, ma_cbsv, don_vi, certificate_code, issued_at=None, template_path=None, layout=None):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    issued_at = issued_at or datetime.utcnow()

    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None

    if not template_path or not Path(template_path).exists():
        return None

    image = Image.open(template_path).convert("RGB")
    draw = ImageDraw.Draw(image)
    layout_meta = layout.get("_meta") if isinstance(layout, dict) else None
    base_width = int(layout_meta.get("width")) if isinstance(layout_meta, dict) and layout_meta.get("width") else CERTIFICATE_WIDTH
    base_height = int(layout_meta.get("height")) if isinstance(layout_meta, dict) and layout_meta.get("height") else CERTIFICATE_HEIGHT
    scale_x = image.width / max(base_width, 1)
    scale_y = image.height / max(base_height, 1)
    scale_font = min(scale_x, scale_y)

    fallback_layout = {
        "student_name": {"x": 930, "y": 560, "size": 78, "color": BLUE, "bold": True, "align": "left"},
        "ma_cbsv": {"x": 1065, "y": 670, "size": 78, "color": BLUE, "bold": True, "align": "left"},
        "don_vi": {"x": 680, "y": 780, "size": 78, "color": BLUE, "bold": True, "align": "left"},
        "issue_date": {"x": 1120, "y": 1115, "size": 50, "color": BLUE, "bold": True, "align": "left"},
        "certificate_code": {"x": 760, "y": 1405, "size": 18, "color": "#7c97b8", "bold": False, "align": "left"},
    }
    anchor_map = {"left": "lt", "center": "mt", "right": "rt"}

    values = {
        "student_name": student_name or "",
        "ma_cbsv": str(ma_cbsv or ""),
        "don_vi": don_vi or "",
        "issue_date": f"TP. Hồ Chí Minh, ngày {issued_at.day} tháng {issued_at.month} năm {issued_at.year}",
        "certificate_code": f"Mã chứng nhận: {certificate_code}",
    }

    for field, text_value in values.items():
        config = fallback_layout[field].copy()
        if isinstance(layout, dict) and isinstance(layout.get(field), dict):
            config.update(layout.get(field))
        align = str(config.get("align", "left")).lower()
        if align not in anchor_map:
            align = "left"
        x = int(config.get("x", fallback_layout[field]["x"]) * scale_x)
        y = int(config.get("y", fallback_layout[field]["y"]) * scale_y)
        size = max(10, int(round(config.get("size", fallback_layout[field]["size"]) * scale_font)))
        fill = config.get("color", fallback_layout[field]["color"])
        bold_flag = bool(config.get("bold", fallback_layout[field]["bold"]))
        font_path = config.get("font_path") or config.get("font_file")
        try:
            selected_font = resolve_font(size, bold=bold_flag, font_path=font_path, static_folder=current_app.static_folder)
        except RuntimeError:
            return None
        anchor = anchor_map[align]
        draw.text((x, y), text_value, fill=fill, font=selected_font, anchor=anchor)

    image.save(output_path, "PDF", resolution=72.0, quality=95, optimize=True)
    return output_path
