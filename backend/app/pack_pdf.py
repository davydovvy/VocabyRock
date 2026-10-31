"""Compact, printer-friendly pack sheets."""

import io
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from .config import get_settings
from .models import Pack, Word

FONT_DIR = Path(__file__).parent / "assets" / "fonts"
PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 27
GAP = 8
INK = (0.15, 0.17, 0.21)
MUTED = (0.41, 0.43, 0.48)
RULE = (0.79, 0.80, 0.82)
TOP = PAGE_HEIGHT - 74
BOTTOM = 31
ENGLISH_SIZE = 11
IPA_SIZE = 9
RUSSIAN_SIZE = 10
TEST_SIZE = 12


def _register_fonts():
    if "PackSans" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("PackSans", str(FONT_DIR / "NotoSans-Regular.ttf")))
        pdfmetrics.registerFont(TTFont("PackSans-Bold", str(FONT_DIR / "NotoSans-Bold.ttf")))


def _wrap(text: str, font: str, size: float, width: float) -> list[str]:
    lines: list[str] = []
    line = ""
    for word in text.split():
        candidate = f"{line} {word}" if line else word
        if pdfmetrics.stringWidth(candidate, font, size) <= width:
            line = candidate
            continue
        if line:
            lines.append(line)
            line = ""
        while pdfmetrics.stringWidth(word, font, size) > width:
            cutoff = len(word)
            while cutoff > 1 and pdfmetrics.stringWidth(word[:cutoff], font, size) > width:
                cutoff -= 1
            lines.append(word[:cutoff])
            word = word[cutoff:]
        line = word
    if line:
        lines.append(line)
    return lines


def _picture(word: Word):
    if not word.picture or not word.picture.startswith("/media/"):
        return None
    path = get_settings().data_dir / "images" / Path(word.picture).name
    try:
        with Image.open(path) as source:
            source.thumbnail((180, 180), Image.Resampling.LANCZOS)
            image = source.convert("RGB")
            return ImageReader(image)
    except (FileNotFoundError, UnidentifiedImageError, OSError):
        return None


def _image_box(pdf: canvas.Canvas, word: Word, x: float, y: float, size: float):
    image = _picture(word)
    if image:
        pdf.drawImage(image, x, y, size, size, preserveAspectRatio=True, anchor="c")
    else:
        pdf.setStrokeColorRGB(*RULE)
        pdf.rect(x, y, size, size, stroke=1, fill=0)


def _header(pdf: canvas.Canvas, pack: Pack, variant: str, page: int):
    pdf.setFillColorRGB(*INK)
    pdf.setFont("PackSans-Bold", 17)
    if variant == "reference":
        title = pack.name
        while pdfmetrics.stringWidth(title, "PackSans-Bold", 17) > PAGE_WIDTH - 2 * MARGIN:
            title = title[:-2] + "…"
        pdf.drawString(MARGIN, PAGE_HEIGHT - 39, title)
        pdf.setFillColorRGB(*MUTED)
        pdf.setFont("PackSans", 10.5)
        pdf.drawString(MARGIN, PAGE_HEIGHT - 55, f"{len(pack.words)} words")
    else:
        pdf.drawString(MARGIN, PAGE_HEIGHT - 39, "Письменный тест")
        pdf.setFillColorRGB(*MUTED)
        pdf.setFont("PackSans", 10)
        pdf.drawRightString(
            PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 39, "Имя: __________   Дата: __________"
        )
    pdf.setStrokeColorRGB(*RULE)
    pdf.line(MARGIN, PAGE_HEIGHT - 67, PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 67)
    pdf.setFillColorRGB(*MUTED)
    pdf.setFont("PackSans", 9)
    pdf.drawRightString(PAGE_WIDTH - MARGIN, 18, str(page))


def _reference_lines(word: Word, text_width: float):
    return (
        _wrap(word.english, "PackSans-Bold", ENGLISH_SIZE, text_width),
        _wrap(word.ipa or "", "PackSans", IPA_SIZE, text_width),
        _wrap(", ".join(word.translations), "PackSans", RUSSIAN_SIZE, text_width),
    )


def _row_height(words: list[Word], variant: str, cell_width: float, image_size: float) -> float:
    heights = []
    for word in words:
        if variant == "reference":
            lines = _reference_lines(word, cell_width - image_size - 18)
            heights.append(
                max(
                    image_size + 12,
                    10 + len(lines[0]) * 14 + len(lines[1]) * 12 + len(lines[2]) * 13,
                )
            )
        else:
            russian = _wrap(
                ", ".join(word.translations),
                "PackSans-Bold",
                TEST_SIZE,
                cell_width - image_size - 18,
            )
            heights.append(max(image_size + 16, 44 + (len(russian) - 1) * 15))
    return max(heights)


