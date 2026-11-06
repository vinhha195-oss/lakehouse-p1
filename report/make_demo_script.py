"""Build report/KichBan_Demo.docx: the presenters' script for the live localhost demo.
Numbers come from a rehearsal of demo/worker.py and demo/test_app.py on 2026-11-05 (MoR, all three formats).
Convert to PDF with report/to_pdf.ps1."""
import os
import re

import docx
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "KichBan_Demo.docx")
FONT = "Times New Roman"
NAVY = RGBColor(0x1F, 0x3A, 0x5F)

doc = docx.Document()
sec = doc.sections[0]
sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
sec.left_margin = sec.right_margin = Cm(2.0)
sec.top_margin = sec.bottom_margin = Cm(2.0)


def set_font(style, size, bold=None, color=None):
    style.font.name = FONT
    style.element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), FONT)
    rfonts = style.element.rPr.rFonts
    for key in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
        if rfonts.get(qn(key)) is not None:
            del rfonts.attrib[qn(key)]
    rfonts.set(qn("w:hAnsi"), FONT)
    style.font.size = Pt(size)
    if bold is not None:
        style.font.bold = bold
    if color is not None:
        style.font.color.rgb = color


set_font(doc.styles["Normal"], 13)
doc.styles["Normal"].paragraph_format.space_after = Pt(6)
doc.styles["Normal"].paragraph_format.line_spacing = 1.15
set_font(doc.styles["Title"], 20, True, NAVY)
set_font(doc.styles["Heading 1"], 15, True, NAVY)
set_font(doc.styles["Heading 2"], 13, True, NAVY)
set_font(doc.styles["List Bullet"], 13)
doc.styles["Heading 1"].paragraph_format.space_before = Pt(14)
doc.styles["Heading 1"].paragraph_format.space_after = Pt(6)
doc.styles["Heading 2"].paragraph_format.space_before = Pt(10)
doc.styles["Heading 2"].paragraph_format.space_after = Pt(3)
title_par = doc.styles["Title"].element.get_or_add_pPr()
for border in title_par.findall(qn("w:pBdr")):
    title_par.remove(border)


def rich(par, text):
    """**bold** and *italic* inline marks."""
    for chunk in re.split(r"(\*\*.+?\*\*|\*.+?\*)", text):
        if chunk.startswith("**"):
            par.add_run(chunk[2:-2]).bold = True
        elif chunk.startswith("*") and len(chunk) > 2:
            par.add_run(chunk[1:-1]).italic = True
        elif chunk:
            par.add_run(chunk)
    return par


def p(text):
    return rich(doc.add_paragraph(), text)


def bullet(text):
    return rich(doc.add_paragraph(style="List Bullet"), text)


def step(head, click, say, screen):
    h = doc.add_paragraph(head, style="Heading 2")
    h.paragraph_format.keep_with_next = True
    p("**Thao tác:** " + click).paragraph_format.keep_with_next = True
    p("**Nói:** “" + say + "”").paragraph_format.keep_with_next = True
    p("**Màn hình:** " + screen)


def table(head, rows, widths):
    t = doc.add_table(rows=1, cols=len(head))
    t.style = "Table Grid"
    t.autofit = False
    for i, text in enumerate(head):
        cell = t.rows[0].cells[i]
        cell.paragraphs[0].add_run(text).bold = True
    for row in rows:
        cells = t.add_row().cells
        for i, text in enumerate(row):
            rich(cells[i].paragraphs[0], text)
    for row in t.rows:
        row._tr.get_or_add_trPr().append(row._tr.makeelement(qn("w:cantSplit"), {}))
        for i, width in enumerate(widths):
            row.cells[i].width = Cm(width)
            row.cells[i].paragraphs[0].paragraph_format.space_after = Pt(2)
    doc.add_paragraph().paragraph_format.space_after = Pt(0)


