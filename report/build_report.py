"""Build the Vietnamese course report (Word) in the layout of the sample report.

The sample .docx is used as a template: its styles, numbering (bullets, "1.", "[1]") and paragraph formats are
copied, its body is replaced. Inline markup in the content: **bold**, *italic*, `code`.

    python report/build_report.py [SAMPLE.docx] [OUT.docx]
"""
import copy
import os
import re
import sys

import docx
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Cm

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SAMPLE = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(r"~\Downloads\NguyenMinhHuy_BaoCao_KnowledgeGraph.docx")
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "BaoCao_P1_Lakehouse.docx")
FIG = os.path.join(ROOT, "results", "report")

doc = docx.Document(SAMPLE)
P = doc.paragraphs
# Paragraph formats taken from the sample (index of a paragraph of that kind in the sample).
TPL_INDEX = {"title": 0, "author": 1, "topic": 2, "abstract": 3, "bullet": 4, "h2": 8, "body_lead": 23,
             "step": 24, "figure": 26, "fig_caption": 27, "eq": 33, "note": 39, "tab_caption": 42, "h3": 64,
             "body": 65, "future": 94, "ref": 105}
TPL = {k: copy.deepcopy(P[i]._p.pPr) for k, i in TPL_INDEX.items()}
body = doc.element.body
sect = body.find(qn("w:sectPr"))
for child in list(body):
    if child is not sect:
        body.remove(child)

TOKEN = re.compile(r"(\*\*.+?\*\*|\*.+?\*|`.+?`)")


def run(text, bold=False, italic=False, code=False, size=None, highlight=False):
    r = OxmlElement("w:r")
    rpr = OxmlElement("w:rPr")
    if code:
        rpr.append(parse_xml(f'<w:rFonts {nsdecls("w")} w:ascii="Consolas" w:cs="Consolas" w:eastAsia="Consolas" '
                             f'w:hAnsi="Consolas"/>'))
    if bold:
        rpr.append(OxmlElement("w:b"))
        rpr.append(OxmlElement("w:bCs"))
    if italic:
        rpr.append(OxmlElement("w:i"))
        rpr.append(OxmlElement("w:iCs"))
    if highlight:
        rpr.append(parse_xml(f'<w:highlight {nsdecls("w")} w:val="yellow"/>'))
    sz = 22 if code and size is None else size
    if sz:
        rpr.append(parse_xml(f'<w:sz {nsdecls("w")} w:val="{sz}"/>'))
        rpr.append(parse_xml(f'<w:szCs {nsdecls("w")} w:val="{sz}"/>'))
    if code:
        rpr.append(parse_xml(f'<w:shd {nsdecls("w")} w:fill="EEEEEE" w:color="auto" w:val="clear"/>'))
    r.append(rpr)
    for i, part in enumerate(text.split("\t")):
        if i:
            r.append(OxmlElement("w:tab"))
        if part:
            t = OxmlElement("w:t")
            t.set(qn("xml:space"), "preserve")
            t.text = part
            r.append(t)
    return r


def runs_from_markup(text, size=None, base_bold=False, base_italic=False):
    out = []
    for tok in TOKEN.split(text):
        if not tok:
            continue
        if tok.startswith("**"):
            out.append(run(tok[2:-2], bold=True, italic=base_italic, size=size))
        elif tok.startswith("`"):
            out.append(run(tok[1:-1], code=True))
        elif tok.startswith("*"):
            out.append(run(tok[1:-1], bold=base_bold, italic=True, size=size))
        else:
            out.append(run(tok, bold=base_bold, italic=base_italic, size=size))
    return out


def add(kind, text="", runs=None, **kw):
    p = OxmlElement("w:p")
    p.append(copy.deepcopy(TPL[kind]))
    for r in (runs if runs is not None else runs_from_markup(text, **kw)):
        p.append(r)
    sect.addprevious(p)
    return p


def h2(t): add("h2", t)
def h3(t): add("h3", t)
def body_p(t): add("body", t)
def bullet(t): add("bullet", t)
def step(t): add("step", t)
def note(t): add("note", t)
def future(t): add("future", t)
def ref(t): add("ref", t, size=22)


def equation(expr, number):
    add("eq", runs=[run("\t"), run(expr, italic=True), run(f"\t({number})")])


FIG_NO = [0]
TAB_NO = [0]


def figure(path, caption, width_cm=13.0):
    FIG_NO[0] += 1
    p = doc.add_paragraph()
    p.add_run().add_picture(path, width=Cm(width_cm))
    old = p._p.pPr
    if old is not None:
        p._p.remove(old)
    p._p.insert(0, copy.deepcopy(TPL["figure"]))
    p._p.getparent().remove(p._p)
    sect.addprevious(p._p)
    add("fig_caption", runs=[run(f"Hình {FIG_NO[0]}. ", bold=True, size=22),
                             *runs_from_markup(caption, size=22, base_bold=True)])


