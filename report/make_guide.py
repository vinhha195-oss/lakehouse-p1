"""Build report/HuongDan_CauTrucDuAn.docx: a Vietnamese guide to the project's folders, workflow and next steps.
Convert to PDF with report/to_pdf.ps1."""
import os

import docx
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "HuongDan_CauTrucDuAn.docx")
FONT = "Times New Roman"
DARK = RGBColor(0x0B, 0x3A, 0x4A)

doc = docx.Document()
sec = doc.sections[0]
sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
for side in ("left_margin", "right_margin"):
    setattr(sec, side, Cm(2.0))
sec.top_margin = sec.bottom_margin = Cm(1.8)


def set_font(style, size, bold=None, color=None):
    style.font.name = FONT
    rfonts = style.element.rPr.rFonts
    rfonts.set(qn("w:eastAsia"), FONT)
    for attr in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
        rfonts.attrib.pop(qn(attr), None)  # theme fonts would override Times New Roman on headings
    style.font.size = Pt(size)
    if bold is not None:
        style.font.bold = bold
    if color is not None:
        style.font.color.rgb = color


set_font(doc.styles["Normal"], 12)
doc.styles["Normal"].paragraph_format.space_after = Pt(4)
set_font(doc.styles["Title"], 20, True, DARK)
set_font(doc.styles["Heading 1"], 15, True, DARK)
set_font(doc.styles["Heading 2"], 13, True, DARK)
for name in ("Heading 1", "Heading 2"):
    doc.styles[name].paragraph_format.space_before = Pt(10)
    doc.styles[name].paragraph_format.space_after = Pt(4)


def para(text, style=None, italic=False, size=None):
    """Paragraph with **bold** and `code` spans."""
    p = doc.add_paragraph(style=style)
    parts = text.replace("**", "\x00").split("\x00")
    for i, part in enumerate(parts):
        for j, chunk in enumerate(part.split("`")):
            if not chunk:
                continue
            r = p.add_run(chunk)
            r.bold = i % 2 == 1
            r.italic = italic
            if j % 2 == 1:
                r.font.name = "Consolas"
                r.font.size = Pt(10.5)
            elif size:
                r.font.size = Pt(size)
    return p


def bullet(text):
    return para(text, style="List Bullet")


def numbered(text):
    return para(text, style="List Number")


def shade(cell, fill):
    tcpr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tcpr.append(shd)


def table(header, rows, widths):
    t = doc.add_table(rows=1, cols=len(header))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, h in enumerate(header):
        c = t.rows[0].cells[i]
        c.text = ""
        r = c.paragraphs[0].add_run(h)
        r.bold = True
        r.font.size = Pt(11)
        shade(c, "E3EDEB")
    for row in rows:
        cells = t.add_row().cells
        for i, v in enumerate(row):
            cells[i].text = ""
            p = cells[i].paragraphs[0]
            for j, chunk in enumerate(v.split("`")):
                if chunk:
                    r = p.add_run(chunk)
                    r.font.size = Pt(10.5 if j % 2 == 1 else 11)
                    if j % 2 == 1:
                        r.font.name = "Consolas"
    for row in t.rows:
        for i, w in enumerate(widths):
            row.cells[i].width = Cm(w)
    doc.add_paragraph()
    return t


# ------------------------------------------------------------------------------------------------ content
doc.add_paragraph("Hướng dẫn cấu trúc dự án P1", style="Title")
para("Delta Lake vs Apache Iceberg vs Apache Hudi dưới workload cập nhật nhiều — Big Data Analytics and "
     "Management (TLU 2026)", italic=True)
para("**Tác giả:** Hà Văn Vinh, Đỗ Thị Lan · **Cập nhật:** 03/11/2026 · **Thư mục:** `C:\\Users\\Admin\\lakehouse-p1` · "
     "**Repo:** https://github.com/vinhha195-oss/lakehouse-p1")
para("Tài liệu giải thích từng thư mục và file trong dự án, quy trình đã thực hiện và các bước còn lại để hoàn "
     "thiện. Các mục được gom theo vai trò, không theo thứ tự chữ cái trong Windows Explorer.")

doc.add_paragraph("1. Bức tranh tổng thể: dự án đi qua 5 bước", style="Heading 1")
table(["Bước", "Việc làm", "Nằm ở đâu"],
      [["1. Dữ liệu", "Tải TSM-Bench d1 (dữ liệu thủy văn, 4,8 GB), cắt 10 trạm × 20 cảm biến × 17 ngày", "`_ext\\`"],
       ["2. Sinh workload", "Bộ sinh sensor-LST tạo luồng thao tác: nạp, 40 batch có dữ liệu trễ, xóa trạm-ngày, "
        "kèm ground truth", "`sensorlst\\workload.py`"],
       ["3. Chạy thí nghiệm", "4 notebook Kaggle, 237 lần chạy (3 format × 2 chế độ × 4 mức u × 3 chu kỳ "
        "compaction, lặp 3 lần)", "`notebooks\\`, `sensorlst\\`"],
       ["4. Phân tích", "Gộp kết quả, chuẩn hóa theo tốc độ VM, xuất bảng và biểu đồ",
        "`sensorlst\\analyze.py` → `results\\report\\`"],
       ["5. Viết & trình bày", "Bài báo 14 trang, slide 20 trang, demo localhost, repo GitHub",
        "`report\\`, `demo\\`, GitHub"]],
      [3.2, 9.4, 4.4])