doc.add_paragraph("Kịch bản demo trực tiếp", style="Title")
p("Project P1: Delta Lake, Apache Iceberg và Apache Hudi · Hà Văn Vinh, Đỗ Thị Lan")
p("**Thời lượng:** 5 phút, ngay sau slide 20. **Thông điệp cần chốt:** cùng một luồng dữ liệu cảm biến có bản ghi "
  "đến trễ, cả ba format đều cho kết quả đúng, nhưng khác nhau về tốc độ và cách lưu file; dữ liệu đã sửa hoặc "
  "đã xóa vẫn đọc lại được bằng time travel.")

doc.add_paragraph("1. Chuẩn bị trước giờ trình bày", style="Heading 1")
bullet("**Trước 10 phút:** đóng các phần mềm nặng, nhấp đúp run_demo.bat, trình duyệt mở "
       "http://localhost:8501. Giữ nguyên cửa sổ đen, đóng nó là demo dừng.")
bullet("**Thanh bên trái:** để cả ba format, chế độ **Merge-on-Read**, bấm **Khởi động / làm lại từ đầu**, "
       "chờ khoảng 1 phút.")
bullet("**Bấm sẵn một lần “Ghi batch tiếp theo (1/12)”.** Batch đầu chậm nhất vì Spark còn lạnh, không nên để "
       "người xem chờ. Bảng phải hiện **9.360 dòng**.")
bullet("Phóng to trình duyệt 125–150% cho cuối phòng đọc được, rồi mở sẵn tab này cạnh slide.")

doc.add_paragraph("2. Kịch bản từng bước", style="Heading 1")
step("Bước 1 – Giới thiệu (30 giây)",
     "chưa bấm gì, chỉ vào bảng “Trạng thái bảng”.",
     "Đây là demo chạy thật trên Spark ngay trên máy em, không phải quay sẵn. Dữ liệu thu nhỏ từ TSM-Bench: 4 trạm, "
     "5 cảm biến. Ba format cùng nhận một luồng dữ liệu. Mỗi batch là 30 phút số đo mới, kèm 20% bản ghi hiệu chỉnh "
     "đến trễ của 2 giờ trước.",
     "cả ba format đều 9.360 dòng.")
step("Bước 2 – Ghi dữ liệu có bản ghi trễ (60 giây)",
     "bấm **Ghi batch tiếp theo** 3 lần, đến khi nút hiện (5/12). Mỗi lần chờ khoảng 8–10 giây.",
     "Mỗi batch có 864 bản ghi nhưng số dòng chỉ tăng 720, vì 144 bản ghi là sửa dòng đã có, không thêm dòng mới. "
     "Thầy và các bạn nhìn biểu đồ thời gian: Iceberg nhanh nhất, khoảng 1 giây. Delta và Iceberg không ghi lại file "
     "cũ mà sinh thêm file xóa, nên số file tăng dần theo mỗi batch.",
     "bảng lên **11.520 dòng**. Delta và Iceberg có 5 file dữ liệu và 4 file xóa. Hudi vẫn 1 file dữ liệu, "
     "0 file log. Thời gian mỗi batch khoảng 1 giây (Iceberg), 2–3 giây (Hudi), 4–5 giây (Delta).")
step("Bước 3 – Time travel xem bản ghi đã sửa (90 giây)",
     "kéo xuống mục Time travel, chọn Format **Apache Iceberg**, Trạm **st3**, kéo Phiên bản về "
     "**v1 · batch 1**. Trỏ vào chấm đỏ, rồi dòng đầu tiên của bảng bên dưới.",
     "Em quay lại bảng ở thời điểm sau batch 1. Lúc đó trạm này có 2.340 dòng, hiện tại có 2.880 dòng. Có 89 số đo "
     "đã được sửa sau phiên bản này, chính là các chấm đỏ. Ví dụ dòng này: bản cũ ghi 0,6201, hiện tại là 0,0426, được sửa ở batch 3. Bản ghi mới không làm mất bản cũ, nên có thể kiểm tra lại số liệu trước khi hiệu chỉnh.",
     "dòng chú thích báo 2.340 dòng, 2.880 dòng và 89 số đo. Dòng đầu bảng là 13:10:00: 0.6201 và 0.0426, sửa ở batch 3.")