def table(caption, header, rows, widths, align=None):
    """Table in the sample's style: grey 999999 borders, bold centred header, 11 pt text."""
    TAB_NO[0] += 1
    add("tab_caption", runs=[run(f"Bảng {TAB_NO[0]}. ", bold=True, size=22),
                             *runs_from_markup(caption, size=22, base_bold=True)])
    total = 10512
    scale = total / sum(widths)
    w = [int(x * scale) for x in widths]
    w[-1] += total - sum(w)
    align = align or (["left"] + ["center"] * (len(header) - 1))
    border = "".join(f'<w:{s} w:val="single" w:color="999999" w:sz="4"/>' for s in ("top", "left", "bottom", "right"))

    def cell(text, width, jc, bold):
        def esc(s):
            return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        parts = ""
        for tok in TOKEN.split(text):
            if not tok:
                continue
            b = bold or tok.startswith("**")
            it = tok.startswith("*") and not tok.startswith("**")
            txt = tok.strip("*`")
            parts += (f'<w:r><w:rPr>{"<w:b/><w:bCs/>" if b else ""}{"<w:i/><w:iCs/>" if it else ""}'
                      f'<w:sz w:val="22"/><w:szCs w:val="22"/></w:rPr><w:t xml:space="preserve">{esc(txt)}</w:t></w:r>')
        return (f'<w:tc><w:tcPr><w:tcW w:type="dxa" w:w="{width}"/><w:tcBorders>{border}</w:tcBorders>'
                f'<w:tcMar><w:top w:type="dxa" w:w="80"/><w:left w:type="dxa" w:w="110"/><w:bottom w:type="dxa" '
                f'w:w="80"/><w:right w:type="dxa" w:w="110"/></w:tcMar><w:vAlign w:val="center"/></w:tcPr>'
                f'<w:p><w:pPr><w:spacing w:after="0" w:line="320" w:lineRule="atLeast"/><w:jc w:val="{jc}"/></w:pPr>'
                f'{parts}</w:p></w:tc>')

    xml = (f'<w:tbl {nsdecls("w")}><w:tblPr><w:tblW w:type="dxa" w:w="{total}"/><w:tblBorders>'
           + "".join(f'<w:{s} w:val="single" w:color="auto" w:sz="4"/>'
                     for s in ("top", "left", "bottom", "right", "insideH", "insideV"))
           + "</w:tblBorders></w:tblPr><w:tblGrid>" + "".join(f'<w:gridCol w:w="{x}"/>' for x in w) + "</w:tblGrid>")
    xml += ('<w:tr><w:trPr><w:cantSplit/><w:tblHeader/></w:trPr>'
            + "".join(cell(h, w[i], "center", True) for i, h in enumerate(header)) + "</w:tr>")
    for r in rows:
        xml += ('<w:tr><w:trPr><w:cantSplit/></w:trPr>'
                + "".join(cell(str(v), w[i], align[i], False) for i, v in enumerate(r)) + "</w:tr>")
    xml += "</w:tbl>"
    sect.addprevious(parse_xml(xml))
    spacer = OxmlElement("w:p")
    spacer.append(parse_xml(f'<w:pPr {nsdecls("w")}><w:spacing w:after="60"/></w:pPr>'))
    sect.addprevious(spacer)


# =================================================================================================== content
add("title", "So sánh Delta Lake, Apache Iceberg và Apache Hudi dưới workload cập nhật nhiều trên cụm nhỏ "
             "cho dữ liệu IoT và khí tượng – thủy văn")
add("author", runs=[run("Hà Văn Vinh, Đỗ Thị Lan"), run(" · "),
                    run("Học viên cao học – Môn Big Data Analytics and Management (TLU 2026), Project P1", italic=True)])
add("topic", "**Tên đề tài:** Đánh giá thực nghiệm ba table format Lakehouse (Delta Lake, Apache Iceberg, Apache Hudi) "
             "dưới workload cảm biến có dữ liệu đến trễ, trên phần cứng nhỏ. **English:** Update-Heavy Workloads on "
             "Small Clusters: An Experimental Comparison of Delta Lake, Apache Iceberg and Apache Hudi for IoT and "
             "Hydro-Meteorological Data")
add("abstract", "**Abstract.** Các table format Lakehouse — Delta Lake, Apache Iceberg và Apache Hudi — bổ sung giao dịch "
                "ACID, time travel và schema evolution lên trên file Parquet, nhưng các đánh giá đã công bố (LHBench [3], "
                "LST-Bench [4]) chủ yếu chạy TPC-DS thiên về đọc trên cụm đám mây lớn. Dữ liệu giám sát mưa, mực nước, "
                "chất lượng nước lại khác: dữ liệu đến liên tục theo micro-batch, số đo đến trễ phải ghi đè hồi tố, và "
                "đôi khi cả một trạm-ngày bị xóa. Đề tài xây dựng **sensor-LST**, bộ sinh workload mã nguồn mở dựng trên "
                "bộ dữ liệu thủy văn TSM-Bench d1 [7], phát lại append, upsert dữ liệu trễ và xóa theo trạm, kèm "
                "ground truth để kiểm tra từng checkpoint. Ba format được đánh giá ở hai chế độ ghi Copy-on-Write (CoW) "
                "và Merge-on-Read (MoR; với Delta là deletion vectors), bốn tỷ lệ cập nhật trễ u ∈ {0, 1, 5, 20}% và ba "
                "chu kỳ compaction trên một máy 4 vCPU — tổng cộng 228 lần chạy, tất cả khớp ground truth.")
bullet("**Có dữ liệu trễ hay không mới là yếu tố quyết định chi phí, không phải tỷ lệ.** Tổng chi phí tăng 1,4–3,8 lần khi "
       "chuyển từ chỉ append sang có dữ liệu trễ, rồi gần như không đổi từ u = 1% đến 20% (chênh tối đa 8%).")
bullet("**Iceberg MoR rẻ nhất ở mọi u > 0:** rẻ hơn 2,6–4,3 lần so với mọi cấu hình Delta và Hudi; write amplification "
       "1,0–1,2 so với 9,4–11 của CoW.")
bullet("**Compaction mỗi 20 batch là đủ:** đưa độ trễ đọc của MoR về ngang CoW với 8–17 s; compaction mỗi 5 batch chỉ "
       "tốn thêm.")
bullet("**Deletion vectors của Delta tiết kiệm byte nhưng không tiết kiệm thời gian:** ghi ít hơn 8 lần về byte nhưng chậm "
       "hơn Delta CoW cả khi ghi lẫn khi đọc ở quy mô này.")
bullet("**Kết quả gắn với quy mô và phần cứng:** một node, đĩa cục bộ, dữ liệu khoảng 222 MB; không khái quát cho cụm đám "
       "mây lớn (mục Caveats).")

h2("1. Introduction")
bullet("*Bối cảnh:* kiến trúc Lakehouse [1] lưu bảng dưới dạng file cột mở trên kho lưu trữ rẻ và khôi phục các tính năng "
       "của kho dữ liệu (giao dịch, phiên bản, data skipping) bằng một lớp metadata. Ba format chiếm ưu thế là Delta "
       "Lake [2], Apache Iceberg [15] và Apache Hudi [16]; trọng tâm nghiên cứu đã chuyển từ \"có nên dùng\" sang \"đánh "
       "đổi thiết kế\": cách ghi thay đổi cấp dòng, cách tổ chức metadata, cách compaction file nhỏ [3, 4, 5].")
