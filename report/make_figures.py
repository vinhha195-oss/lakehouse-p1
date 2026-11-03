"""Figures used only by the Vietnamese report (report/build_report.py): the system architecture diagram."""
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "figures")
INK, MUTED, EDGE = "#0b0b0b", "#52514e", "#8a8984"
ACCENT = "#2a78d6"


def box(ax, x, y, w, h, title, lines=(), accent=False):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.06",
                                fc=(ACCENT + "1f") if accent else "white", ec=ACCENT if accent else EDGE,
                                lw=1.6 if accent else 1.0))
    ax.text(x + w / 2, y + h - 0.2, title, ha="center", va="top", fontsize=9.5, fontweight="bold", color=INK)
    for i, ln in enumerate(lines):
        ax.text(x + w / 2, y + h - 0.52 - 0.27 * i, ln, ha="center", va="top", fontsize=8, color=MUTED)


def arrow(ax, x1, y1, x2, y2, dashed=False):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=11, lw=1.0, color=EDGE,
                                 linestyle=(0, (4, 3)) if dashed else "solid"))


def architecture():
    fig, ax = plt.subplots(figsize=(9.2, 3.6))
    ax.set_xlim(0, 13.2)
    ax.set_ylim(0.2, 5.3)
    ax.axis("off")
    ax.text(0.1, 5.15, "Chuẩn bị (một lần cho mỗi mức u)", fontsize=9, color=MUTED, style="italic")
    ax.text(0.1, 2.5, "Thực thi (mỗi cấu hình × 3 lần lặp, JVM mới mỗi lần)", fontsize=9, color=MUTED, style="italic")
    box(ax, 0.1, 3.2, 2.9, 1.75, "TSM-Bench d1", ["CSV 4,8 GB, 10 trạm", "× 100 cảm biến, 10 s", "→ cắt 20 cảm biến,", "17 ngày (1,47 triệu dòng)"])
    box(ax, 3.5, 3.2, 3.0, 1.75, "Bộ sinh sensor-LST", ["seed, tỷ lệ cập nhật u", "append · upsert trễ ·", "xóa trạm-ngày ·", "lịch checkpoint"], accent=True)
    box(ax, 7.0, 3.2, 2.9, 1.75, "Luồng thao tác", ["base + 40 batch Parquet", "giống hệt byte cho", "mọi format", "+ ground truth"])
    box(ax, 10.4, 3.2, 2.7, 1.75, "Ma trận thí nghiệm", ["3 format × 2 chế độ", "× 4 mức u × 3 chu kỳ", "compaction + Parquet", "= 228 lần chạy"])
    box(ax, 10.4, 0.35, 2.7, 1.75, "Runner", ["Spark 3.5.3 local", "đo từng thao tác,", "đếm byte ghi, file,", "metadata, time travel"], accent=True)
    box(ax, 7.0, 0.35, 2.9, 1.75, "Adapter", ["Delta 3.2.1 (CoW / DV)", "Iceberg 1.6.1 (CoW / MoR)", "Hudi 0.15.0 (CoW / MoR)", "Parquet (ghi lại ph. vùng)"])
    box(ax, 3.5, 0.35, 3.0, 1.75, "Kiểm tra đúng đắn", ["số dòng + Σ s0 tại", "mỗi checkpoint so với", "ground truth", "(237/237 khớp)"])
    box(ax, 0.1, 0.35, 2.9, 1.75, "Phân tích", ["chuẩn hóa theo VM", "(cấu hình hiệu chuẩn)", "→ bảng, hình RQ1–RQ3"])
    arrow(ax, 3.0, 4.075, 3.5, 4.075)
    arrow(ax, 6.5, 4.075, 7.0, 4.075)
    arrow(ax, 9.9, 4.075, 10.4, 4.075)
    arrow(ax, 11.75, 3.2, 11.75, 2.1)
    arrow(ax, 10.4, 1.225, 9.9, 1.225)
    arrow(ax, 7.0, 1.225, 6.5, 1.225)
    arrow(ax, 3.5, 1.225, 3.0, 1.225)
    arrow(ax, 8.45, 3.2, 8.45, 2.1, dashed=True)
    fig.tight_layout()
    os.makedirs(OUT, exist_ok=True)
    fig.savefig(os.path.join(OUT, "fig_architecture_vi.png"), dpi=200, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    architecture()
    print("ok")