step("Bước 4 – Xóa một trạm và kiểm tra đúng đắn (60 giây)",
     "kéo lên, bấm **Xóa trạm st0 ngày 2019-03-01**. Khi thấy dòng xanh, kéo xuống đổi Trạm thành **st0**, "
     "để nguyên phiên bản v4.",
     "Giả sử trạm st0 hỏng, ta xóa dữ liệu của trạm trong ngày. Dòng xanh là kiểm tra tự động: số dòng của cả ba format "
     "đều khớp đáp án 8.640. Trong thí nghiệm chính, cả 395 lần chạy đều qua bước kiểm tra này. Trạm st0 đã mất khỏi bảng "
     "hiện tại, nhưng time travel về phiên bản trước vẫn đọc được 2.880 dòng.",
     "bảng còn **8.640 dòng**, dòng xanh “tất cả format khớp”, sau đó là cảnh báo vàng “Trạm st0 đã bị xóa… "
     "phiên bản v4 vẫn còn 2,880 dòng”.")
step("Bước 5 – Compaction (45 giây)",
     "kéo lên, bấm **Compaction**, chỉ vào bảng trạng thái.",
     "Các file nhỏ và file xóa làm đọc chậm dần, nên cần compaction để gộp lại. Số dòng không đổi, chỉ cách lưu "
     "thay đổi. Delta từ 5 file dữ liệu về 1, không còn file xóa. Iceberg cũng về 1 nhưng còn 1 delete file: đây chính "
     "là bẫy delete file “treo” nêu ở slide 17, file này đã hết tác dụng. Dung lượng đĩa tăng vì đề tài giữ file cũ "
     "cho time travel, chưa dọn.",
     "vẫn 8.640 dòng. Delta 1 file dữ liệu, 0 file xóa. Iceberg 1 file dữ liệu, 1 file xóa. Hudi 1 file dữ liệu, 0 file log.")
step("Bước 6 – Kết (15 giây)",
     "dừng tay, quay lại nhìn người nghe.",
     "Số trong demo chỉ để minh họa cơ chế. Kết luận của đề tài dựa trên 380 lần chạy: khi có dữ liệu trễ, nên chọn "
     "Iceberg Merge-on-Read, compaction mỗi 20 batch; nếu dashboard đọc nhiều thì mỗi 5 batch. Em xin hết phần demo, mời thầy và các bạn đặt câu hỏi.",
     "giữ nguyên.")

doc.add_paragraph("3. Lưu ý khi nói", style="Heading 1")
bullet("Số dòng luôn cố định. Số file có thể lệch đôi chút, và **thời gian đổi theo từng lần chạy**, nên hãy đọc số "
       "trên màn hình, đừng đọc thuộc số trong kịch bản.")
bullet("**Đừng nói Hudi tạo log file ở bước 2.** Trong demo, Hudi có 0 file log đến batch 8, khác với thí nghiệm chính.")
bullet("**Đừng tải lại trang (F5) khi đang demo:** trang sẽ quay về đầu. Nếu lỡ bấm, bấm lại **Khởi động / làm lại từ đầu** rồi ghi lại các batch.")
bullet("Đừng dùng thời gian trong demo để kết luận format nào tốt hơn, vì bảng demo rất nhỏ.")

