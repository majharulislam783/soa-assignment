import re
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image as ReportImage,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Preformatted,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "report.md"
OUTPUT = ROOT / "report.pdf"
FONT_DIR = Path(r"C:\Windows\Fonts")


def register_fonts() -> tuple[str, str, str, str]:
    regular_path = FONT_DIR / "times.ttf"
    bold_path = FONT_DIR / "timesbd.ttf"
    italic_path = FONT_DIR / "timesi.ttf"
    bold_italic_path = FONT_DIR / "timesbi.ttf"
    paths = [regular_path, bold_path, italic_path, bold_italic_path]
    if all(path.exists() for path in paths):
        names = ("TimesNewRoman", "TimesNewRoman-Bold", "TimesNewRoman-Italic", "TimesNewRoman-BoldItalic")
        for name, path in zip(names, paths):
            pdfmetrics.registerFont(TTFont(name, str(path)))
        pdfmetrics.registerFontFamily(
            names[0], normal=names[0], bold=names[1], italic=names[2], boldItalic=names[3]
        )
        return names
    pdfmetrics.registerFontFamily(
        "Times-Roman",
        normal="Times-Roman",
        bold="Times-Bold",
        italic="Times-Italic",
        boldItalic="Times-BoldItalic",
    )
    return ("Times-Roman", "Times-Bold", "Times-Italic", "Times-BoldItalic")


FONT, FONT_BOLD, FONT_ITALIC, FONT_BOLD_ITALIC = register_fonts()


class NumberedCanvas:
    def __new__(cls, *args, **kwargs):
        from reportlab.pdfgen.canvas import Canvas

        class CanvasWithPageCount(Canvas):
            def __init__(self, *canvas_args, **canvas_kwargs):
                super().__init__(*canvas_args, **canvas_kwargs)
                self._saved_page_states = []

            def showPage(self):
                self._saved_page_states.append(dict(self.__dict__))
                self._startPage()

            def save(self):
                page_count = len(self._saved_page_states)
                for state in self._saved_page_states:
                    self.__dict__.update(state)
                    self.setFont(FONT, 9)
                    self.setFillColor(colors.HexColor("#555555"))
                    self.drawRightString(
                        A4[0] - 24 * mm,
                        14 * mm,
                        f"Page {self._pageNumber} of {page_count}",
                    )
                    Canvas.showPage(self)
                Canvas.save(self)

        return CanvasWithPageCount(*args, **kwargs)


class AssignmentDocTemplate(BaseDocTemplate):
    def __init__(self, filename: str, **kwargs):
        super().__init__(
            filename,
            pagesize=A4,
            leftMargin=25 * mm,
            rightMargin=25 * mm,
            topMargin=23 * mm,
            bottomMargin=23 * mm,
            title="MaltaShop: A Practical, Phased Move to Microservices",
            author="Majharul Islam",
            **kwargs,
        )
        frame = Frame(
            self.leftMargin,
            self.bottomMargin,
            self.width,
            self.height,
            id="normal",
            leftPadding=0,
            rightPadding=0,
            topPadding=0,
            bottomPadding=0,
        )
        self.addPageTemplates([PageTemplate(id="main", frames=frame)])
        self.heading_index = 0

    def beforeDocument(self):
        self.heading_index = 0

    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and flowable.style.name in (
            "ReportHeading1",
            "ReportHeading2",
        ):
            level = 0 if flowable.style.name == "ReportHeading1" else 1
            text = flowable.getPlainText()
            key = f"toc-{self.heading_index}"
            self.heading_index += 1
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(text, key, level=level, closed=(level == 0))
            self.notify("TOCEntry", (level, text, self.page, key))


def inline_markup(text: str) -> str:
    text = escape(text)
    text = re.sub(r"`([^`]+)`", r'<font name="Courier">\1</font>', text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        r'<link href="\2" color="#145DA0">\1</link>',
        text,
    )
    return text


def word_count(markdown: str) -> int:
    body = markdown.split("## 1. Architectural Evolution and Synthesis", 1)[1]
    body = body.split("\n## Appendix A", 1)[0]
    body = re.sub(r"```.*?```", " ", body, flags=re.S)
    body = re.sub(r"^#{1,6}\s+", "", body, flags=re.M)
    return len(re.findall(r"\b[\w’'-]+\b", body))


