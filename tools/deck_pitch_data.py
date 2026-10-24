"""발표 6페이지 '공 하나하나의 데이터' 그림 (2026-10-23 사용자 A안): Soroka 2025-07-04(구속 하락 경보가 울린 등판) 실제 Statcast 투구 기록.
왼쪽 표 = 1회 처음 12구 (구종·구속·릴리스 높이·옆·팔 각도·회전수·결과), 오른쪽 = 그날 93구의 릴리스 위치(포수 쪽에서 본 투수 손 위치).
원자료 일부만 예시로 싣는다 (전체 자료는 싣지 않음). 입력: data/raw/statcast/2025/*.parquet (저장소에 없음, 그림만 저장소에).
    python -m tools.deck_pitch_data   → reports/figures/deck/pitch_data.png
"""
from __future__ import annotations

import glob
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from tools import deck_assets as A

PITCHER, DATE = 647336, "2025-07-04"
TYPE = {"FF": "포심", "SI": "싱커", "SV": "슬러브", "CH": "체인지업", "PO": "견제"}
COLOR = {"FF": "#4BA3E6", "SI": "#1F4E8C", "SV": "#E07A2E", "CH": "#3F9B6C"}
RESULT = {"ball": "볼", "called_strike": "루킹 스트라이크", "swinging_strike": "헛스윙", "foul": "파울", "hit_into_play": "타격",
          "blocked_ball": "볼", "foul_tip": "파울팁", "swinging_strike_blocked": "헛스윙"}


def load() -> pd.DataFrame:
    for f in sorted(glob.glob(str(A.ROOT / "data" / "raw" / "statcast" / "2025" / "*.parquet"))):
        d = pd.read_parquet(f)
        s = d[(d["pitcher"] == PITCHER) & d["game_date"].astype(str).str.startswith(DATE)]
        if len(s):
            return s[s["pitch_type"] != "PO"].sort_values(["at_bat_number", "pitch_number"]).reset_index(drop=True)
    raise FileNotFoundError("Statcast 원자료에서 등판을 찾지 못함")


def draw(path) -> None:
    s = load()
    plt.rcParams.update({"font.family": "Malgun Gothic",          # Noto Sans KR은 가변 글꼴이라 matplotlib에서 굵기가 안 맞음
                          "axes.unicode_minus": False})
    fig = plt.figure(figsize=(13.5, 5.6), dpi=170)
    fig.patch.set_facecolor("white")
    # 왼쪽: 표
    ax = fig.add_axes([0.01, 0.09, 0.63, 0.80]); ax.axis("off")
    head = ["#", "이닝", "구종", "구속\nkm/h", "릴리스 높이\nm", "릴리스 옆\nm", "팔 각도\n°", "회전수\nrpm", "결과"]
    rows = []
    for i, r in s.head(12).iterrows():
        rows.append([str(i + 1), f"{r.inning}회", TYPE.get(r.pitch_type, r.pitch_type), f"{r.release_speed * 1.609:.1f}",
                     f"{r.release_pos_z * 0.3048:.2f}", f"{r.release_pos_x * 0.3048:.2f}", f"{r.arm_angle:.1f}", f"{int(r.release_spin_rate):,}",
                     RESULT.get(r.description, r.description)])
    xs = [0.0, 0.05, 0.13, 0.25, 0.37, 0.51, 0.64, 0.75, 0.87]
    for x, h in zip(xs, head):
        ax.text(x, 0.97, h, fontsize=10.5, fontweight="bold", color="#111", va="top", transform=ax.transAxes)
    ax.plot([0, 1.02], [0.87, 0.87], color="#111", lw=1.4, transform=ax.transAxes, clip_on=False)
    for k, row in enumerate(rows):
        y = 0.825 - k * 0.069
        if k % 2 == 0:
            ax.add_patch(plt.Rectangle((-0.01, y - 0.046), 1.03, 0.069, color="#f2f4f7", transform=ax.transAxes, zorder=0, lw=0))
        pt = s.loc[k, "pitch_type"]
        for j, (x, v) in enumerate(zip(xs, row)):
            ax.text(x, y - 0.012, v, fontsize=11, color=COLOR.get(pt, "#111") if j == 2 else "#111", fontweight="bold" if j in (2, 3) else None,
                    va="center", transform=ax.transAxes)
    ax.text(0, -0.06, f"…  이 등판 {len(s)}구 전부, 공마다 같은 항목이 기록됩니다", fontsize=10.5, color="#555", transform=ax.transAxes)
    # 오른쪽: 릴리스 위치
    bx = fig.add_axes([0.70, 0.13, 0.28, 0.72])
    for pt, g in s.groupby("pitch_type"):
        bx.scatter(g.release_pos_x * 0.3048, g.release_pos_z * 0.3048, s=26, color=COLOR.get(pt, "#888"), alpha=0.85, label=f"{TYPE.get(pt, pt)} {len(g)}", edgecolor="white", lw=0.4)
    bx.set_title(f"그날 {len(s)}구의 릴리스 위치 (포수 쪽에서 봄)", fontsize=11, loc="left", fontweight="bold")
    bx.set_xlabel("옆 위치 (m)", fontsize=10); bx.set_ylabel("높이 (m)", fontsize=10)
    bx.set_xlim(-1.25, -0.45); bx.set_ylim(1.45, 2.05)                # 손 위치가 공마다 거의 같다는 걸 보이게 넓게
    bx.tick_params(labelsize=9)
    for sp in ("top", "right"):
        bx.spines[sp].set_visible(False)
    bx.grid(alpha=0.3)
    bx.legend(fontsize=9, frameon=False, loc="lower right")
    fig.text(0.01, 0.955, "Michael Soroka · 2025년 7월 4일 등판 — 공 하나하나의 투구 추적 기록", fontsize=13.5, fontweight="bold", color="#111")
    fig.text(0.99, 0.955, "자료: MLB Statcast(Baseball Savant) 공개 데이터", fontsize=9.5, color="#666", ha="right")
    fig.savefig(path, facecolor="white")
    plt.close(fig)


