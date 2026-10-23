"""발표자료 장식 그림 (2026-10-22, 사용자: 'Beyond Goals' 템플릿과 같은 느낌 — 구겨진 종이 바탕, 찢어진 검정 상자, 붓 자국 X·O, 사선 줄무늬).
템플릿 PDF는 쪽마다 통째로 그림이라 요소를 떼어 쓸 수 없어 같은 모양을 직접 그린다. 모두 난수 씨앗을 고정해 다시 그려도 같다.
  python -m tools.deck_assets            → reports/figures/deck/*.png
  frame(src, dst)                        → 화면 캡처에 찢어진 종이 테두리와 그림자를 둘러 저장 (build_deck가 부른다)
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy.ndimage import gaussian_filter

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "figures" / "deck"
BLUE, LIGHT_BLUE, INK = (75, 163, 230), (190, 224, 248), (17, 17, 17)
W, H = 1920, 1080


def paper(path: Path, dark: bool = False, seed: int = 7) -> None:
    """구겨진 종이: 큰 굴곡과 날카로운 접힌 선(능선)을 높이로 두고 왼쪽 위에서 빛을 비춘다."""
    rng = np.random.default_rng(seed)
    h = gaussian_filter(rng.standard_normal((H, W)), 70) * 2500 + gaussian_filter(rng.standard_normal((H, W)), 22) * 120
    yy, xx = np.mgrid[0:H, 0:W]
    for _ in range(22):                                   # 접힌 선: 임의의 선분까지 거리로 만든 좁은 능선·골
        x0, y0, ang = rng.uniform(0, W), rng.uniform(0, H), rng.uniform(0, np.pi)
        d = (xx - x0) * np.sin(ang) - (yy - y0) * np.cos(ang)
        along = (xx - x0) * np.cos(ang) + (yy - y0) * np.sin(ang)
        length = rng.uniform(250, 1400)
        fade = np.clip(1 - np.abs(along) / length, 0, 1)
        h += rng.uniform(1.0, 2.5) * np.exp(-np.abs(d) / rng.uniform(6, 30)) * fade * rng.choice([-1, 1])
    gy, gx = np.gradient(gaussian_filter(h, 1.0))
    shade = -(gx + gy)
    shade = np.clip(shade / (np.percentile(np.abs(shade), 99.5) + 1e-9), -1, 1)
    grain = gaussian_filter(rng.standard_normal((H, W)), 0.7) * (2.5 if dark else 3.5)
    base, amp = (24.0, 9.0) if dark else (234.0, 15.0)
    v = np.clip(base + amp * shade + grain, 0, 255)
    rgb = np.stack([v, v, v + 1.5], -1).clip(0, 255).astype(np.uint8)
    Image.fromarray(rgb).save(path, optimize=True)

def _rough_polygon(w: int, h: int, rng, amp: float, step: int = 6) -> list[tuple[float, float]]:
    """가장자리가 찢어진 직사각형 꼭짓점 (안쪽으로 들쭉날쭉)."""
    pts = []
    def edge(a, b, n):
        for t in np.linspace(0, 1, n, endpoint=False):
            x, y = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
            nx, ny = -(b[1] - a[1]), (b[0] - a[0])
            ln = np.hypot(nx, ny); nx, ny = nx / ln, ny / ln
            j = abs(rng.normal(0, amp)) + amp * 0.3
            pts.append((x - nx * j, y - ny * j))
    m = amp * 2
    corners = [(m, m), (w - m, m), (w - m, h - m), (m, h - m)]
    for a, b in zip(corners, corners[1:] + corners[:1]):
        edge(a, b, max(8, int(np.hypot(b[0] - a[0], b[1] - a[1]) / step)))
    return pts


def torn_box(path: Path, w: int, h: int, color=INK, seed: int = 1, amp: float = 5.0) -> None:
    """찢어진 종이 상자 (투명 바탕). 글자는 PPT 글상자로 위에 얹는다."""
    rng = np.random.default_rng(seed)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(im).polygon(_rough_polygon(w, h, rng, amp), fill=color + (255,))
    a = np.array(im).astype(float)
    a[..., :3] += rng.standard_normal((h, w, 1)) * 6           # 종이 결
    Image.fromarray(a.clip(0, 255).astype(np.uint8)).save(path)


def _stroke(draw, pts: np.ndarray, width: float, color, rng) -> None:
    """붓 자국 모양(불투명 띠)을 그린다: 굵은 선 여러 개를 폭 방향으로 겹치고 끝을 가늘게. 거친 가장자리와 마른 결은 _dry가 낸다."""
    n = len(pts)
    taper = np.minimum(1, np.minimum(np.arange(n), np.arange(n)[::-1]) / (n * 0.18) + 0.35)
    for off in np.linspace(-0.5, 0.5, 9):
        seg = []
        for i in range(n):
            j0, j1 = max(0, i - 1), min(n - 1, i + 1)
            dx, dy = pts[j1][0] - pts[j0][0], pts[j1][1] - pts[j0][1]
            ln = np.hypot(dx, dy) + 1e-9
            o = off * width * taper[i] + rng.normal(0, width * 0.03)
            seg.append((pts[i][0] - dy / ln * o, pts[i][1] + dx / ln * o))
        draw.line(seg, fill=color + (255,), width=max(3, int(width * 0.16)), joint="curve")


def _dry(im: Image.Image, rng, color) -> Image.Image:
    """가장자리를 거칠게, 안쪽에 마른 붓 결(작은 빈틈)을 낸다."""
    a = np.array(im).astype(float)
    alpha = a[..., 3] / 255
    noise = gaussian_filter(rng.standard_normal(alpha.shape), 1.6)
    edge = gaussian_filter(alpha, 2.5) + 0.22 * noise / (noise.std() + 1e-9)
    keep = (edge > 0.55) & (noise > -1.9 * noise.std()) & (gaussian_filter(alpha, 3) > 0.25)
    a[..., :3] = color                                     # 겹친 선 사이 빈칸이 검게 남지 않게 색을 한 가지로
    a[..., 3] = keep * 255
    return Image.fromarray(a.astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.5))

def brush_x(path: Path, size: int = 420, color=BLUE, seed: int = 3) -> None:
    rng = np.random.default_rng(seed)
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    m = size * 0.14
    for (x0, y0, x1, y1) in ((m, m, size - m, size - m * 1.2), (size - m, m * 1.1, m * 1.1, size - m)):
        t = np.linspace(0, 1, 60)
        pts = np.c_[x0 + (x1 - x0) * t + np.sin(t * 3) * 6, y0 + (y1 - y0) * t + np.cos(t * 2) * 6]
        _stroke(d, pts, size * 0.11, color, rng)
    _dry(im, rng, color).save(path)


def brush_o(path: Path, size: int = 420, color=BLUE, seed: int = 4) -> None:
    rng = np.random.default_rng(seed)
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    t = np.linspace(0.15, 2 * np.pi + 0.35, 120)                 # 끝이 살짝 겹치는 원
    r = size * 0.36 * (1 + 0.04 * np.sin(t * 3))
    pts = np.c_[size / 2 + r * np.cos(t), size / 2 + r * np.sin(t) * 0.92]
    _stroke(d, pts, size * 0.1, color, rng)
    _dry(im, rng, color).save(path)


def stripes(path: Path, w: int = 70, h: int = 1080, color=LIGHT_BLUE) -> None:
    """세로 띠 위의 하늘색 사선 줄무늬 (템플릿 가장자리 장식)."""
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    for y in range(-w, h, 62):
        d.polygon([(0, y + w * 0.55), (w, y), (w, y + 28), (0, y + w * 0.55 + 28)], fill=color + (255,))
    im.save(path)


def frame(src: Path, dst: Path, angle: float = 0.0, border: int = 16, seed: int = 5, max_w: int = 1600) -> Path:
    """화면 캡처에 흰 종이 테두리(찢어진 가장자리)와 부드러운 그림자를 두르고 살짝 기울인다."""
    rng = np.random.default_rng(seed)
    shot = Image.open(src).convert("RGB")
    if shot.width > max_w:
        shot = shot.resize((max_w, round(shot.height * max_w / shot.width)), Image.LANCZOS)
    w, h = shot.width + 2 * border, shot.height + 2 * border
    sheet = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(sheet).polygon(_rough_polygon(w, h, rng, 3.0, step=5), fill=(250, 250, 248, 255))
    sheet.paste(shot, (border, border))
    pad = 40
    canvas = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    shadow.paste((0, 0, 0, 70), (pad + 8, pad + 10, pad + w + 8, pad + h + 10), sheet.split()[3])
    canvas = Image.alpha_composite(canvas, shadow.filter(ImageFilter.GaussianBlur(12)))
    canvas.alpha_composite(sheet, (pad, pad))
    if angle:
        canvas = canvas.rotate(angle, resample=Image.BICUBIC, expand=True)
    dst.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(dst)
    return dst

def usual_band(path: Path) -> None:
    """'평소의 나와 비교' 도식: 투수 한 명의 평소 구속 범위(띠)와, 그 아래로 이어지는 낮은 등판, 경보. 실제 자료가 아닌 설명용 그림."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    bh = Path.home() / "AppData/Local/Microsoft/Windows/Fonts/BlackHanSans-Regular.ttf"
    font_manager.fontManager.addfont(str(bh))
    rng = np.random.default_rng(21)
    n = 18
    x = np.arange(1, n + 1)
    usual = 94.4 - 0.02 * x
    v = usual + rng.normal(0, 0.22, n)
    v[-4:] = usual[-4:] - np.array([0.9, 1.3, 1.6, 2.2])
    fig, ax = plt.subplots(figsize=(7.2, 4.4), dpi=200)
    fig.patch.set_alpha(0); ax.set_facecolor("none")
    blue, ink, red = "#4BA3E6", "#111111", "#C8352E"
    ax.fill_between(x, usual - 0.75, usual + 0.75, color=blue, alpha=0.22, lw=0)
    ax.plot(x, usual, color=blue, lw=2, ls=(0, (4, 3)))
    ax.plot(x, v, color=ink, lw=1.6, marker="o", ms=7, mfc=ink)
    ax.plot(x[-1], v[-1], marker="o", ms=22, mfc="none", mec=red, mew=3)
    fp = dict(fontfamily="Black Han Sans")
    ax.text(2, usual[1] + 1.0, "평소 범위", color=blue, fontsize=20, **fp)
    ax.text(x[-5] - 3.3, v[-3] - 0.75, "평소보다 낮은 흐름", color=ink, fontsize=16, **fp)
    ax.text(x[-1] + 0.85, v[-1] - 0.12, "경보", color=red, fontsize=20, va="center", **fp)
    ax.set_ylim(usual.min() - 3.0, usual.max() + 1.8); ax.set_xlim(0.3, n + 2.6)
    ax.set_xlabel("등판", fontsize=15, color="#444444", loc="right", **fp)
    ax.text(0.45, usual.max() + 1.55, "구속", fontsize=15, color="#444444", va="top", **fp)
    ax.set_xticks([]); ax.set_yticks([])
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#555555"); ax.spines[s].set_linewidth(1.5)
    fig.savefig(path, bbox_inches="tight", transparent=True)
    plt.close(fig)