bullet("*Vấn đề:* dữ liệu giám sát khí tượng – thủy văn có dạng bảng rộng (mỗi dòng một trạm và một thời điểm, mỗi cột một "
       "cảm biến); số đo đến vài phút một lần, số đo trễ hoặc được hiệu chỉnh đến sau vài giờ và phải ghi đè giá trị cũ, "
       "dữ liệu của trạm hỏng bị xóa cả ngày. Đây là workload *update-heavy*, khác TPC-DS. Đồng thời các cơ quan và "
       "trường đại học ở Việt Nam thường chỉ có 1–4 máy chủ, trong khi các so sánh hiện có chạy TPC-DS 1–3 TB trên cụm "
       "đám mây [3, 4].")
bullet("*Hướng tiếp cận:* xây bộ sinh workload có kiểm soát từ dữ liệu thủy văn thật, cho mọi format ghi cùng một luồng "
       "thao tác giống hệt byte, đo chi phí ghi, đọc, compaction, metadata và time travel, và kiểm tra tính đúng đắn "
       "của mọi lần chạy.")
bullet("*RQ1:* với tỷ lệ cập nhật trễ u ∈ {0, 1, 5, 20}%, format và chế độ ghi nào có tổng chi phí (nạp + compaction + "
       "truy vấn) thấp nhất?")
bullet("*RQ2:* chu kỳ compaction nào cân bằng tốt nhất giữa số file nhỏ và độ trễ đọc?")
bullet("*RQ3:* metadata tăng thế nào theo số commit và ảnh hưởng ra sao đến time travel?")
bullet("*Giả thuyết:* (H1) ở u thấp, khác biệt chủ yếu nằm ở đường đọc như LHBench; (H2) ở u cao, MoR giảm chi phí ghi "
       "nhưng tăng độ trễ đọc cho đến khi compaction; (H3) tồn tại \"điểm gãy\" về số file nhỏ mà sau đó compaction định "
       "kỳ có lợi rõ rệt.")
bullet("*Contributions:* (C1) bộ sinh workload sensor-LST mã nguồn mở, tất định theo seed, có ground truth; (C2) so sánh có "
       "kiểm soát, tái lập được của ba format (cộng Parquet thuần) ở hai chế độ ghi và ba chu kỳ compaction, 228 lần chạy "
       "có lặp và xen kẽ ngẫu nhiên; (C3) giải thích kết quả bằng thiết kế của từng format, danh sách các \"bẫy\" khi dùng "
       "thực tế và bảng khuyến nghị; (C4) demo trực tiếp trên localhost.")

h2("2. Related Work")
bullet("*Lakehouse và table format:* cả ba format lưu dữ liệu thành file Parquet bất biến và giữ riêng một mô tả có phiên "
       "bản về các file tạo nên bảng — tương tự các run của LSM-tree [9], nên còn được gọi là log-structured tables [4]. "
       "Delta ghi mỗi commit thành file JSON trong `_delta_log` và checkpoint Parquet mỗi 10 commit [2]; Iceberg ghi cây "
       "metadata JSON → manifest list → manifest Avro cho mỗi snapshot [15]; Hudi tổ chức file group gồm base file và "
       "log file, có timeline các instant, chỉ mục khóa và cơ chế small-file handling [16].")
bullet("*Ghi thay đổi cấp dòng:* CoW ghi lại mọi file chứa dòng bị đổi; MoR ghi thay đổi rẻ rồi hợp nhất khi đọc — Iceberg "
       "dùng position-delete file [15], Hudi ghi log file [16], Delta không có MoR kiểu log mà dùng deletion vectors đánh "
       "dấu dòng đã xóa trong bitmap [17].")
bullet("*Benchmark Lakehouse:* LHBench [3] chạy TPC-DS 3 TB và kết luận khác biệt chủ yếu do thời gian đọc dữ liệu, Hudi nạp "
       "chậm hơn vì tối ưu cho upsert theo khóa; LST-Bench [4] mở rộng TPC-DS với các mẫu bảo trì, tối ưu, time travel và "
       "chỉ số ổn định hiệu năng; AutoComp [5] cho thấy small-file là vấn đề vận hành lớn ở LinkedIn; Harby và Zulkernine "
       "[6] khảo sát data lake, warehouse và lakehouse; TPC-DS [8] vẫn là workload chuẩn.")
bullet("*Dữ liệu chuỗi thời gian:* Jensen và cộng sự [10] khảo sát các hệ quản trị chuỗi thời gian; TSM-Bench [7] đánh giá 7 "
       "TSDB với truy vấn từ bài toán giám sát nước. Đề tài dùng lại dữ liệu và phong cách truy vấn của TSM-Bench nhưng "
       "thêm hiệu chỉnh trễ và xóa — điều mà mạng quan trắc thật gặp phải.")
bullet("*Phương pháp benchmark trên cloud:* hiệu năng trên máy dùng chung biến động theo thời gian và giữa các máy cùng loại "
       "[11, 12]; cách khắc phục là lặp nhiều lần, xen kẽ ngẫu nhiên các hệ được so sánh trên cùng máy, báo cáo độ phân "
       "tán và dùng cấu hình hiệu chuẩn.")
bullet("*Vị trí của đề tài:* chưa có nghiên cứu công bố nào kết hợp workload cảm biến cập nhật nhiều, cả hai chế độ ghi, chu "
       "kỳ compaction có kiểm soát và phần cứng một node.")

h2("3. Proposed Method")
add("body_lead", "Hình 1 tóm tắt kiến trúc: phần chuẩn bị sinh luồng thao tác một lần cho mỗi mức u; phần thực thi phát lại "
                 "luồng đó trên từng layout trong một JVM mới và kiểm tra với ground truth tại mỗi checkpoint.")
figure(os.path.join(HERE, "figures", "fig_architecture_vi.png"),
       "Kiến trúc hệ thống thí nghiệm. Đường nét đứt: luồng thao tác đã sinh được mọi adapter đọc như nhau.", 12.5)
step("**Chuẩn bị dữ liệu:** đọc thẳng file nén của TSM-Bench d1 (CSV 4,8 GB) theo dòng, không giải nén ra đĩa; giữ 10 trạm "
     "× 20 cảm biến × 17 ngày (1,47 triệu dòng, 253 MB Parquet); thêm cột `day` (phân vùng) và `ingest_batch`.")