PRIVATE = Path("C:/work/private/pitchsignal/시안/deck")           # 원자료 행을 그대로 보이는 그림은 저장소 밖
RAW_COLS = ["game_date", "player_name", "pitch_type", "release_speed", "release_pos_x", "release_pos_z", "release_spin_rate", "arm_angle", "description"]


def raw_csv(path) -> int:
    """A용: 그 등판의 원자료 행(견제 제외 92구)을 열 119개 그대로 csv로 — 엑셀로 열어 화면을 찍는다 (scratch의 excel_shot.ps1)."""
    s = load()
    s.to_csv(path, index=False, encoding="utf-8-sig")          # BOM이 없으면 엑셀이 선수 이름의 악센트 글자를 깨뜨림
    return len(s)


def raw_zoom(path) -> None:
    """B용: 원자료 핵심 열 9개를 영어 열 이름·원래 단위(mph, ft) 그대로 확대한 표, 공 1~10 (2026-10-24 사용자: 가공 없이 raw 그대로)."""
    s = load().head(10)
    plt.rcParams.update({"font.family": "Consolas", "axes.unicode_minus": False})
    fig = plt.figure(figsize=(10.2, 3.4), dpi=200); fig.patch.set_facecolor("white")
    ax = fig.add_axes([0.02, 0.03, 0.96, 0.82]); ax.axis("off")
    xs = [0.0, 0.115, 0.265, 0.345, 0.45, 0.555, 0.66, 0.79, 0.875]
    for x, h in zip(xs, RAW_COLS):
        ax.text(x, 0.98, h, fontsize=9.2, fontweight="bold", color="#111", va="top", transform=ax.transAxes)
    ax.plot([-0.01, 1.03], [0.88, 0.88], color="#111", lw=1.2, transform=ax.transAxes, clip_on=False)
    for k, (_, r) in enumerate(s.iterrows()):
        y = 0.82 - k * 0.082
        if k % 2 == 0:
            ax.add_patch(plt.Rectangle((-0.01, y - 0.048), 1.04, 0.082, color="#f2f4f7", transform=ax.transAxes, zorder=0, lw=0))
        for x, c in zip(xs, RAW_COLS):
            v = r[c]
            ax.text(x, y, f"{v:g}" if isinstance(v, float) else str(v)[:10 if c == "game_date" else None], fontsize=9.8, color="#111", va="center", transform=ax.transAxes)
    fig.text(0.02, 0.93, "원자료 핵심 열 확대 — 열 이름과 단위(mph, ft) 그대로", fontsize=10, color="#555", fontfamily="Malgun Gothic")
    fig.savefig(path, facecolor="white")
    plt.close(fig)


def scatter(path) -> None:
    """오른쪽 점 그림만 따로 (6페이지에서 원자료 캡처 옆에 둔다)."""
    s = load()
    plt.rcParams.update({"font.family": "Malgun Gothic", "axes.unicode_minus": False})
    fig, bx = plt.subplots(figsize=(4.6, 4.9), dpi=200)
    fig.patch.set_facecolor("white")
    for pt, g in s.groupby("pitch_type"):
        bx.scatter(g.release_pos_x * 0.3048, g.release_pos_z * 0.3048, s=26, color=COLOR.get(pt, "#888"), alpha=0.85, label=f"{TYPE.get(pt, pt)} {len(g)}", edgecolor="white", lw=0.4)
    bx.set_title(f"그날 {len(s)}구의 릴리스 위치 (포수 쪽에서 봄)", fontsize=11, loc="left", fontweight="bold")
    bx.set_xlabel("옆 위치 (m)", fontsize=10); bx.set_ylabel("높이 (m)", fontsize=10)
    bx.set_xlim(-1.25, -0.45); bx.set_ylim(1.45, 2.05)
    bx.tick_params(labelsize=9)
    for sp in ("top", "right"):
        bx.spines[sp].set_visible(False)
    bx.grid(alpha=0.3)
    bx.legend(fontsize=9, frameon=False, loc="lower right")
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    out = A.OUT / "pitch_data.png"
    draw(out)
    PRIVATE.mkdir(parents=True, exist_ok=True)
    print("원자료 행:", raw_csv(PRIVATE / "soroka_20250704_raw.csv"))
    raw_zoom(PRIVATE / "raw_zoom.png")
    scatter(A.OUT / "pitch_scatter.png")
    print("저장:", out, PRIVATE)
