"""Export the slide deck to report/Slides_P1_Lakehouse.pptx with editable text, tables and speaker notes.

    python report/build_slides_pptx.py <deck folder holding project/deck.json and project/slides/>

Headless Edge lays out the same HTML that the PDF export prints, the script reads each element's position back,
and python-pptx rebuilds it as native PowerPoint objects. 1920 px maps to 13.33 in.
"""
import http.server
import json
import os
import re
import subprocess
import tempfile
import threading
import time

from bs4 import BeautifulSoup, NavigableString
from lxml import etree
from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Pt

import build_slides_pdf as pdf

OUT = os.path.join(pdf.HERE, "Slides_P1_Lakehouse.pptx")
FONT = "Times New Roman"
PX = 6350  # EMU per CSS pixel
BULLET_INDENT = 36  # px
NO_STYLE_TABLE = "{2D5ABB26-0587-4C30-8999-92F81FD0307C}"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"

MEASURE = """<script>
window.addEventListener('load', function () {
  var out = {};
  var keep = {H1: 1, H2: 1, P: 1, UL: 1, OL: 1, TABLE: 1, IMG: 1};
  document.querySelectorAll('section').forEach(function (sec) {
    var o = sec.getBoundingClientRect(), items = [];
    function box(e) {
      var r = e.getBoundingClientRect();
      return [r.left - o.left, r.top - o.top, r.width, r.height];
    }
    (function walk(el) {
      Array.prototype.forEach.call(el.children, function (c) {
        if (c.tagName === 'ASIDE') return;
        if (keep[c.tagName]) {
          var item = {tag: c.tagName, box: box(c)};
          if (c.tagName === 'TABLE') {
            item.rows = Array.prototype.map.call(c.rows, function (r) { return r.getBoundingClientRect().height; });
            item.cols = Array.prototype.map.call(c.rows[0].cells, function (d) { return d.getBoundingClientRect().width; });
          }
          items.push(item);
        } else { walk(c); }
      });
    })(sec);
    out[sec.id] = items;
  });
  fetch('http://127.0.0.1:PORT/', {method: 'POST', mode: 'no-cors', body: JSON.stringify(out)});
});
</script>"""