doc.add_paragraph("2. Từng mục và nhiệm vụ", style="Heading 1")
doc.add_paragraph("A. Mã nguồn chính: sensorlst\\", style="Heading 2")
para("Đây là “trái tim” của dự án; các notebook Kaggle chạy chính những file này.")
table(["File", "Nhiệm vụ"],
      [["`config.py`", "Khai báo phiên bản (Spark 3.5.3, Delta 3.2.1, Iceberg 1.6.1, Hudi 0.15.0), các quy mô "
        "(smoke, small, demo) và ma trận thí nghiệm 3 format × 2 chế độ × 4 mức u × 3 chu kỳ compaction"],
       ["`workload.py`", "Bộ sinh workload sensor-LST: đọc TSM-Bench d1, sinh trước toàn bộ luồng thao tác ra file "
        "Parquet và tính ground truth (số dòng, tổng s0) để kiểm tra"],
       ["`formats.py`", "Adapter cho 4 layout (Delta, Iceberg, Hudi, Parquet) với cùng các lệnh: tạo bảng, append, "
        "upsert, xóa, compaction, time travel, đếm file và metadata; chứa các bản sửa lỗi Hudi"],
       ["`queries.py`", "Năm truy vấn phân tích Q1–Q5"],
       ["`run_one.py`", "Chạy một cấu hình trong một JVM Spark mới: đo từng thao tác, đếm byte ghi, so với ground "
        "truth, ghi kết quả ra một file JSON"],
       ["`matrix.py`", "Chạy nhiều cấu hình (một shard): 3 vòng, xáo thứ tự ngẫu nhiên, giới hạn thời gian, chạy "
        "tiếp được khi bị ngắt"],
       ["`analyze.py`", "Gộp JSON, chuẩn hóa thời gian theo VM, xuất bảng CSV và biểu đồ fig_*.png"]],
      [3.4, 13.6])

doc.add_paragraph("B. Chạy thí nghiệm", style="Heading 2")
table(["Mục", "Nhiệm vụ"],
      [["`notebooks\\sensorlst_u00/01/05/20.ipynb`", "4 notebook đã chạy trên Kaggle, mỗi notebook một mức u; "
        "code sensorlst được nhúng sẵn bên trong"],
       ["`scripts\\make_notebooks.py`", "Sinh lại 4 notebook từ code trong sensorlst\\"],
       ["`HUONG_DAN_KAGGLE.md`", "Hướng dẫn từng bước chạy trên Kaggle"],
       ["`scripts\\show_run.py`", "In tóm tắt nhanh một file kết quả JSON"]],
      [6.0, 11.0])

doc.add_paragraph("C. Kết quả: results\\", style="Heading 2")
table(["Mục", "Nội dung"],
      [["`kaggle\\`", "Dữ liệu gốc chính thức: 237 file JSON từ 4 file zip Kaggle"],
       ["`report\\`", "Kết quả đã phân tích: summary.csv, bảng theo truy vấn, hệ số hiệu chuẩn VM, 8 biểu đồ dùng "
        "trong bài"]],
      [6.0, 11.0])

doc.add_paragraph("D. Báo cáo", style="Heading 2")
table(["Mục", "Nhiệm vụ"],
      [["`report\\BaoCao_P1_Lakehouse.docx / .pdf`", "Bài báo để nộp, 14 trang, khổ A4, chữ 13 pt"],
       ["`report\\Slides_P1_Lakehouse.pptx / .pdf`", "Slide trình bày, 20 trang; bản .pptx sửa được chữ, bảng và ghi chú"],
       ["`report\\build_slides_pptx.py`, `build_slides_pdf.py`", "Xuất slide online sang PowerPoint và PDF"],
       ["`report\\make_figures.py`", "Vẽ hình 1 (sơ đồ kiến trúc, nhãn tiếng Việt)"],
       ["`report\\make_formulas.py`", "Tạo ảnh công thức dùng trên slide"],
       ["`report\\make_guide.py`", "Tạo tài liệu hướng dẫn này"],
       ["`report\\to_pdf.ps1`", "Gọi Microsoft Word để xuất .docx sang PDF"],
       ["`scripts\\check_report.py`", "Kiểm tra bài: số trang, tham chiếu hình/bảng, trích dẫn, con số chính"],
       ["`paper\\main.tex`, `paper_overleaf.zip`", "Bản bài báo IEEE tiếng Anh (LaTeX) để biên dịch trên Overleaf; "
        "không bắt buộc"],
       ["`scripts\\check_paper.py`", "Kiểm tra bản LaTeX: trích dẫn, tham chiếu, file hình"]],
      [6.0, 11.0])