doc.add_paragraph("4. Nếu có sự cố", style="Heading 1")
table(["Tình huống", "Cách xử lý"],
      [["Trình duyệt không tự mở", "Gõ tay http://localhost:8501"],
       ["Trang báo lỗi hoặc “worker stopped”", "Bấm **Khởi động / làm lại từ đầu**, chờ 1 phút, bấm lại batch 1. "
        "Sau buổi trình bày, xem lỗi trong work\\demo_<format>.log"],
       ["Trang trắng, không kết nối được", "Xem cửa sổ đen còn mở không; nếu đã đóng, nhấp đúp lại run_demo.bat"],
       ["Quá 2 phút vẫn chưa chạy được", "Dừng demo, chuyển sang slide 10–14 và trình bày kết quả. "
        "Nên quay sẵn một video màn hình để dự phòng"]],
      [6.5, 10.5])

doc.add_paragraph("5. Câu hỏi có thể gặp", style="Heading 1")
table(["Câu hỏi", "Gợi ý trả lời"],
      [["Sao Hudi không có file log?",
        "Bảng demo rất nhỏ nên mỗi batch Hudi ghi lại base file, đĩa tăng khoảng 1 MB mỗi batch. Từ batch 9 mới có "
        "file log. Ở thí nghiệm chính, Hudi MoR có 124 file log sau 40 batch"],
       ["Demo nhỏ có đại diện cho kết quả không?",
        "Không dùng để so sánh hiệu năng. Demo chỉ minh họa cơ chế; số liệu kết luận lấy từ thí nghiệm 1,43 triệu dòng, "
        "lặp 5 lần mỗi cấu hình"],
       ["Sau compaction còn time travel được không?",
        "Được, vì đề tài không dọn file cũ. Hệ thống thật phải chọn thời gian giữ lịch sử, dọn rồi thì mất phiên bản cũ"],
       ["Copy-on-Write khác gì?",
        "CoW ghi lại cả file chứa dòng bị đổi, đọc nhanh nhưng ghi tốn: write amplification khoảng 9,4 so với "
        "1,0–1,2 của Delta DV và Iceberg MoR. Có thể chọn CoW ở thanh bên rồi khởi động lại"],
       ["Dữ liệu demo có phải thật không?",
        "Lấy từ TSM-Bench d1, thu nhỏ còn 4 trạm × 5 cảm biến. Bản ghi hiệu chỉnh trễ do bộ sinh sensor-LST tạo, "
        "có đáp án sẵn để kiểm tra"]],
      [6.5, 10.5])

doc.add_paragraph("6. Giải thích bằng ví dụ ba chiếc xe tải", style="Heading 1")
p("Coi Delta, Iceberg và Hudi là ba xe tải chở cùng một lô hàng; mỗi dòng dữ liệu là một kiện hàng. "
  "Demo là lái thử vài vòng, còn 380 lần chạy thí nghiệm là chặng đường dài để kết luận.")
table(["Trong demo", "Trên chiếc xe"],
      [["Số dòng", "Số kiện hàng trên xe"],
       ["Batch (720 mới + 144 trễ)", "Một chuyến giao 720 kiện mới và đổi 144 kiện"],
       ["File dữ liệu", "Số thùng chứa hàng"],
       ["File xóa / log", "Phiếu ghi “kiện này bỏ, dùng kiện mới”"],
       ["Metadata", "Sổ giấy tờ theo xe"],
       ["Dữ liệu trên đĩa", "Chỗ xe chiếm trong kho"],
       ["Thời gian", "Thời gian chất hàng"],
       ["Số phiên bản, time travel", "Ảnh chụp xe sau mỗi chuyến; so ảnh cũ để biết kiện nào đã đổi"],
       ["Compaction", "Dừng xe, dồn hàng cho gọn; số kiện không đổi"]],
      [6.5, 10.5])
p("**Câu chốt:** chở hàng hay phải đổi hàng thì chọn xe Iceberg, cứ 20 chuyến dồn hàng một lần, phải lấy hàng thường xuyên thì 5 chuyến một lần: "
  "ở thí nghiệm chính, *u* = 20%, Iceberg MoR hết 63 giây, Hudi MoR 170 giây, Delta DV 256 giây.")

doc.save(OUT)
print("saved", OUT)
