"""One-off fix of the report (2026-11-03): reference every figure/table in the text, cite [13, 14], and
disambiguate the Table 4 header. Edits report/BaoCao_P1_Lakehouse.docx in place (the sample template used by
build_report.py is no longer available)."""
import os
import sys

import docx

sys.stdout.reconfigure(encoding="utf-8")
PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "BaoCao_P1_Lakehouse.docx")
d = docx.Document(PATH)

EDITS = [
    ("Không compaction, MoR trả giá khi đọc.", "Không compaction, MoR trả giá khi đọc (Hình 4)."),
    ("Metadata tăng tuyến tính nhưng với tốc độ rất khác nhau.",
     "Metadata tăng tuyến tính nhưng với tốc độ rất khác nhau (Hình 6)."),
    (" MERGE một batch có 4.320", " theo Hình 7, MERGE một batch có 4.320"),
    ("Ngược lại, cùng một cấu hình", "Ngược lại (Hình 8, bên phải), cùng một cấu hình"),
    ("ảnh hưởng như nhau tới mọi format.", "ảnh hưởng như nhau tới mọi format. Bảng 2 tóm tắt các tham số workload."),
    ("Iceberg MoR rẻ nhất ở mọi u > 0 (58–63 s),", "Iceberg MoR rẻ nhất ở mọi u > 0 (58–63 s; chi tiết ở u = 20% trong Bảng 4),"),
    (" Spark 3.5.3 (local,", " Spark 3.5.3 [13, 14] (local,"),
]
done = []
for old, new in EDITS:
    for p in d.paragraphs:
        hit = next((r for r in p.runs if old in r.text), None)
        if hit is not None:
            hit.text = hit.text.replace(old, new, 1)
            done.append(old)
            break
missing = [o for o, _ in EDITS if o not in done]

# Table 4: the second "Compaction" column is the cadence, the fourth is the time spent.
t4 = next(t for t in d.tables if t.rows[0].cells[0].text.strip() == "Layout" and len(t.columns) == 9)
cell = t4.rows[0].cells[1]
run = next(r for r in cell.paragraphs[0].runs if r.text.strip())
assert run.text.strip() == "Compaction", run.text
run.text = "Chu kỳ"

d.save(PATH)
print("applied:", len(done), "of", len(EDITS), "| missing:", missing, "| table 4 header fixed")