doc.add_paragraph("E. Demo", style="Heading 2")
table(["Mục", "Nhiệm vụ"],
      [["`run_demo.bat`", "Nhấp đúp để mở demo tại http://localhost:8501"],
       ["`report\\KichBan_Demo.docx / .pdf`", "Kịch bản trình bày demo 5 phút, xử lý sự cố, câu hỏi có thể gặp"],
       ["`demo\\app.py`", "Giao diện web Streamlit: ghi batch, xóa, compaction, time travel"],
       ["`demo\\worker.py`", "Chạy một phiên Spark cho mỗi format, nhận lệnh từ giao diện"],
       ["`demo\\test_app.py`, `demo\\test_worker.py`", "Test tự động cho demo"],
       ["`scripts\\demo_time_travel.py`", "Demo time travel bản dòng lệnh (bản đơn giản)"]],
      [6.0, 11.0])

doc.add_paragraph("F. Kiểm thử, môi trường và tài liệu", style="Heading 2")
table(["Mục", "Nhiệm vụ"],
      [["`tests\\test_workload.py`", "7 unit test cho bộ sinh workload"],
       ["`README.md`", "Mô tả dự án bằng tiếng Anh, hiển thị trên GitHub"],
       ["`requirements.txt`", "Danh sách thư viện Python cần cài"],
       ["`.gitignore`", "Những thư mục không đưa lên GitHub"],
       ["`scripts\\local_env.sh`", "Thiết lập Java và Hadoop để chạy Spark trên Windows"],
       ["`.venv\\` (≈ 1 GB)", "Môi trường Python riêng của dự án (PySpark, Streamlit…)"],
       ["`_ext\\` (≈ 1,8 GB)", "Công cụ tải về: Java portable, winutils, gói Delta/Iceberg/Hudi, dữ liệu đã cắt "
        "d1_small.parquet"]],
      [6.0, 11.0])

doc.add_paragraph("G. Thư mục tạm của demo (không nộp, không có trên GitHub)", style="Heading 2")
table(["Mục", "Ghi chú"],
      [["`staging\\demo_u20\\`", "Luồng thao tác của demo; demo tự tạo lại nếu thiếu"],
       ["`work\\`", "Thư mục làm việc của Spark khi chạy demo, đang trống"]],
      [6.0, 11.0])

doc.add_paragraph("3. Quy trình đã thực hiện", style="Heading 1")
numbered("**Xây dựng (30/10):** viết sensorlst\\, sửa các lỗi Hudi, chạy thử 26 cấu hình nhỏ trên máy và 3 cấu hình "
         "quy mô thật; tất cả đều đúng.")
numbered("**Chạy thí nghiệm (31/10):** 4 notebook Kaggle, 237 lần chạy, tải 4 file zip về results\\kaggle\\.")
numbered("**Phân tích (31/10):** analyze.py tạo results\\report\\; phát hiện các VM chênh tốc độ tới 1,58 lần nên "
         "bổ sung bước chuẩn hóa.")
numbered("**Viết (01/11):** bài báo Word 14 trang theo mẫu, 20 slide, demo localhost, cập nhật proposal.")
numbered("**Hoàn thiện (03/11):** điền tên tác giả, đẩy repo lên GitHub, thêm link vào bài và slide, rà soát báo "
         "cáo (tham chiếu hình/bảng, trích dẫn, con số).")

doc.add_paragraph("4. Trạng thái và việc còn lại", style="Heading 1")
table(["Hạng mục", "Trạng thái"],
      [["Proposal (Mốc 1)", "Xong"], ["Code + thí nghiệm (Mốc 2)", "Xong — 237/237 lần chạy khớp ground truth"],
       ["Bài báo 12–14 trang", "Xong — 14 trang, đã rà soát"], ["Tên tác giả, link GitHub", "Xong"],
       ["Repo GitHub", "Xong — github.com/vinhha195-oss/lakehouse-p1"],
       ["Slide", "Xong — cần tự rà một lượt và xuất PDF"], ["Demo", "Xong — cần tập trình diễn"]],
      [6.0, 11.0])
para("**Các bước còn lại:**")
bullet("**Bước 1 – Xuất slide ra PDF:** mở link slide trên claude.ai → Share → Export → PDF (hoặc .pptx).")
bullet("**Bước 2 – Rà slide** một lượt; slide nào chữ tràn hoặc lệch thì sửa trực tiếp trên web.")
bullet("**Bước 3 – Tập demo khoảng 5 phút:** nhấp đúp run_demo.bat → khởi động chế độ MoR → ghi 4 batch → xóa trạm st0 → "
         "time travel xem lại st0 → compaction.")
bullet("**Bước 4 – Nộp:** PDF bài báo, slide (PDF/.pptx), link GitHub; trình diễn demo khi thuyết trình.")
para("**Lưu ý khi sửa bài:** file mẫu dùng để dựng bài ban đầu đã bị xóa, nên mọi chỉnh sửa làm trực tiếp trong "
     "Word rồi xuất lại PDF (File → Save As → PDF, hoặc powershell report\\to_pdf.ps1). Thân bài đang dùng Times New "
     "Roman, tiêu đề mục dùng Segoe UI; nếu cần thống nhất một phông, đổi trong Word trước khi xuất PDF.")

doc.save(OUT)
print("saved", OUT)
