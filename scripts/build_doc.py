#!/usr/bin/env python3
"""Build a monthly video doc in house style.

Usage:
    python3 scripts/build_doc.py spec.json

The document starts from template/house-style.docx (Letter, 1" margins,
Roboto Slab 12pt, the numbered-list style used for the question ideas) so the
output matches the docs already in Google Drive.

spec.json:
{
  "output": "ABC_Video_Prompts_12-2026.docx",
  "header": "Client: ... | Platform: ... | Month: ... | Ideas: 30",      (optional)
  "trend_summary": "Trend Summary: ...",                                 (optional)
  "ideas": [                                                             (optional)
    {"question": "...", "hook": "...", "followups": ["...", "..."]}
  ],
  "formats_intro": "Trending formats adapted for <client>. ...",          (optional)
  "formats": [                                                           (optional)
    {
      "title": "\"Nobody asks how WE'RE doing\"",
      "source": "Text-overlay skit · 1.1M views (97x the creator's normal)",
      "idea": "...",
      "setup": "8-10 sec, loops · Location: ... · 1 person",
      "shots": ["...", "Safety take: ..."],
      "lines": "...",                     (optional: exact words the client says)
      "on_screen_text": "...",
      "edit_notes": "...",
      "url": "https://...",
      "frames": ["path/frame_0001.jpg", "path/frame_0008.jpg", "path/frame_0015.jpg"]
    }
  ]
}

"hook" is written without the label; quotes are added if missing.
Frames are combined into one small strip (about 1.3" wide) so cards stay compact
when printed. A card with no frames gets a full-width text layout.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "template" / "house-style.docx"
FONT = "Roboto Slab"
HYPERLINK = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink"


def _font(r, size, bold=False, italic=False, color=None):
    r.font.name = FONT
    rpr = r._element.get_or_add_rPr()
    fonts = rpr.find(qn("w:rFonts"))
    for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        fonts.set(qn(attr), FONT)
    r.font.size = Pt(size)
    r.bold = bold or None
    r.italic = italic or None
    if color:
        r.font.color.rgb = RGBColor.from_string(color)
    return r


def run(p, text, size=12, bold=False, italic=False, color=None):
    return _font(p.add_run(text), size, bold, italic, color)


def para(container, before=0, after=0):
    p = container.add_paragraph()
    pf = p.paragraph_format
    pf.space_before, pf.space_after, pf.line_spacing = Pt(before), Pt(after), 1.0
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    return p


def numbered(p):
    """Put a paragraph in the template's numbered list (numId 1), like the question ideas."""
    if not TEMPLATE.exists():
        p.style = p.part.document.styles["List Number"]
        ppr = p._p.get_or_add_pPr()
        cs = OxmlElement("w:contextualSpacing")
        cs.set(qn("w:val"), "0")
        ppr.append(cs)
        p.paragraph_format.left_indent = Inches(0.5)
        p.paragraph_format.first_line_indent = Inches(-0.25)
        return
    ppr = p._p.get_or_add_pPr()
    num = OxmlElement("w:numPr")
    ilvl, nid = OxmlElement("w:ilvl"), OxmlElement("w:numId")
    ilvl.set(qn("w:val"), "0")
    nid.set(qn("w:val"), "1")
    num.append(ilvl)
    num.append(nid)
    ppr.insert(0, num)
    p.paragraph_format.left_indent = Inches(0.5)
    p.paragraph_format.first_line_indent = Inches(-0.25)


def hyperlink(doc, p, url, size=10):
    rid = doc.part.relate_to(url, HYPERLINK, is_external=True)
    h = OxmlElement("w:hyperlink")
    h.set(qn("r:id"), rid)
    r = run(p, url, size, color="1155CC")
    r.underline = True
    r._r.addprevious(h)
    h.append(r._r)


def no_borders(table):
    tblPr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        e = OxmlElement(f"w:{edge}")
        e.set(qn("w:val"), "nil")
        borders.append(e)
    tblPr.append(borders)
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    tblPr.append(layout)
    for old in tblPr.findall(qn("w:tblW")):
        tblPr.remove(old)
    w = OxmlElement("w:tblW")
    w.set(qn("w:w"), "9360")
    w.set(qn("w:type"), "dxa")
    tblPr.append(w)
    tr_pr = table.rows[0]._tr.get_or_add_trPr()
    tr_pr.append(OxmlElement("w:cantSplit"))


def rule(p):
    ppr = p._p.get_or_add_pPr()
    bdr, bottom = OxmlElement("w:pBdr"), OxmlElement("w:bottom")
    for k, v in (("val", "single"), ("sz", "6"), ("space", "4"), ("color", "BFBFBF")):
        bottom.set(qn(f"w:{k}"), v)
    bdr.append(bottom)
    ppr.append(bdr)


