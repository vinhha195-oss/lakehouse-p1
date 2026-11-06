"""Render the deck's formulas as PNG in a Times-style math font (STIX) into report/figures/."""
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

plt.rcParams.update({"mathtext.fontset": "stix", "font.family": "STIXGeneral"})
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "figures")
INK = "#1A1A1A"
FORMULAS = {
    "eq_runs": r"$N = (3 \times 2 \times 4 \times 3 + 4) \times 3 = 228$",
    "eq_wa": r"$\mathrm{WA} = \dfrac{B_{\mathrm{written}}}{B_{\mathrm{logical}}}$",
    "eq_deg": r"$D = \dfrac{L_{\mathrm{last}} - L_{\mathrm{first}}}{L_{\mathrm{first}}}$",
}

for name, tex in FORMULAS.items():
    fig = plt.figure(figsize=(0.01, 0.01))
    fig.text(0, 0, tex, fontsize=40, color=INK)
    fig.savefig(os.path.join(OUT, f"{name}.png"), dpi=200, bbox_inches="tight", pad_inches=0.04, facecolor="white")
    plt.close(fig)
    print(name)
