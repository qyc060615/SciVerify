"""Generate real PDF and DOCX files from the complete, flattened report snapshot."""
import re
from io import BytesIO
from pathlib import Path
from threading import Lock
from typing import Literal
from xml.sax.saxutils import escape

from pydantic import BaseModel, ConfigDict, Field


class ReportBlock(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['title', 'heading', 'subheading', 'body', 'quote', 'code', 'pagebreak']
    text: str = Field(default='', max_length=100000)
    status: str | None = Field(default=None, max_length=120)


class ReportExportRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    simplify_evidence: bool = False
    format: Literal['pdf', 'docx']
    title: str = Field(min_length=1, max_length=300)
    blocks: list[ReportBlock] = Field(min_length=1, max_length=20000)


_FONT_LOCK = Lock()
_INVALID_XML_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")


def _status_color(status):
    label = status.split(' (', 1)[0].strip().lower()
    if label == 'supported':
        return '15803D'
    if label in {'contradict', 'contradicted'}:
        return 'DC2626'
    return 'CA8A04'


def _pdf_font():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont, TTFError
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    with _FONT_LOCK:
        if 'ReportUnicode' in pdfmetrics.getRegisteredFontNames():
            return 'ReportUnicode'
        # Embed a locally installed Unicode font when available; never fetch fonts.
        for path in ['C:/Windows/Fonts/msyh.ttc', 'C:/Windows/Fonts/simsun.ttc',
                     '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']:
            if Path(path).is_file():
                try:
                    pdfmetrics.registerFont(TTFont('ReportUnicode', path, subfontIndex=0))
                    return 'ReportUnicode'
                except (TTFError, OSError):
                    continue
        if 'STSong-Light' not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
        return 'STSong-Light'


def _pdf_text(text, font):
    from reportlab.pdfbase import pdfmetrics
    face = pdfmetrics.getFont(font).face
    glyphs = getattr(face, 'charToGlyph', None)
    if glyphs:
        # Preserve unsupported symbols explicitly instead of silently dropping them.
        text = ''.join(c if c in '\n\t\r' or ord(c) in glyphs else f'[U+{ord(c):04X}]' for c in text)
    return escape(text).replace('\n', '<br/>')


def render_pdf(report):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
    output = BytesIO()
    font = _pdf_font()
    base = ParagraphStyle('body', fontName=font, fontSize=9.5, leading=15,
                          textColor=colors.HexColor('#172b3a'), spaceAfter=6,
                          wordWrap='CJK', alignment=TA_LEFT)
    styles = {
        'body': base,
        'title': ParagraphStyle('title', parent=base, fontSize=22, leading=29, spaceAfter=18, keepWithNext=True),
        'heading': ParagraphStyle('heading', parent=base, fontSize=14, leading=20, spaceBefore=12, spaceAfter=8, textColor=colors.HexColor('#14697c'), keepWithNext=True),
        'subheading': ParagraphStyle('subheading', parent=base, fontSize=11, leading=17, spaceBefore=9, spaceAfter=5, keepWithNext=True),
        'quote': ParagraphStyle('quote', parent=base, leftIndent=12, rightIndent=8, backColor=colors.HexColor('#f3f7f9'), borderPadding=7, spaceBefore=8, spaceAfter=12),
        'code': ParagraphStyle('code', parent=base, fontSize=8, leading=12, backColor=colors.HexColor('#f5f7f9'), borderPadding=6, spaceBefore=6, spaceAfter=10),
    }
    reference_style = ParagraphStyle('reference', parent=styles['subheading'], spaceBefore=24, spaceAfter=8)
    story = []
    for block in report.blocks:
        if block.kind == 'pagebreak':
            if story and not isinstance(story[-1], PageBreak):
                story.append(PageBreak())
            continue
        if not block.text.strip():
            continue
        if block.kind == 'heading' and block.status:
            right = ParagraphStyle('claim-status', parent=base, alignment=TA_RIGHT, fontSize=10, textColor=colors.HexColor('#' + _status_color(block.status)))
            row = Table([[Paragraph(_pdf_text(block.text, font), styles['heading']), Paragraph(_pdf_text(block.status, font), right)]], colWidths=[65 * mm, 111 * mm])
            row.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('LEFTPADDING', (0,0), (-1,-1), 0), ('RIGHTPADDING', (0,0), (-1,-1), 0)]))
            row.keepWithNext = True
            story.append(row)
            continue
        # Split very long diagnostics into bounded paragraphs so they paginate.
        parts = [block.text[i:i + 6000] for i in range(0, len(block.text), 6000)]
        for part in parts:
            style = reference_style if block.kind == 'subheading' and re.match(r'^Reference(?: \d+)?:', block.text) else styles[block.kind]
            story.append(Paragraph(_pdf_text(part, font), style))
    if not story:
        story.append(Spacer(1, 1))
    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(font, 8)
        canvas.setFillColor(colors.HexColor('#667788'))
        canvas.drawString(17 * mm, 10 * mm, 'SciVerify | Whole-paper verification')
        canvas.drawRightString(A4[0] - 17 * mm, 10 * mm, str(doc.page))
        canvas.restoreState()
    doc = SimpleDocTemplate(output, pagesize=A4, rightMargin=17 * mm, leftMargin=17 * mm,
                            topMargin=17 * mm, bottomMargin=18 * mm, title=report.title, author='SciVerify')
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()