def measure(deck):
    """Slide html by id, and the element boxes Edge computed for each slide."""
    html, parts = {}, []
    for sid in deck["order"]:
        s = open(os.path.join(pdf.DECK, "project", "slides", f"{sid}.html"), encoding="utf-8").read()
        for blob, path in pdf.BLOBS.items():
            s = s.replace(f"/_blob/{blob}", "file:///" + path.replace("\\", "/"))
        html[sid] = s
        parts.append(s)
    received = {}
    done = threading.Event()

    class Receiver(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            received.update(json.loads(self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8")))
            self.send_response(204)
            self.end_headers()
            done.set()

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    script = MEASURE.replace("PORT", str(server.server_address[1]))
    page = f'<!doctype html><html><head><meta charset="utf-8"><style>{pdf.CSS}</style></head><body>{"".join(parts)}{script}</body></html>'
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        src = os.path.join(tmp, "deck.html")
        open(src, "w", encoding="utf-8").write(page)
        # Edge's launcher exits at once; the page reports its measurements to the local receiver when it has loaded.
        subprocess.run([pdf.EDGE, "--headless=new", "--disable-gpu", "--no-first-run", "--window-size=1920,1080",
                        f"--user-data-dir={os.path.join(tmp, 'profile')}", "--virtual-time-budget=15000",
                        "--allow-file-access-from-files", f"--print-to-pdf={os.path.join(tmp, 'x.pdf')}",
                        "file:///" + src.replace("\\", "/")], capture_output=True, timeout=60, check=True)
        got = done.wait(90)
        time.sleep(3)
    server.shutdown()
    if not got:
        raise SystemExit("Edge returned no measurements")
    return html, received


def css(el):
    return {k.strip(): v.strip() for k, v in (d.split(":", 1) for d in (el.get("style") or "").split(";") if ":" in d)}


def color(value, default="1A1A1A"):
    value = (value or "").lstrip("#")
    return RGBColor.from_string((value or default).upper())


def runs_of(node, bold=False, italic=False):
    """(text, bold, italic) runs of an element, with HTML whitespace collapsed."""
    out = []
    for c in node.children:
        if isinstance(c, NavigableString):
            text = re.sub(r"\s+", " ", str(c))
            if text:
                out.append((text, bold, italic))
        elif c.name in ("b", "strong"):
            out += runs_of(c, True, italic)
        elif c.name in ("i", "em"):
            out += runs_of(c, bold, True)
        else:
            out += runs_of(c, bold, italic)
    return out


def write_runs(par, runs, size, rgb, base_bold=False, base_italic=False):
    for text, b, i in runs:
        run = par.add_run()
        run.text = text
        run.font.name = FONT
        run.font.size = Pt(size)
        run.font.color.rgb = rgb
        run.font.bold = bool(b or base_bold)
        run.font.italic = bool(i or base_italic)


def align(style):
    return {"center": PP_ALIGN.CENTER, "right": PP_ALIGN.RIGHT}.get(style.get("text-align"), PP_ALIGN.LEFT)


def frame(tf):
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.TOP


def textbox(slide, box, name):
    x, y, w, h = box
    tb = slide.shapes.add_textbox(Emu(int(x * PX)), Emu(int(y * PX)), Emu(int((w + 4) * PX)), Emu(int(h * PX)))
    tb.name = name
    frame(tb.text_frame)
    return tb


def bullet(par, kind, indent):
    pPr = par._p.get_or_add_pPr()
    pPr.set("marL", str(indent * PX))
    pPr.set("indent", str(-indent * PX))
    if kind == "ol":
        etree.SubElement(pPr, f"{{{A}}}buFont").set("typeface", "+mj-lt")
        etree.SubElement(pPr, f"{{{A}}}buAutoNum").set("type", "arabicPeriod")
    else:
        etree.SubElement(pPr, f"{{{A}}}buFont").set("typeface", FONT)
        etree.SubElement(pPr, f"{{{A}}}buChar").set("char", "•")


def add_title(slide, el, item):
    st = css(el)
    size = float(st["font-size"][:-2]) / 2
    x, y, w, h = item["box"]
    if el.name == "h1":  # the browser shrinks a centred title to its text; PowerPoint needs room to keep one line
        x, w = 128, 1664
    t = slide.shapes.title
    t.left, t.top, t.width, t.height = Emu(int(x * PX)), Emu(int(y * PX)), Emu(int(w * PX)), Emu(int(h * PX))
    frame(t.text_frame)
    par = t.text_frame.paragraphs[0]
    par.alignment = align(st)
    write_runs(par, runs_of(el), size, color(st.get("color")), True)
    if el.name == "h2":
        line = slide.shapes.add_connector(1, Emu(int(x * PX)), Emu(int((y + h) * PX)), Emu(int((x + w) * PX)), Emu(int((y + h) * PX)))
        line.name = "Đường kẻ tiêu đề"
        line.line.color.rgb = color(st.get("color"))
        line.line.width = Pt(1)


def add_text(slide, el, item, inherited):
    st = {**inherited, **css(el)}
    size = float(st.get("font-size", "32px")[:-2]) / 2
    spacing = Pt(size * float(st.get("line-height", 1.4)))
    rgb = color(st.get("color"))
    x, y, w, h = item["box"]
    if el.name in ("ul", "ol"):
        indent = BULLET_INDENT + 16 if el.name == "ol" else BULLET_INDENT
        tb = textbox(slide, (x - indent, y, w + indent, h), "Danh sách")
        for i, li in enumerate(el.find_all("li", recursive=False)):
            par = tb.text_frame.paragraphs[0] if i == 0 else tb.text_frame.add_paragraph()
            par.line_spacing = spacing
            write_runs(par, runs_of(li), size, rgb)
            bullet(par, el.name, indent)
        return
    pinned = st.get("position") == "absolute"
    tb = textbox(slide, item["box"], "Chân trang" if pinned else "Nội dung")
    par = tb.text_frame.paragraphs[0]
    par.alignment = align(st)
    par.line_spacing = spacing
    bold = st.get("font-weight") == "700"
    italic = st.get("font-style") == "italic"
    if pinned and el.get_text().strip().isdigit():
        fld = etree.SubElement(par._p, f"{{{A}}}fld", id="{B6F15528-21DE-4FAA-801E-634DDDAF4B2B}", type="slidenum")
        rPr = etree.SubElement(fld, f"{{{A}}}rPr", lang="vi-VN", sz=str(int(size * 100)))
        fill = etree.SubElement(rPr, f"{{{A}}}solidFill")
        etree.SubElement(fill, f"{{{A}}}srgbClr", val=str(rgb))
        etree.SubElement(rPr, f"{{{A}}}latin", typeface=FONT)
        etree.SubElement(fld, f"{{{A}}}t").text = el.get_text().strip()
        return
    write_runs(par, runs_of(el), size, rgb, bold, italic)


def cell_border(cell, sides, rgb, width_px=1):
    tcPr = cell._tc.get_or_add_tcPr()
    for side in sides:
        ln = etree.Element(f"{{{A}}}{side}", w=str(width_px * PX), cap="flat", cmpd="sng", algn="ctr")
        fill = etree.SubElement(ln, f"{{{A}}}solidFill")
        etree.SubElement(fill, f"{{{A}}}srgbClr", val=rgb)
        etree.SubElement(ln, f"{{{A}}}prstDash", val="solid")
        tcPr.append(ln)


def add_table(slide, el, item):
    st = css(el)
    px = float(st["font-size"][:-2])
    size = px / 2
    rows = el.find_all("tr")
    x, y, w, h = item["box"]
    gf = slide.shapes.add_table(len(rows), len(item["cols"]), Emu(int(x * PX)), Emu(int(y * PX)), Emu(int(w * PX)), Emu(int(h * PX)))
    gf.name = "Bảng"
    tbl = gf.table
    props = tbl._tbl.tblPr
    props.find(qn("a:tableStyleId")).text = NO_STYLE_TABLE
    tbl.horz_banding = False
    tbl.first_row = True
    for col, width in zip(tbl.columns, item["cols"]):
        col.width = Emu(int(width * PX))
    for row, height in zip(tbl.rows, item["rows"]):
        row.height = Emu(int(height * PX))
    for r, tr in enumerate(rows):
        head = tr.find("th") is not None
        for c, td in enumerate(tr.find_all(["th", "td"])):
            cell = tbl.cell(r, c)
            cell.margin_left = cell.margin_right = Emu(int(0.4 * px * PX))
            cell.margin_top = cell.margin_bottom = Emu(int(0.2 * px * PX))
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            par = cell.text_frame.paragraphs[0]
            par.alignment = align(css(td))
            write_runs(par, runs_of(td), size, color(st.get("color")), head)
            # a:tcPr needs the four borders before the fill, so write the borders first.
            cell_border(cell, ["lnL", "lnR", "lnT", "lnB"], "B8C0CC")
            cell.fill.solid()
            cell.fill.fore_color.rgb = color("E9EDF2" if head else "FFFFFF")


def add_image(slide, el, item):
    path = el["src"].replace("file:///", "")
    x, y, w, h = item["box"]
    iw, ih = Image.open(path).size
    scale = min(w / iw, h / ih)
    pw, ph = iw * scale, ih * scale
    left = x if "object-position:left" in el.get("style", "") else x + (w - pw) / 2
    top = y + (h - ph) / 2
    pic = slide.shapes.add_picture(path, Emu(int(left * PX)), Emu(int(top * PX)), Emu(int(pw * PX)), Emu(int(ph * PX)))
    pic.name = "Hình"
    pic._element.nvPicPr.cNvPr.set("descr", el.get("alt", ""))


def set_theme_font(prs):
    for rel in prs.slide_masters[0].part.rels.values():
        if rel.reltype.endswith("/theme"):
            part = rel.target_part
            part._blob = re.sub(rb'(<a:(?:major|minor)Font>\s*<a:latin typeface=")[^"]*', rb"\g<1>" + FONT.encode(), part.blob)


def main():
    deck = json.load(open(os.path.join(pdf.DECK, "project", "deck.json"), encoding="utf-8"))
    html, boxes = measure(deck)
    prs = Presentation()
    prs.slide_width, prs.slide_height = Emu(1920 * PX), Emu(1080 * PX)
    prs.core_properties.title = deck["title"]
    prs.core_properties.author = "Hà Văn Vinh, Đỗ Thị Lan"
    set_theme_font(prs)
    layout = prs.slide_layouts[5]  # Title Only
    for sid in deck["order"]:
        sec = BeautifulSoup(html[sid], "html.parser").find("section")
        tags = [e for e in sec.find_all(["h1", "h2", "p", "ul", "ol", "table", "img"])
                if not e.find_parent(["ul", "ol", "table"])]
        items = boxes[sid]
        assert len(tags) == len(items), (sid, len(tags), len(items))
        inherited = {k: v for k, v in css(sec).items() if k == "color"}
        slide = prs.slides.add_slide(layout)
        for el, item in zip(tags, items):
            if el.name in ("h1", "h2"):
                add_title(slide, el, item)
            elif el.name == "table":
                add_table(slide, el, item)
            elif el.name == "img":
                add_image(slide, el, item)
            else:
                add_text(slide, el, item, inherited)
        note = sec.find("aside")
        if note:
            slide.notes_slide.notes_text_frame.text = note.get_text().strip()
    prs.save(OUT)
    print("saved", OUT, os.path.getsize(OUT) // 1024, "KB", len(prs.slides), "slides")


if __name__ == "__main__":
    main()