def _draw_reference(
    pdf: canvas.Canvas,
    word: Word,
    x: float,
    top: float,
    width: float,
    height: float,
    image_size: float,
):
    _image_box(pdf, word, x + 3, top - (height + image_size) / 2, image_size)
    english, ipa, russian = _reference_lines(word, width - image_size - 18)
    text_x = x + image_size + 13
    text_height = len(english) * 14 + len(ipa) * 12 + len(russian) * 13
    baseline = top - (height - text_height) / 2 - 11
    for lines, font, size, leading, color in (
        (english, "PackSans-Bold", ENGLISH_SIZE, 14, INK),
        (ipa, "PackSans", IPA_SIZE, 12, MUTED),
        (russian, "PackSans", RUSSIAN_SIZE, 13, INK),
    ):
        pdf.setFont(font, size)
        pdf.setFillColorRGB(*color)
        for line in lines:
            pdf.drawString(text_x, baseline, line)
            baseline -= leading
    pdf.setStrokeColorRGB(*RULE)
    pdf.line(x, top - height + 2, x + width, top - height + 2)


def _draw_test(
    pdf: canvas.Canvas,
    word: Word,
    x: float,
    top: float,
    width: float,
    height: float,
    image_size: float,
):
    _image_box(pdf, word, x + 3, top - (height + image_size) / 2, image_size)
    text_x = x + image_size + 14
    russian = _wrap(
        ", ".join(word.translations), "PackSans-Bold", TEST_SIZE, width - image_size - 18
    )
    base_height = max(image_size + 16, 44 + (len(russian) - 1) * 15)
    inset = (height - base_height) / 2
    pdf.setFillColorRGB(*INK)
    pdf.setFont("PackSans-Bold", TEST_SIZE)
    for index, line in enumerate(russian):
        pdf.drawString(text_x, top - 15 - inset - index * 15, line)
    pdf.setStrokeColorRGB(*MUTED)
    pdf.line(text_x, top - height + 16 + inset, x + width - 5, top - height + 16 + inset)
    pdf.setStrokeColorRGB(*RULE)
    pdf.line(x, top - height + 2, x + width, top - height + 2)


def render_pack(pack: Pack, variant: str) -> bytes:
    if variant not in {"reference", "test"}:
        raise ValueError("Unknown pack sheet")
    _register_fonts()
    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=A4, pageCompression=1)
    pdf.setTitle(f"{pack.name} - {'words' if variant == 'reference' else 'writing test'}")
    pdf.setAuthor("VacabyRock")
    words = [item.word for item in pack.words]
    columns = 2
    image_size = 62 if variant == "reference" else 55
    cell_width = (PAGE_WIDTH - 2 * MARGIN - (columns - 1) * GAP) / columns
    rows = [words[start : start + columns] for start in range(0, len(words), columns)]
    heights = [_row_height(row, variant, cell_width, image_size) for row in rows]
    if variant == "reference" and sum(heights) + len(heights) * 3 > TOP - BOTTOM:
        columns = 3
        image_size = 43
        cell_width = (PAGE_WIDTH - 2 * MARGIN - (columns - 1) * GAP) / columns
        rows = [words[start : start + columns] for start in range(0, len(words), columns)]
        heights = [_row_height(row, variant, cell_width, image_size) for row in rows]
    if heights and sum(heights) + len(heights) * 3 <= TOP - BOTTOM:
        extra = min(60, (TOP - BOTTOM - sum(heights) - len(heights) * 3) / len(heights))
        heights = [height + extra for height in heights]
    top = TOP
    page = 1
    _header(pdf, pack, variant, page)
    for row, height in zip(rows, heights):
        if top - height < BOTTOM:
            pdf.showPage()
            page += 1
            _header(pdf, pack, variant, page)
            top = TOP
        for column, word in enumerate(row):
            x = MARGIN + column * (cell_width + GAP)
            if variant == "reference":
                _draw_reference(pdf, word, x, top, cell_width, height, image_size)
            else:
                _draw_test(pdf, word, x, top, cell_width, height, image_size)
        top -= height + 3
    pdf.save()
    return output.getvalue()