def make_styles():
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            "ReportBody",
            parent=styles["BodyText"],
            fontName=FONT,
            fontSize=12,
            leading=18,
            alignment=TA_LEFT,
            spaceAfter=7,
            splitLongWords=True,
        )
    )
    styles.add(
        ParagraphStyle(
            "ReportHeading1",
            parent=styles["Heading1"],
            fontName=FONT_BOLD,
            fontSize=15,
            leading=20,
            textColor=colors.HexColor("#16324F"),
            spaceBefore=12,
            spaceAfter=9,
            keepWithNext=True,
        )
    )
    styles.add(
        ParagraphStyle(
            "ReportHeading2",
            parent=styles["Heading2"],
            fontName=FONT_BOLD,
            fontSize=12,
            leading=16,
            textColor=colors.HexColor("#1D4E73"),
            spaceBefore=9,
            spaceAfter=6,
            keepWithNext=True,
        )
    )
    styles.add(
        ParagraphStyle(
            "ReportTableCell",
            parent=styles["ReportBody"],
            fontSize=10,
            leading=13,
            spaceAfter=0,
        )
    )
    styles.add(
        ParagraphStyle(
            "ReportTableHeader",
            parent=styles["ReportTableCell"],
            fontName=FONT_BOLD,
            textColor=colors.white,
        )
    )
    styles.add(
        ParagraphStyle(
            "ReportCodeBlock",
            fontName="Courier",
            fontSize=7.3,
            leading=9,
            leftIndent=4,
            rightIndent=4,
            borderColor=colors.HexColor("#D4DCE5"),
            borderWidth=0.5,
            borderPadding=6,
            backColor=colors.HexColor("#F5F7FA"),
            spaceBefore=4,
            spaceAfter=9,
        )
    )
    styles.add(
        ParagraphStyle(
            "CoverTitle",
            fontName=FONT_BOLD,
            fontSize=22,
            leading=28,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#16324F"),
            spaceAfter=20,
        )
    )
    styles.add(
        ParagraphStyle(
            "CoverSub",
            fontName=FONT,
            fontSize=14,
            leading=20,
            alignment=TA_CENTER,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            "TOCTitle",
            fontName=FONT_BOLD,
            fontSize=18,
            leading=23,
            textColor=colors.HexColor("#16324F"),
            spaceAfter=16,
        )
    )
    styles.add(
        ParagraphStyle(
            "ReportCaption",
            fontName=FONT_ITALIC,
            fontSize=9,
            leading=12,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#555555"),
            spaceBefore=4,
            spaceAfter=10,
        )
    )
    return styles


def parse_table(lines, styles, available_width):
    rows = []
    for line in lines:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue
        rows.append(cells)
    if not rows:
        return None
    column_count = max(len(row) for row in rows)
    data = []
    for row_index, row in enumerate(rows):
        row = row + [""] * (column_count - len(row))
        style = (
            styles["ReportTableHeader"]
            if row_index == 0
            else styles["ReportTableCell"]
        )
        data.append([Paragraph(inline_markup(cell), style) for cell in row])
    table = Table(
        data,
        colWidths=[available_width / column_count] * column_count,
        repeatRows=1,
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#16324F")),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#AAB7C4")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F6F9")]),
            ]
        )
    )
    return table


