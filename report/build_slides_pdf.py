"""Export the slide deck to report/Slides_P1_Lakehouse.pdf with headless Edge.

    python report/build_slides_pdf.py <deck folder holding project/deck.json and project/slides/>

Each slide is a 1920x1080 <section>; images use the local PNGs behind the deck's /_blob/ assets.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DECK = sys.argv[1]
OUT = os.path.join(HERE, "Slides_P1_Lakehouse.pdf")
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
RES = os.path.join(ROOT, "results", "report")
BLOBS = {
    "39a7cb4ad1d97efc41fe8165fd7e9952": os.path.join(HERE, "figures", "fig_architecture_vi.png"),
    "0e281ff5497f46bf05f0a3c69b5c5804": os.path.join(RES, "fig_rq1_total_cost.png"),
    "54b88aaba413e9f4181c9950ff99aaa3": os.path.join(RES, "fig_write_amplification.png"),
    "adc873dedc24888f4519457ecbce258b": os.path.join(RES, "fig_rq2_compaction.png"),
    "7680d4c1d069ab3698833f6f25326b18": os.path.join(RES, "fig_rq3_metadata.png"),
    "8acdbe69721b46759fbd79e9daebcfdd": os.path.join(RES, "fig_ops.png"),
    "87e74c23469a49821148cd3287c70b4c": os.path.join(RES, "fig_variability.png"),
    "725130b2931d857376f45390ce646aaf": os.path.join(RES, "fig_ingest_trend.png"),
    "25f40125ca49a82b4c76f691eacd473b": os.path.join(HERE, "figures", "eq_runs.png"),
    "6a6481a1c8c20dc205c0ff3b0a7d5542": os.path.join(HERE, "figures", "eq_wa.png"),
    "4af89dfc920a5e2c933ea027469b329e": os.path.join(HERE, "figures", "eq_deg.png"),
}
CSS = """
@page { size: 1920px 1080px; margin: 0; }
html, body { margin: 0; padding: 0; }
* { box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
section { position: relative; width: 1920px; height: 1080px; overflow: hidden; page-break-after: always;
          break-after: page; }
section:last-of-type { page-break-after: auto; break-after: auto; }
h1, h2, h3, p, ul, ol { margin: 0; padding: 0; }
p { font-size: 32px; line-height: 1.4; }
table { border-collapse: collapse; width: 100%; }
th, td { padding: 0.35em 0.6em; border-bottom: 1px solid #C9CDD6; text-align: left; }
th { font-weight: 700; }
aside { display: none; }
img { display: block; }
"""


def main():
    deck = json.load(open(os.path.join(DECK, "project", "deck.json"), encoding="utf-8"))
    links = "".join(f'<link rel="stylesheet" href="{f["href"]}">' for f in deck["faces"].values())
    parts = []
    for sid in deck["order"]:
        html = open(os.path.join(DECK, "project", "slides", f"{sid}.html"), encoding="utf-8").read()
        for blob, path in BLOBS.items():
            html = html.replace(f"/_blob/{blob}", "file:///" + path.replace("\\", "/"))
        assert "/_blob/" not in html, sid
        parts.append(html)
    page = (f'<!doctype html><html><head><meta charset="utf-8"><title>{deck["title"]}</title>{links}'
            f"<style>{CSS}</style></head><body>{''.join(parts)}</body></html>")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        src = os.path.join(tmp, "deck.html")
        tmp_pdf = os.path.join(tmp, "deck.pdf")
        open(src, "w", encoding="utf-8").write(page)
        subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--no-first-run",
                        f"--user-data-dir={os.path.join(tmp, 'profile')}", "--virtual-time-budget=15000",
                        "--allow-file-access-from-files", f"--print-to-pdf={tmp_pdf}", "file:///" + src.replace("\\", "/")],
                       check=True, timeout=180, capture_output=True)
        # The Edge launcher exits before its child has printed, so wait for the file to stop growing.
        last, stable = -1, 0
        for _ in range(240):
            time.sleep(0.5)
            size = os.path.getsize(tmp_pdf) if os.path.isfile(tmp_pdf) else -1
            stable = stable + 1 if size > 0 and size == last else 0
            last = size
            if stable >= 6:
                break
        else:
            raise SystemExit("Edge produced no PDF")
        os.replace(tmp_pdf, OUT)
    print("saved", OUT, os.path.getsize(OUT) // 1024, "KB")


if __name__ == "__main__":
    main()
