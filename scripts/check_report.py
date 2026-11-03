"""Static checks of the Vietnamese report PDF: page count, figure/table numbering and references, citations,
leftover placeholders, and a few headline numbers against results/report/summary.csv."""
import os
import re
import sys

import pandas as pd
import pymupdf

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
pdf = pymupdf.open(os.path.join(ROOT, "report", "BaoCao_P1_Lakehouse.pdf"))
text = "\n".join(p.get_text() for p in pdf)
flat = re.sub(r"\s+", " ", text)
print("pages:", pdf.page_count)

fig_caps = [int(n) for n in re.findall(r"Hình (\d+)\. ", flat)]
tab_caps = [int(n) for n in re.findall(r"Bảng (\d+)\. ", flat)]
print("figure captions:", fig_caps, "| table captions:", tab_caps)
fig_refs = {int(n) for n in re.findall(r"Hình (\d+)(?!\.)", flat)}
tab_refs = {int(n) for n in re.findall(r"Bảng (\d+)(?!\.)", flat)}
print("figures referenced in text:", sorted(fig_refs), "| never referenced:", sorted(set(fig_caps) - fig_refs))
print("tables referenced in text:", sorted(tab_refs), "| never referenced:", sorted(set(tab_caps) - tab_refs))
print("refs to missing figures/tables:", sorted(fig_refs - set(fig_caps)), sorted(tab_refs - set(tab_caps)))

body = flat.split("References")[0]
cites = {int(x) for grp in re.findall(r"\[(\d+(?:\s*,\s*\d+)*)\]", body) for x in grp.split(",")}
n_refs = len(re.findall(r"\[(\d+)\]", flat.split("References")[-1]))
print("citations used:", sorted(cites), "| reference entries:", n_refs,
      "| uncited:", sorted(set(range(1, n_refs + 1)) - cites), "| out of range:", sorted(c for c in cites if c > n_refs))
print("placeholders:", [m for m in ("[Họ", "\\res", "TODO", "XXX") if m in text])

s = pd.read_csv(os.path.join(ROOT, "results", "report", "summary.csv"))
def tot(fmt, mode, u, c=0):
    return s[(s.fmt == fmt) & (s["mode"] == mode) & (s.u == u) & (s.c == c)].total_s.iat[0]
checks = {
    "Iceberg MoR u20 total = 59": round(tot("iceberg", "mor", 0.2)) == 59,
    "Delta DV u20 total = 251": round(tot("delta", "mor", 0.2)) == 251,
    "Hudi MoR u20 total = 165": round(tot("hudi", "mor", 0.2)) == 165,
    "Iceberg MoR c20 u20 total = 63": round(tot("iceberg", "mor", 0.2, 20)) == 63,
    "Parquet u0 total = 24": round(tot("parquet", "cow", 0.0)) == 24,
    "CV median 3.5%": round(s.total_cv.median() * 100, 1) == 3.5,
}
for k, v in checks.items():
    print(("OK  " if v else "FAIL"), k)