step("**Bộ sinh workload sensor-LST:** nạp 7 ngày lịch sử, rồi 40 micro-batch, mỗi batch 6 giờ dữ liệu mới (21.600 dòng) "
     "cộng u × 21.600 bản ghi hiệu chỉnh trễ — các khóa đã tồn tại, chọn ngẫu nhiên trong 72 giờ trước, nhận giá trị mới; "
     "cứ 10 batch xóa một trạm-ngày. Toàn bộ luồng được ghi sẵn thành Parquet trước khi chạy, nên mọi format nhận đầu "
     "vào giống hệt byte; bộ sinh đồng thời tính trạng thái mong đợi (số dòng và tổng s0) tại mỗi checkpoint.")
step("**Adapter cho bốn layout:** cùng một giao diện create / append / upsert / delete / compact / time travel / thống kê "
     "(Bảng 1). MERGE và DELETE luôn kèm vị từ `day IN (…)` để cắt tỉa phân vùng; với Hudi, khóa bản ghi là chuỗi "
     "`id_station|epoch_micros` (xem mục 6.4).")
table("Cơ chế ghi và bảo trì của từng format", ["", "Delta Lake 3.2.1", "Iceberg 1.6.1", "Hudi 0.15.0"],
      [["Nhật ký phiên bản", "JSON commit + checkpoint Parquet mỗi 10 commit", "metadata JSON → manifest list → manifest",
        "timeline instant + metadata table"],
       ["Thay đổi cấp dòng (MoR)", "deletion vector (bitmap)", "position-delete file", "log file trong file group"],
       ["Khóa bản ghi", "không (MERGE theo vị từ)", "không (MERGE theo vị từ)", "bắt buộc; chỉ mục khóa"],
       ["Compaction", "REORG … APPLY (PURGE) + OPTIMIZE", "rewrite_data_files (+ rewrite_position_delete_files)",
        "run_compaction (MoR) / run_clustering (CoW)"],
       ["Giới hạn time travel (mặc định)", "đến khi VACUUM", "đến khi expire snapshot", "chỉ timeline đang hoạt động"]],
      [2.2, 2.6, 2.6, 2.6], ["left", "left", "left", "left"])
step("**Runner và đo lường:** mỗi lần chạy là một tiến trình với JVM Spark mới; bấm giờ quanh hành động Spark hoàn tất mỗi "
     "thao tác (gồm lập kế hoạch, thực thi, commit); sau mỗi thao tác liệt kê thư mục bảng để tính byte dữ liệu và "
     "metadata đã ghi (bỏ file `.crc` vì không có trên object storage). Write amplification và tốc độ suy giảm theo "
     "(1)–(2):")
equation("WA = byte file dữ liệu đã ghi / byte của bảng cuối ghi một lần bằng Parquet snappy", 1)
equation("degradation = (L_cuối − L_đầu) / L_đầu,  L = độ trễ warm của Q1–Q5 tại checkpoint", 2)
step("**Kiểm tra đúng đắn:** tại mỗi checkpoint so số dòng và Σ s0 của bảng với ground truth của bộ sinh; một lần chạy chỉ "
     "được tính khi khớp ở cả bốn checkpoint.")
step("**Kiểm soát công bằng:** một engine (Spark 3.5.3), nén snappy cho mọi format (mặc định Iceberg là zstd, Hudi là gzip), "
     "không dọn file cũ trong lúc chạy (byte trên đĩa = byte đã ghi), xáo ngẫu nhiên thứ tự các cấu hình trong mỗi vòng "
     "lặp để các format xen kẽ trên cùng máy.")
step("**Demo:** ứng dụng Streamlit trên localhost (`run_demo.bat`): mỗi format chạy trong một tiến trình Spark riêng; người "
     "dùng bấm ghi batch, xóa trạm, compaction, xem số file, metadata, thời gian, và time travel về phiên bản bất kỳ, "
     "kể cả đọc lại trạm đã bị xóa.")
note("*Điểm khác so với LHBench / LST-Bench: workload cảm biến có hiệu chỉnh trễ và xóa thay cho TPC-DS; phần cứng một node; "
     "điều khiển chu kỳ compaction như một biến; kiểm tra ground truth ở mọi checkpoint; chuẩn hóa thời gian giữa các máy "
     "bằng cấu hình hiệu chuẩn.*")

h2("4. Dataset")
bullet("*Nguồn dữ liệu:* TSM-Bench d1 [7] gồm 10 trạm × 100 cảm biến, mẫu 10 giây, 60 ngày (5,18 triệu dòng), sinh từ chuỗi "
       "nhiệt độ và mực nước của Cơ quan Môi trường Liên bang Thụy Sĩ. Giá trị trong d1 đã chuẩn hóa, gần như phân phối đều "
       "trên [0, 1) và ít tự tương quan nên nén kém — làm tăng byte tuyệt đối nhưng ảnh hưởng như nhau tới mọi format.")
table("Tham số workload (quy mô small dùng trong mọi thí nghiệm)", ["Tham số", "Giá trị"],
      [["Trạm × cảm biến", "10 × 20 (TSM-Bench d1), mẫu 10 giây"],
       ["Lịch sử nạp ban đầu", "7 ngày — 604.800 dòng"],
       ["Micro-batch", "40 batch × 6 giờ = 10 ngày; 21.600 dòng mới mỗi batch"],
       ["Tỷ lệ cập nhật trễ u", "0, 1, 5, 20% (0–4.320 bản ghi mỗi batch), khóa trong 72 giờ trước"],
       ["Xóa / checkpoint", "xóa một trạm-ngày mỗi 10 batch; checkpoint mỗi 10 batch"],
       ["Chu kỳ compaction", "không bao giờ, mỗi 5 batch, mỗi 20 batch"],
       ["Bảng cuối", "1,43 triệu dòng, khoảng 222 MB Parquet"]], [3.2, 7.0], ["left", "left"])
bullet("*Truy vấn:* năm truy vấn theo phong cách giám sát của TSM-Bench (Bảng 3), mỗi truy vấn chạy hai lần tại mỗi checkpoint "
       "(cold, warm); time travel đọc phiên bản 5 commit trước và phiên bản đầu tiên.")