def build_story(markdown: str, styles):
    story = []
    count = word_count(markdown)
    story.append(Spacer(1, 34 * mm))
    story.append(
        Paragraph(
            "MaltaShop: A Practical,<br/>Phased Move to Microservices",
            styles["CoverTitle"],
        )
    )
    story.append(Paragraph("Unit 5: Service-Oriented Architecture and Microservices Fundamentals", styles["CoverSub"]))
    story.append(Spacer(1, 18 * mm))
    cover_lines = [
        "<b>Student:</b> Majharul Islam",
        "<b>Student ID:</b> 11718",
        "<b>Institution:</b> Learnkey Institute, Malta",
        "<b>Lecturer:</b> Believe Ayodele",
        "<b>Submission date:</b> 22 October 2026",
        f"<b>Report body word count:</b> {count:,} (references and contents excluded)",
    ]
    for line in cover_lines:
        story.append(Paragraph(line, styles["CoverSub"]))
    story.append(PageBreak())
    story.append(Paragraph("Contents", styles["TOCTitle"]))
    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle(
            "TOCLevel0",
            fontName=FONT,
            fontSize=11,
            leading=16,
            leftIndent=0,
            firstLineIndent=0,
            spaceBefore=5,
        ),
        ParagraphStyle(
            "TOCLevel1",
            fontName=FONT,
            fontSize=9.5,
            leading=13,
            leftIndent=16,
            firstLineIndent=0,
        ),
    ]
    story.append(toc)
    story.append(PageBreak())

    lines = markdown.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("## 1. Architectural"))
    end = next(i for i, line in enumerate(lines) if line.strip() == "## Contents")
    start = min(start, end) if start < end else start
    lines = lines[start:]

    i = 0
    paragraph_lines = []
    in_code = False
    code_lines = []
    table_lines = []

    def flush_paragraph():
        nonlocal paragraph_lines
        if paragraph_lines:
            text = " ".join(line.strip() for line in paragraph_lines).strip()
            if text:
                story.append(Paragraph(inline_markup(text), styles["ReportBody"]))
            paragraph_lines = []

    def flush_table():
        nonlocal table_lines
        if table_lines:
            table = parse_table(table_lines, styles, A4[0] - 50 * mm)
            if table:
                story.append(Spacer(1, 3))
                story.append(table)
                story.append(Spacer(1, 8))
            table_lines = []

    while i < len(lines):
        line = lines[i]
        if line.strip() == "## Contents":
            break
        if line.startswith("```"):
            flush_paragraph()
            flush_table()
            if in_code:
                story.append(Preformatted("\n".join(code_lines), styles["ReportCodeBlock"]))
                code_lines = []
                in_code = False
            else:
                in_code = True
            i += 1
            continue
        if in_code:
            code_lines.append(line)
            i += 1
            continue
        image_match = re.fullmatch(r"!\[([^\]]*)\]\(([^)]+)\)", line.strip())
        if image_match:
            flush_paragraph()
            flush_table()
            caption, source = image_match.groups()
            image_path = (ROOT / source).resolve()
            try:
                image_path.relative_to(ROOT.resolve())
            except ValueError as error:
                raise ValueError("Report images must be inside the assignment folder") from error
            if not image_path.is_file():
                raise FileNotFoundError(f"Report image not found: {image_path}")
            image = ReportImage(str(image_path))
            scale = min(
                (A4[0] - 50 * mm) / image.imageWidth,
                (A4[1] - 60 * mm) / image.imageHeight,
            )
            image.drawWidth = image.imageWidth * scale
            image.drawHeight = image.imageHeight * scale
            image.hAlign = "CENTER"
            story.append(KeepTogether([image, Paragraph(inline_markup(caption), styles["ReportCaption"])]))
            i += 1
            continue
        if line.startswith("|"):
            flush_paragraph()
            table_lines.append(line)
            i += 1
            continue
        flush_table()
        if line.startswith("# "):
            flush_paragraph()
            i += 1
            continue
        if line.startswith("## "):
            flush_paragraph()
            title = line[3:].strip()
            if title == "References":
                story.append(PageBreak())
            story.append(Paragraph(inline_markup(title), styles["ReportHeading1"]))
        elif line.startswith("### "):
            flush_paragraph()
            story.append(Paragraph(inline_markup(line[4:].strip()), styles["ReportHeading2"]))
        elif line.startswith("#### "):
            flush_paragraph()
            story.append(Paragraph(inline_markup(line[5:].strip()), styles["ReportHeading2"]))
        elif line.strip():
            paragraph_lines.append(line)
        else:
            flush_paragraph()
        i += 1
    flush_paragraph()
    flush_table()
    return story, count


def main():
    markdown = SOURCE.read_text(encoding="utf-8")
    styles = make_styles()
    story, count = build_story(markdown, styles)
    doc = AssignmentDocTemplate(str(OUTPUT))
    doc.multiBuild(story, canvasmaker=NumberedCanvas)
    print(f"Created {OUTPUT} ({count:,} report-body words)")


if __name__ == "__main__":
    main()
