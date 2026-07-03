import logging
from pathlib import Path

from flask import current_app, has_app_context
from PIL import ImageFont


logger = logging.getLogger(__name__)

FONT_WARNING = "Khong tim thay font Unicode, chu tieng Viet co the hien thi sai"
REQUIRED_FONT_FILES = ("Roboto-Regular.ttf", "Roboto-Bold.ttf")


def _static_folder():
    if has_app_context() and current_app.static_folder:
        return Path(current_app.static_folder)
    return Path(__file__).resolve().parents[1] / "static"


def _font_file(filename):
    return _static_folder() / "fonts" / filename


def _custom_font_candidates(font_path):
    if not font_path:
        return []

    path = Path(font_path)
    if path.is_absolute():
        return [path]

    candidates = [_static_folder() / path]
    if has_app_context():
        candidates.append(Path(current_app.root_path) / path)
    candidates.append(Path.cwd() / path)
    return candidates


def _bundled_font_candidates(bold=False, serif=False):
    if serif:
        return [
            _font_file("NotoSerif-Bold.ttf" if bold else "NotoSerif-Regular.ttf"),
            _font_file("Roboto-Bold.ttf" if bold else "Roboto-Regular.ttf"),
        ]
    return [
        _font_file("Roboto-Bold.ttf" if bold else "Roboto-Regular.ttf"),
    ]


def _system_font_candidates(bold=False, serif=False, condensed=False):
    if serif:
        return [
            Path("C:/Windows/Fonts/georgiab.ttf" if bold else "C:/Windows/Fonts/georgia.ttf"),
            Path("C:/Windows/Fonts/timesbd.ttf" if bold else "C:/Windows/Fonts/times.ttf"),
            Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
            Path("C:/Windows/Fonts/Arial.ttf"),
        ]
    if condensed:
        return [
            Path("C:/Windows/Fonts/impact.ttf"),
            Path("C:/Windows/Fonts/arialbd.ttf"),
            Path("C:/Windows/Fonts/Arial.ttf"),
        ]
    return [
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/Arial.ttf"),
    ]


def _dejavu_candidates(bold=False):
    return [
        Path("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"),
    ]


def _load_first_existing(candidates, size):
    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            return ImageFont.truetype(str(candidate), size)
        except OSError as exc:
            logger.warning("Khong the load font %s: %s", candidate, exc)
    return None


def resolve_font(size, bold=False, serif=False, condensed=False, font_path=None):
    custom_font = _load_first_existing(_custom_font_candidates(font_path), size)
    if custom_font:
        return custom_font

    bundled_font = _load_first_existing(_bundled_font_candidates(bold=bold, serif=serif), size)
    if bundled_font:
        return bundled_font

    fallback_font = _load_first_existing(
        [
            *_system_font_candidates(bold=bold, serif=serif, condensed=condensed),
            *_dejavu_candidates(bold=bold),
        ],
        size,
    )
    if fallback_font:
        return fallback_font

    logger.warning(FONT_WARNING)
    raise FileNotFoundError(FONT_WARNING)


def warn_missing_required_fonts(app=None):
    static_folder = Path(app.static_folder) if app and app.static_folder else _static_folder()
    missing_fonts = [
        str(static_folder / "fonts" / filename)
        for filename in REQUIRED_FONT_FILES
        if not (static_folder / "fonts" / filename).exists()
    ]
    if missing_fonts:
        target_logger = app.logger if app else logger
        target_logger.warning(
            "%s. Can bo sung cac file font: %s",
            FONT_WARNING,
            ", ".join(missing_fonts),
        )