table("Các truy vấn phân tích", ["Truy vấn", "Nội dung", "Phạm vi dữ liệu"],
      [["Q1", "Trung bình theo giờ của mỗi trạm", "24 giờ gần nhất"],
       ["Q2", "Top-5 trạm theo giá trị đỉnh", "72 giờ gần nhất"],
       ["Q3", "Trung bình theo ngày và vùng (join bảng metadata trạm)", "toàn bộ lịch sử"],
       ["Q4", "Một cảm biến của một trạm trong 2 giờ", "1–2 phân vùng ngày"],
       ["Q5", "count(*) và Σ s0 (đồng thời là checksum)", "toàn bộ lịch sử"]], [1.4, 6.0, 3.0],
      ["center", "left", "left"])

h2("5. Experimental Setup")
bullet("*Ma trận:* 3 format × 2 chế độ × 4 mức u × 3 chu kỳ compaction = 72 cấu hình, cộng 4 baseline Parquet thuần (ghi lại "
       "phân vùng ngày bị ảnh hưởng khi upsert/xóa); mỗi cấu hình lặp 3 lần — 228 lần chạy, chạy theo vòng, thứ tự trong "
       "vòng xáo ngẫu nhiên có seed.")
bullet("*Phiên bản:* Spark 3.5.3 (local, toàn bộ lõi, driver 60% RAM), Delta Lake 3.2.1, Iceberg 1.6.1 (Hadoop catalog, format "
       "v2), Hudi 0.15.0; Java 21, Python 3.13 (cả bốn layout đã được kiểm tra cho kết quả giống hệt trên Java 11/21 và "
       "Python 3.12/3.13).")
bullet("*Phần cứng:* notebook CPU của Kaggle (4 vCPU, 31,3 GB RAM, Linux, đĩa cục bộ), chạy nền; mỗi mức u là một notebook "
       "riêng trên một VM riêng, mất 2–6 giờ.")
bullet("*Hiệu chuẩn máy:* mỗi VM chạy lặp cấu hình Delta CoW, u = 0. Cùng cấu hình mất 65, 103, 70 và 98 s trên VM của các "
       "mức u = 0, 1, 5, 20% — hai VM chậm hơn khoảng 1,5 lần. So sánh giữa các format luôn trong cùng một VM; so sánh giữa "
       "các mức u dùng thời gian chia cho hệ số của VM (1,00; 1,58; 1,07; 1,50).")
bullet("*Metrics:* thời gian từng thao tác, thời gian compaction, độ trễ truy vấn cold/warm, write amplification, số file dữ liệu "
       "và file delete/log còn hiệu lực, byte và số file metadata, số phiên bản, độ trễ time travel, tốc độ suy giảm; báo "
       "cáo median và hệ số biến thiên (CV) qua 3 lần lặp.")

h2("6. Results & Ablation")
table("Kết quả ở u = 20%, không compaction và Iceberg MoR với compaction mỗi 20 batch (median 3 lần, giây quy về máy tham chiếu). Đọc = Q1–Q5 warm ở checkpoint cuối; File = dữ liệu + "
      "delete/log còn hiệu lực",
      ["Layout", "Compaction", "Nạp", "Compaction (s)", "Truy vấn", "Tổng", "WA", "Đọc", "File"],
      [["Iceberg MoR", "–", "51", "0", "8", "**59**", "1,16", "2,24", "167+154"],
       ["Parquet (ghi lại)", "–", "84", "0", "3", "87", "9,53", "0,70", "84+0"],
       ["Iceberg CoW", "–", "105", "0", "3", "108", "9,37", "0,63", "17+0"],
       ["Hudi MoR", "–", "154", "0", "11", "165", "2,51", "2,87", "5+124"],
       ["Delta CoW", "–", "200", "0", "7", "207", "9,37", "1,64", "17+0"],
       ["Hudi CoW", "–", "204", "0", "3", "207", "11,00", "0,80", "11+0"],
       ["Delta DV", "–", "233", "0", "19", "251", "1,16", "4,52", "167+154"],
       ["Iceberg MoR", "mỗi 20", "51", "8", "4", "**63**", "2,34", "0,65", "17+10"]],
      [2.4, 1.4, 0.9, 1.3, 1.1, 0.9, 0.9, 0.9, 1.3])
figure(os.path.join(FIG, "fig_rq1_total_cost.png"),
       "Tổng chi phí (nạp + compaction + mọi truy vấn checkpoint; median 3 lần, chuẩn hóa theo VM) theo tỷ lệ cập nhật trễ. "
       "Nét liền: CoW; nét đứt: MoR / deletion vectors.")

h3("6.1 RQ1 – Tỷ lệ cập nhật và tổng chi phí")
body_p("Bước nhảy nằm ở chỗ có hay không có dữ liệu trễ, không nằm ở giá trị u. Chuyển từ chỉ append sang có dữ liệu trễ làm "
       "tổng chi phí tăng 3,3–3,8 lần với các layout CoW (Delta 3,4; Iceberg 3,5; Parquet 3,8), 3,3 lần với Delta DV, 2,2 lần "
       "với Iceberg MoR và 1,4–1,7 lần với Hudi (Hình 2). Từ u = 1% đến u = 20%, chi phí của mọi layout chênh nhau "
       "tối đa 8%. Ở u = 1%, mỗi batch đã có 216 bản ghi hiệu chỉnh rải trên 72 giờ, tức trên bốn phân vùng ngày chỉ có vài "
       "file mỗi phân vùng, nên hầu như mọi file của các phân vùng đó đều bị chạm tới. CoW vì vậy ghi lại đúng những file ấy "
       "dù 216 hay 4.320 dòng thay đổi.")
body_p("Iceberg MoR rẻ nhất ở mọi u > 0 (58–63 s), so với 1,4–1,6 lần ở Parquet thuần, 1,6–1,8 lần ở Iceberg CoW, 2,6–2,8 lần "
       "ở Hudi MoR và 3,3–4,3 lần ở các cấu hình Delta và Hudi CoW. Ở u = 0, Parquet thuần nhanh nhất (24 s), tiếp theo là "
       "Iceberg (27–28 s); Hudi chậm nhất (120–122 s) do small-file handling gộp bản ghi mới vào base file có sẵn. Write "
       "amplification (Hình 3) cho thấy cơ chế: mọi layout CoW ghi khoảng 9,4 lần kích thước bảng (Hudi CoW 11,0) khi u > 0, "
       "trong khi Delta DV và Iceberg MoR chỉ 1,03–1,16. Nhưng byte không phải là thời gian: Delta DV ghi ít byte hơn Delta CoW "
       "8 lần mà nạp chậm hơn 9–17%, còn Iceberg MoR biến khoản tiết kiệm đó thành tốc độ nạp nhanh gấp đôi Iceberg CoW. "
       "Giả thuyết H1 không đúng với workload này: ở quy mô gigabyte, các format khác nhau chủ yếu ở đường *ghi*.")
