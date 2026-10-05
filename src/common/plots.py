"""그림 공통 스타일: 흰 바탕, 옅은 격자, 한글 글꼴. 글자는 먹색 계열로만 쓰고 색은 표시(막대·선)에만 쓴다."""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

INK, INK_SECONDARY, MUTED, GRID, AXIS = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
SERIES = "#2a78d6"          # 계열이 하나일 때의 색


def use_style() -> None:
    plt.rcParams.update({
        "font.family": "Malgun Gothic", "font.size": 10, "axes.unicode_minus": False,
        "figure.facecolor": "white", "axes.facecolor": "white", "savefig.facecolor": "white",
        "text.color": INK, "axes.titlecolor": INK, "axes.labelcolor": INK_SECONDARY,
        "axes.titlesize": 11, "axes.titleweight": "bold", "axes.titlelocation": "left",
        "xtick.color": MUTED, "ytick.color": MUTED, "xtick.labelcolor": INK_SECONDARY, "ytick.labelcolor": INK_SECONDARY,
        "axes.edgecolor": AXIS, "axes.linewidth": 0.8, "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "axes.grid.axis": "y", "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
        "lines.linewidth": 2, "savefig.dpi": 200, "savefig.bbox": "tight",
    })