def frame_strip(paths, workdir):
    from PIL import Image

    imgs = []
    for p in paths[:3]:
        try:
            im = Image.open(p).convert("RGB")
            imgs.append(im)
        except Exception:
            continue
    if not imgs:
        return None
    h = 480
    imgs = [im.resize((max(1, int(im.width * h / im.height)), h)) for im in imgs]
    gap = 16
    strip = Image.new("RGB", (sum(i.width for i in imgs) + gap * (len(imgs) - 1), h), "white")
    x = 0
    for im in imgs:
        strip.paste(im, (x, 0))
        x += im.width + gap
    out = Path(workdir) / f"strip_{len(os.listdir(workdir))}.jpg"
    strip.save(out, quality=85)
    return out, strip.width / strip.height


def card_fields(doc, cell_or_doc, c, first_para=None):
    def field(label, value, first=False):
        p = first_para if (first and first_para is not None) else para(cell_or_doc, after=2)
        run(p, label + " ", 10, bold=True)
        run(p, value, 10)

    field("The idea:", c["idea"], first=True)
    field("Length & setup:", c["setup"])
    p = para(cell_or_doc, after=1)
    run(p, "Shots:", 10, bold=True)
    for j, s in enumerate(c.get("shots", []), 1):
        p = para(cell_or_doc, after=1)
        p.paragraph_format.left_indent = Inches(0.15)
        run(p, f"{j}. {s}", 10)
    if c.get("lines"):
        field("Lines:", c["lines"])
    field("On-screen text:", c["on_screen_text"])
    field("Edit notes:", c["edit_notes"])
    if c.get("url"):
        p = para(cell_or_doc, after=2)
        run(p, "Original: ", 10, bold=True)
        hyperlink(doc, p, c["url"])


def new_document():
    """House-style document. Uses template/house-style.docx when it is next to this
    script; otherwise builds the same page setup from scratch, so this file also
    works on its own (copied out of the format-ideas skill)."""
    if TEMPLATE.exists():
        return Document(str(TEMPLATE))
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Inches(8.5), Inches(11)
    for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(sec, side, Inches(1))
    for name in ("Normal", "List Number"):
        st = doc.styles[name]
        st.font.name = FONT
        st.font.size = Pt(12)
        rfonts = st.element.get_or_add_rPr().get_or_add_rFonts()
        for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
            rfonts.set(qn(attr), FONT)
    return doc


def build(spec):
    doc = new_document()
    workdir = tempfile.mkdtemp(prefix="cards-")

    if spec.get("header"):
        p = para(doc, after=12)
        run(p, spec["header"])
    if spec.get("trend_summary"):
        p = para(doc, after=12)
        run(p, spec["trend_summary"])

    for idea in spec.get("ideas", []):
        p = para(doc, before=12, after=12)
        numbered(p)
        run(p, idea["question"].rstrip() + " ", bold=True)
        hook = idea["hook"].strip()
        if not hook.startswith(("\"", "“")):
            hook = f"\"{hook}\""
        run(p, f"Recommended hook: {hook} ")
        fups = " / ".join(
            q if q.startswith(("\"", "“")) else f"\"{q}\"" for q in idea.get("followups", [])
        )
        if fups:
            run(p, f"Optional follow-up questions: {fups}", italic=True)

    formats = spec.get("formats", [])
    if formats:
        p = para(doc)
        if spec.get("ideas") or spec.get("header"):
            p.add_run().add_break(WD_BREAK.PAGE)
        p = para(doc, after=4)
        run(p, "Format Ideas", bold=True)
        p = para(doc, after=10)
        run(p, spec.get("formats_intro") or
            "Trending formats adapted for this client. Each card has everything needed to "
            "shoot and edit without watching the original.", 10, italic=True)

        for i, c in enumerate(formats, 1):
            p = para(doc, after=2)
            p.paragraph_format.keep_with_next = True
            run(p, f"{i}. {c['title']}", bold=True)
            if c.get("source"):
                p = para(doc, after=4)
                p.paragraph_format.keep_with_next = True
                run(p, c["source"], 9, italic=True, color="595959")

            strip = frame_strip(c.get("frames") or [], workdir)
            if strip:
                path, ratio = strip
                t = doc.add_table(rows=1, cols=2)
                no_borders(t)
                t.autofit = False
                for col, w in zip(t.columns, (Inches(1.55), Inches(4.95))):
                    col.width = w
                    for cell in col.cells:
                        cell.width = w
                left, right = t.rows[0].cells
                lp = left.paragraphs[0]
                lp.alignment = WD_ALIGN_PARAGRAPH.LEFT
                lp.paragraph_format.space_after = Pt(0)
                width = 1.3 if ratio >= 1.3 / 1.6 else 1.6 * ratio  # cap the height near 1.6"
                lp.add_run().add_picture(str(path), width=Inches(width))
                cap = para(left)
                run(cap, "Reference frames", 7, italic=True, color="7F7F7F")
                first = right.paragraphs[0]
                first.alignment = WD_ALIGN_PARAGRAPH.LEFT
                first.paragraph_format.space_after = Pt(2)
                card_fields(doc, right, c, first_para=first)
            else:
                card_fields(doc, doc, c)
            p = para(doc, after=8)
            rule(p)

    out = Path(spec.get("output", "output.docx"))
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out))
    return out


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: build_doc.py spec.json")
    spec = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    print(build(spec))