figure(os.path.join(FIG, "fig_write_amplification.png"), "Write amplification khi không compaction.", 11.5)

h3("6.2 RQ2 – Chu kỳ compaction")
figure(os.path.join(FIG, "fig_rq2_compaction.png"),
       "Độ trễ đọc cuối lần chạy và số file còn hiệu lực theo chu kỳ compaction (u = 20%).")
body_p("Không compaction, MoR trả giá khi đọc. Sau 40 batch ở u = 20%, Delta DV và Iceberg MoR giữ 167 file dữ liệu cộng 154 "
       "deletion vector hoặc delete file; Hudi MoR giữ 5 base file và 124 log file; CoW chỉ 11–17 file. Độ trễ warm Q1–Q5 "
       "tương ứng 2,24 s (Iceberg MoR), 2,87 s (Hudi MoR), 4,52 s (Delta DV), so với 0,63; 0,80 và 1,64 s ở chế độ CoW của "
       "cùng format. Theo thời gian (Hình 5), độ trễ CoW giảm nhẹ khi JVM nóng lên (−9% đến −26%), còn Iceberg MoR tăng 24% "
       "và Hudi MoR tăng 15%; Hudi MoR nhảy lên giữa batch 20 và 30 — đó là \"điểm gãy\" về số file nhỏ (H3) trong dữ liệu.")
body_p("Compaction mỗi 20 batch là đủ: Iceberg MoR còn 0,65 s và Hudi MoR 1,11 s, trong vòng 3–40% so với CoW, với 8 s "
       "(Iceberg) và 17 s (Hudi) compaction cho cả lần chạy. Compaction mỗi 5 batch không đọc nhanh hơn (0,75 và 1,20 s) mà "
       "tốn gấp đôi (16 và 36 s). Với CoW, compaction không đem lại gì khi u > 0 vì mỗi batch đã ghi lại phân vùng bị chạm "
       "thành một file. H2 đúng với Iceberg và Hudi nhưng không đúng với Delta.")
figure(os.path.join(FIG, "fig_rq2_degradation.png"), "Độ trễ warm Q1–Q5 trong suốt lần chạy, không compaction (u = 20%).", 7.0)
table("Độ trễ warm từng truy vấn ở checkpoint cuối, u = 20% (giây, median 3 lần)", ["Layout (compaction)", "Q1", "Q2", "Q3", "Q4", "Q5"],
      [["Iceberg CoW (không)", "0,09", "0,10", "0,28", "0,05", "0,10"], ["Iceberg MoR (không)", "0,14", "0,22", "1,07", "0,07", "0,75"],
       ["Iceberg MoR (mỗi 20)", "0,12", "0,11", "0,26", "0,06", "0,08"], ["Hudi CoW (không)", "0,15", "0,12", "0,37", "0,06", "0,10"],
       ["Hudi MoR (không)", "0,15", "0,28", "1,28", "0,16", "0,95"], ["Hudi MoR (mỗi 20)", "0,14", "0,20", "0,47", "0,08", "0,22"],
       ["Delta CoW (không)", "0,28", "0,29", "0,54", "0,25", "0,33"], ["Delta DV (không)", "0,87", "0,84", "1,46", "0,66", "0,82"],
       ["Delta DV (mỗi 20)", "0,54", "0,46", "0,85", "0,46", "0,51"], ["Parquet (ghi lại)", "0,12", "0,13", "0,27", "0,06", "0,10"]],
      [3.6, 1.2, 1.2, 1.2, 1.2, 1.2])
body_p("Bảng 5 cho thấy truy vấn nào chịu thiệt của MoR. Với Iceberg và Hudi, thiệt hại dồn vào các truy vấn quét toàn bộ lịch "
       "sử: Q3 chậm hơn CoW 3,5–3,9 lần và Q5 chậm hơn 7,8–9,7 lần vì phải mở mọi file dữ liệu kèm delete/log file; các truy "
       "vấn kiểu dashboard trên dữ liệu gần đây (Q1, Q4) gần như không bị ảnh hưởng nhờ cắt tỉa phân vùng. Delta DV thì khác: "
       "cả năm truy vấn đều chậm hơn Delta CoW 2,5–3,1 lần, kể cả sau khi đã xóa hết deletion vector (2,86 so với 1,52 s với "
       "cùng 17 file) — chỉ riêng việc bật tính năng này đã làm chậm mỗi truy vấn khoảng 0,2–0,3 s.")

h3("6.3 RQ3 – Metadata và time travel")
figure(os.path.join(FIG, "fig_rq3_metadata.png"),
       "Metadata trên đĩa và độ trễ time travel về phiên bản 5 commit trước, theo batch (u = 20%, không compaction).")
body_p("Metadata tăng tuyến tính nhưng với tốc độ rất khác nhau. Mỗi micro-batch, log của Delta CoW tăng 11 KB (0,45 MB sau 45 "
       "phiên bản), Hudi 31–32 KB (1,4 MB), Delta DV 67 KB và Iceberg 72 KB ở cả hai chế độ (2,4–2,5 MB). Iceberg ghi metadata "
       "JSON, manifest list và manifest mới cho mỗi snapshot; log của Delta DV tăng nhanh gấp sáu lần Delta CoW vì mỗi commit "
       "thêm lại mọi file bị chạm kèm deletion vector mới, và bảng DV giữ nhiều file gấp mười lần (167 so với 17). Metadata "
       "của Hudi vẫn tăng sau khi timeline đầy, nhưng chỉ 23 phiên bản còn time travel được: các instant cũ bị archive kể cả "
       "khi đã tắt cleaner.")