def render_docx(report):
    from docx import Document
    from docx.shared import Mm, Pt, RGBColor
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    doc = Document()
    section = doc.sections[0]
    section.page_width, section.page_height = Mm(210), Mm(297)
    section.top_margin = section.bottom_margin = Mm(18)
    section.left_margin = section.right_margin = Mm(17)
    for name in ['Normal', 'Title', 'Heading 1', 'Heading 2', 'Quote']:
        style = doc.styles[name]
        style.font.name = 'Calibri'
        style.element.get_or_add_rPr().rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')
    normal = doc.styles['Normal']
    normal.font.size = Pt(10)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.2
    doc.styles['Title'].font.color.rgb = RGBColor.from_string('172B3A')
    for name in ['Heading 1', 'Heading 2']:
        doc.styles[name].font.color.rgb = RGBColor.from_string('14697C')
    for block in report.blocks:
        if block.kind == 'pagebreak':
            doc.add_page_break()
            continue
        # Extracted PDF text can contain characters forbidden by Word's XML.
        text = _INVALID_XML_CHARACTERS.sub(' ', block.text)
        if not text.strip():
            continue
        style = {'title': 'Title', 'heading': 'Heading 1', 'subheading': 'Heading 2', 'quote': 'Quote'}.get(block.kind, 'Normal')
        p = doc.add_paragraph(text, style=style)
        if block.kind == 'heading' and block.status:
            from docx.enum.text import WD_TAB_ALIGNMENT
            p.paragraph_format.tab_stops.add_tab_stop(Mm(176), WD_TAB_ALIGNMENT.RIGHT)
            run = p.add_run('\t' + _INVALID_XML_CHARACTERS.sub(' ', block.status))
            run.font.size = Pt(10)
            run.font.color.rgb = RGBColor.from_string(_status_color(block.status))
        if block.kind == 'subheading' and re.match(r'^Reference(?: \d+)?:', block.text):
            p.paragraph_format.space_before = Pt(24)
            p.paragraph_format.keep_with_next = True
        if block.kind == 'code':
            for run in p.runs:
                run.font.name = 'Consolas'
                run.font.size = Pt(8)
    footer = section.footer.paragraphs[0]
    footer.text = 'SciVerify | Whole-paper verification    '
    field = OxmlElement('w:fldSimple')
    field.set(qn('w:instr'), 'PAGE')
    footer._p.append(field)
    doc.core_properties.title = _INVALID_XML_CHARACTERS.sub(' ', report.title)
    doc.core_properties.author = 'SciVerify'
    output = BytesIO()
    doc.save(output)
    return output.getvalue()


def render_report(report):
    return render_pdf(report) if report.format == 'pdf' else render_docx(report)