def false_alarm_case(path: Path, pid: str = "675848_2026") -> dict:
    """7페이지 실제 예 (2026-10-23 사용자 "뜬구름 잡는 느낌", "경고선은 어디서 쓰는 거고 시즌 초는 몇 경기?"):
    부상 없던 투수 한 시즌에서 '1마일(1.6km/h) 하락' 경고선과 피치시그널의 평소 범위를 나란히.
    1마일 기준은 FanGraphs(Petti, 2013: 1마일 이상 떨어진 투수 팔 부상률 11% vs 4%)에서 널리 쓰는 구속 하락 경고선이고,
    비교 실험(B1)은 이를 '시즌 시작 구간 평균'(선발 첫 8등판, 불펜 첫 15등판·직구 누적 120구 — 피치시그널의 시작 구간과 같음)에 적용했다.
    회색 = 시작 구간 등판, 회색 실선 = 그 평균, 빨간 점선 = 평균 − 1.6km/h, 빨간 × = 경고선 아래 등판, 파란 띠 = 피치시그널의 평소 범위(예상 ± 2σ)."""
    import json
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker
    import pandas as pd
    d = json.loads((ROOT / "dashboard-web/public/data/replay" / f"{pid}.json").read_text(encoding="utf-8"))
    K = 1.609
    b = [o for o in d["outings"] if o["phase"] == "baseline" and o.get("velo") is not None]
    mon = [o for o in d["outings"] if o["phase"] == "monitor" and o.get("velo") is not None]
    avg = sum(o["velo"] for o in b) / len(b) * K
    line = avg - 1.0 * K
    bx, bv = pd.to_datetime([o["date"] for o in b]), [o["velo"] * K for o in b]
    x, v = pd.to_datetime([o["date"] for o in mon]), [o["velo"] * K for o in mon]
    lo = [(o["exp"]["velo"] - 2 * o["sd"]["velo"]) * K for o in mon]; hi = [(o["exp"]["velo"] + 2 * o["sd"]["velo"]) * K for o in mon]
    fired = [vi < line for vi in v]; ours = sum(bool(o["velo_alarm"]) for o in mon)
    plt.rcParams.update({"font.family": "Malgun Gothic", "axes.unicode_minus": False})
    fig, ax = plt.subplots(figsize=(8.4, 4.6), dpi=200)
    fig.patch.set_facecolor("white"); ax.set_facecolor("white")              # 흰 바탕 — 찢어진 종이 테두리(RGB)로 감쌀 때 반투명 띠가 진하게 칠해지지 않게
    RED, BLUE_T, GRAY = "#C8352E", "#2F7FC1", "#8A8A8A"
    # 시작 구간
    ax.axvspan(bx[0] - pd.Timedelta(days=2), bx[-1] + pd.Timedelta(days=2), color="#E9E8E3", lw=0, zorder=0)
    ax.text(bx[0] + (bx[-1] - bx[0]) / 2, 162.3, f"시즌 초 {len(b)}등판\n(기준 구간)", ha="center", va="top", fontsize=10, color="#555", linespacing=1.3)
    ax.plot(bx, bv, color=GRAY, lw=1.0, marker="o", ms=4.5, zorder=3)
    ax.hlines(avg, bx[0], x[-1], color=GRAY, lw=1.3, zorder=2)
    ax.text(x[-1] + pd.Timedelta(days=4), avg, f"시즌 초 평균\n{avg:.1f}km/h", ha="left", va="center", fontsize=9.5, color="#555", linespacing=1.2)
    # 이후 등판
    ax.fill_between(x, lo, hi, color="#4BA3E6", alpha=0.22, lw=0, step="mid", zorder=1)
    ax.hlines(line, bx[0], x[-1], color=RED, linestyles=(0, (5, 4)), lw=1.6, zorder=2)
    ax.text(x[-1] + pd.Timedelta(days=4), line - 0.1, f"경고선\n{line:.1f}km/h", ha="left", va="center", fontsize=9.5, color=RED, linespacing=1.2)
    ax.plot(x, v, color="#111", lw=1.0, marker="o", ms=4.5, zorder=3)
    ax.scatter([xi for xi, f in zip(x, fired) if f], [vi for vi, f in zip(v, fired) if f], marker="x", s=70, color=RED, lw=2.2, zorder=4)
    ax.set_ylim(min(min(lo), min(v)) - 0.6, 162.5)
    ax.set_ylabel("등판 평균 직구 구속 (km/h)", fontsize=10)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(labelsize=9); ax.grid(axis="y", alpha=0.3)
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.set_xlim(bx[0] - pd.Timedelta(days=6), x[-1] + pd.Timedelta(days=30))   # 오른쪽 여백에 선 이름
    last = mdates.date2num(x[-1])
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda val, _: f"{mdates.num2date(val).month}월" if val <= last + 5 else ""))
    ax.text(0.0, 1.10, f"×  1마일(1.6km/h) 하락 경고선에 걸린 등판: {sum(fired)}번", color=RED, fontsize=10.5, fontweight="bold", transform=ax.transAxes, va="bottom")
    ax.text(0.0, 1.03, f"■  피치시그널의 평소 범위 (등판마다 다시 배움) — 경보 {ours}번", color=BLUE_T, fontsize=10.5, fontweight="bold", transform=ax.transAxes, va="bottom")
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return {"name": d["name"], "season": d["season"], "role": d["role"], "baseline": len(b), "baseline_fb": sum(o["n_fb"] for o in b),
            "baseline_dates": (b[0]["date"], b[-1]["date"]), "avg_kmh": round(avg, 1), "outings": len(mon), "rule": sum(fired), "ours": ours}

def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    paper(OUT / "paper_light.png")
    paper(OUT / "paper_dark.png", dark=True, seed=11)
    for name, (w, h), seed in (("box_wide", (1100, 300), 1), ("box_tall", (520, 760), 2), ("box_stat", (620, 240), 3), ("box_small", (520, 210), 4)):
        torn_box(OUT / f"{name}.png", w, h, seed=seed)
    torn_box(OUT / "box_blue.png", 900, 260, color=BLUE, seed=8)
    torn_box(OUT / "box_paper.png", 900, 780, color=(246, 246, 243), seed=12, amp=6.0)
    brush_x(OUT / "brush_x.png"); brush_o(OUT / "brush_o.png")
    brush_x(OUT / "brush_x_ink.png", color=(30, 40, 70), seed=9); brush_o(OUT / "brush_o_ink.png", color=(30, 40, 70), seed=10)
    stripes(OUT / "stripes.png")
    usual_band(OUT / "usual_band.png")
    print(false_alarm_case(OUT / "false_alarm_case.png"))
    print("저장:", OUT)


if __name__ == "__main__":
    main()