body_p("Độ trễ time travel đi theo số delete/log file chứ không theo kích thước metadata. Đọc phiên bản 5 commit trước mất "
       "0,04–0,12 s với Iceberg CoW và khoảng 0,3 s với Hudi CoW, không đổi suốt lần chạy; khoảng 1,5 s với Delta ở cả hai "
       "chế độ, cũng không đổi nhờ checkpoint log mỗi 10 commit. Hai format MoR tích lũy delete thì chậm dần: Iceberg MoR từ "
       "0,30 lên 0,70 s, Hudi MoR từ 0,68 lên 1,22 s.")

h3("6.4 Phân tích theo thao tác, theo thời gian và các \"bẫy\" khi dùng thực tế")
figure(os.path.join(FIG, "fig_ops.png"),
       "Độ trễ median của một thao tác ở u = 20%: một upsert micro-batch và một lần xóa trạm-ngày (không compaction), một lần "
       "compaction (cả hai chu kỳ).", 12.0)
bullet("**Một thao tác:** MERGE một batch có 4.320 bản ghi hiệu chỉnh mất 1,06 s với Iceberg MoR, 2,04 s với Iceberg CoW, 1,88 s "
       "với Parquet, 3,3–4,1 s với Hudi và 4,0–5,1 s với Delta. Xóa một trạm-ngày rẻ nhất ở Iceberg MoR (0,19 s, một delete "
       "file), 2,2–2,9 s ở Delta và Hudi. Nạp ban đầu 604.800 dòng mất 5,6–6,3 s (Parquet, Iceberg), 10,5 s (Delta), 12,9–13,2 s "
       "(Hudi) — nhất quán với nhận xét Hudi nạp chậm của LHBench [3].")
bullet("**Theo thời gian:** độ trễ nạp không tăng khi bảng lớn dần từ 0,6 lên 1,43 triệu dòng vì vị từ `day IN (…)` giới hạn "
       "mỗi MERGE trong bốn phân vùng mới nhất. Append của Delta chậm hẳn ở mỗi commit thứ 10 (5,1 s so với 0,6 s) vì commit "
       "đó ghi checkpoint log đồng bộ; append của Hudi luôn khoảng 2,2–2,4 s, gấp 7 lần Iceberg.")
bullet("**Bẫy của Hudi:** khóa ghép chứa timestamp bị `bulk_insert` và `upsert` biểu diễn khác nhau nên upsert chèn bản "
       "ghi trùng (chỉ checksum phát hiện; đề tài dùng khóa chuỗi `id_station|epoch_micros`); compaction mặc định chỉ được lập "
       "lịch sau 5 delta commit; archive chỉ giữ khoảng 23 instant cho time travel.")
bullet("**Bẫy của Iceberg và mặc định chung:** `rewrite_data_files` của Iceberg 1.6 để lại delete file hết tác dụng (23 file với "
       "compaction mỗi 5 batch, Delta để lại 0); Iceberg mặc định nén zstd, Hudi gzip, Delta snappy — giữ mặc định là đo cả bộ nén.")

h3("6.5 Độ biến thiên và hiệu chuẩn")
figure(os.path.join(FIG, "fig_variability.png"),
       "Biến thiên giữa các lần lặp và giữa các máy. Trái: tổng chi phí từng lần lặp (vạch = median). Phải: cấu hình hiệu chuẩn "
       "trên bốn VM, giây thô.", 12.0)
body_p("Cả 237 lần chạy (228 cộng 9 lần hiệu chuẩn) đều khớp số dòng và checksum ở cả bốn checkpoint. Hệ số biến thiên median "
       "của tổng chi phí qua 3 lần lặp là 3,5% (tối đa 12,7%, Iceberg CoW ở u = 20%), nên chênh lệch trên khoảng 15% nằm ngoài "
       "nhiễu. Ngược lại, cùng một cấu hình mất 65 đến 103 s trên các VM cùng loại — chênh 1,6 lần — sẽ làm sai mọi so sánh "
       "giữa các mức u nếu không chuẩn hóa.")

h2("7. Rủi ro & hạn chế")
bullet("**Một node, đĩa cục bộ:** chưa có mạng và object storage, nơi mỗi file là một request — chi phí file nhỏ ở đây là cận "
       "dưới. Giảm thiểu: chạy lại trên cụm 3–4 node với MinIO (hướng phát triển).")
bullet("**Máy dùng chung trên cloud:** tốc độ VM chênh tới 1,58 lần. Giảm thiểu: lặp 3 lần, xen kẽ ngẫu nhiên, cấu hình hiệu chuẩn, "
       "chỉ so sánh format trong cùng VM; chuẩn hóa giả định mọi layout chậm đi như nhau trên VM chậm.")
bullet("**Quy mô dữ liệu nhỏ:** bảng khoảng 222 MB, không chạy TPC-DS SF10–SF100 như đề cương ban đầu vì giới hạn phần cứng. "
       "Giảm thiểu: báo cáo rõ phạm vi; workload sensor-LST là đóng góp chính.")
bullet("**Dữ liệu d1 gần như ngẫu nhiên đều:** nén kém hơn dữ liệu cảm biến thật. Giảm thiểu: chỉ so sánh tỷ lệ giữa các format, "
       "không so sánh byte tuyệt đối với hệ thống thật.")
bullet("**Phụ thuộc phiên bản và cấu hình:** kết quả đúng cho các phiên bản đã chốt; chỉ thay đổi bộ nén, việc dọn file và lịch "
       "compaction của Hudi, mọi thiết lập được công bố trong repo.")
bullet("**Một engine:** chỉ Spark; Trino hoặc DuckDB có thể ưu tiên format khác. Giảm thiểu: đọc đa engine là hướng phát triển.")

h2("8. Kết luận & hướng phát triển")
body_p("Với bảng cảm biến cập nhật nhiều trên một node, việc có dữ liệu trễ — chứ không phải tỷ lệ — quyết định chi phí: tổng "
       "chi phí tăng 1,4–3,8 lần khi xuất hiện hiệu chỉnh trễ rồi đứng yên trong 8% từ 1% đến 20% (RQ1). Iceberg MoR là layout "
       "rẻ nhất ở mọi u > 0, và compaction mỗi 20 micro-batch khôi phục độ trễ đọc của CoW với vài giây, còn compaction mỗi 5 "
       "batch chỉ tốn thêm (RQ2). Metadata tăng tuyến tính 11–72 KB mỗi batch mà không ảnh hưởng độ trễ time travel — vốn đi "
       "theo số delete/log file; archive mặc định của Hudi giới hạn time travel ở khoảng 23 phiên bản (RQ3). Bảng 6 tóm tắt "
       "khuyến nghị cho một hệ thống giám sát quy mô nhỏ.")
table("Khuyến nghị cấu hình cho hệ thống giám sát nhỏ (một node, vài GB mỗi ngày)", ["Tình huống", "Layout", "Compaction"],
      [["Chỉ append (u = 0), cần ACID / lịch sử", "Iceberg (chế độ nào cũng được)", "mỗi 20 batch"],
       ["Chỉ append, không cần ACID", "Parquet thuần", "–"],
       ["Có dữ liệu trễ (u = 1–20%)", "**Iceberg MoR**", "mỗi 20 batch"],
       ["Đã dùng Delta Lake", "Delta CoW (tắt deletion vectors)", "tùy chọn"],
       ["Đã dùng Hudi", "Hudi MoR", "mỗi 20 batch"],
       ["Cần time travel dài", "Iceberg hoặc Delta (Hudi giữ ≈23 phiên bản)", "–"]], [4.2, 4.0, 2.0],
      ["left", "left", "center"])
future("Chạy trên cụm 3–4 node với object storage MinIO để đo ảnh hưởng của request và listing đối với file nhỏ và metadata.")
future("Đọc đa engine: Trino, DuckDB đọc Iceberg; thêm catalog (Apache Polaris, Unity Catalog).")
future("Chính sách compaction theo ngân sách kiểu AutoComp [5], kích hoạt theo số delete/log file thay vì theo chu kỳ cố định.")
future("Bổ sung TPC-DS SF10 theo giao thức LHBench / LST-Bench để có điểm neo so sánh trực tiếp.")

h2("Caveats")
bullet("Thời gian đo trên VM Kaggle dùng chung; số liệu giữa các mức u đã chuẩn hóa bằng hệ số hiệu chuẩn, chỉ dùng để so sánh "
       "tương đối. Mọi kết luận gắn với Spark 3.5.3, Delta 3.2.1, Iceberg 1.6.1, Hudi 0.15.0 và cấu hình công bố trong repo.")
bullet("Dữ liệu là bản thu nhỏ của TSM-Bench d1 (10 trạm × 20 cảm biến × 17 ngày), không phải dữ liệu trạm quan trắc thật của "
       "Việt Nam.")
bullet("Demo localhost dùng quy mô nhỏ hơn (4 trạm, 12 batch); con số thời gian trong demo chỉ minh họa.")

h2("References")
for r in [
    "Armbrust, M., Ghodsi, A., Xin, R., Zaharia, M.: Lakehouse: A New Generation of Open Platforms that Unify Data "
    "Warehousing and Advanced Analytics. CIDR 2021 (2021)",
    "Armbrust, M., et al.: Delta Lake: High-Performance ACID Table Storage over Cloud Object Stores. PVLDB 13(12), "
    "3411–3424 (2020)",
    "Jain, P., Kraft, P., Power, C., Das, T., Stoica, I., Zaharia, M.: Analyzing and Comparing Lakehouse Storage Systems. "
    "CIDR 2023 (2023) — https://www.cidrdb.org/cidr2023/papers/p92-jain.pdf",
    "Camacho-Rodríguez, J., et al.: LST-Bench: Benchmarking Log-Structured Tables in the Cloud. Proc. ACM Manag. Data 2(1) "
    "(2024). doi:10.1145/3639314",
    "Gruenheid, A., et al.: AutoComp: Automated Data Compaction for Log-Structured Tables in Data Lakes. SIGMOD-Companion "
    "2025 (2025). doi:10.1145/3722212.3724430",
    "Harby, A.A., Zulkernine, F.: Data Lakehouse: A Survey and Experimental Study. Information Systems 127 (2025)",
    "Khelifati, A., Khayati, M., Dignös, A., Difallah, D., Cudré-Mauroux, P.: TSM-Bench: Benchmarking Time Series Database "
    "Systems for Monitoring Applications. PVLDB 16(11), 3363–3376 (2023). doi:10.14778/3611479.3611532",
    "Nambiar, R.O., Poess, M.: The Making of TPC-DS. VLDB 2006 (2006)",
    "O'Neil, P., Cheng, E., Gawlick, D., O'Neil, E.: The Log-Structured Merge-Tree (LSM-Tree). Acta Informatica 33(4), "
    "351–385 (1996)",
    "Jensen, S.K., Pedersen, T.B., Thomsen, C.: Time Series Management Systems: A Survey. IEEE Trans. Knowl. Data Eng. "
    "29(11), 2581–2600 (2017)",
    "Leitner, P., Cito, J.: Patterns in the Chaos — A Study of Performance Variation and Predictability in Public IaaS "
    "Clouds. ACM Trans. Internet Technol. 16(3) (2016)",
    "Uta, A., et al.: Is Big Data Performance Reproducible in Modern Cloud Networks? NSDI 2020 (2020)",
    "Zaharia, M., et al.: Resilient Distributed Datasets: A Fault-Tolerant Abstraction for In-Memory Cluster Computing. "
    "NSDI 2012 (2012)",
    "Armbrust, M., et al.: Spark SQL: Relational Data Processing in Spark. SIGMOD 2015 (2015)",
    "Apache Iceberg: Iceberg Table Spec — https://iceberg.apache.org/spec/ (truy cập 10/2026)",
    "Apache Hudi: Table & Query Types — https://hudi.apache.org/docs/table_types (truy cập 10/2026)",
    "Delta Lake: Deletion Vectors — https://docs.delta.io/latest/delta-deletion-vectors.html (truy cập 10/2026)",
]:
    ref(r)

doc.core_properties.title = "So sánh Delta Lake, Apache Iceberg và Apache Hudi dưới workload cập nhật nhiều"
doc.core_properties.author = "Hà Văn Vinh, Đỗ Thị Lan"
doc.save(OUT)
print("saved", OUT, f"({FIG_NO[0]} figures, {TAB_NO[0]} tables)")
