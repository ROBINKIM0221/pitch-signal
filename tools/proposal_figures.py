"""제안서 v3 새 그림 두 장 (2026-10-22, 사용자 템플릿·새 흐름: 고교 먼저 → 프로).
  00_service.png  서비스 구성 — 고교(장비 없음)와 프로(추적 장비) 두 갈래, 같은 원리, 이용자
  08_hs_gap.png   규정 위반과 누적 부하 — 2025·2026 전국 고교 (숫자는 제안서 3.2절 표와 같은 화면 자료 집계)
사용 예: python tools/proposal_figures.py
"""
from __future__ import annotations

import json

import matplotlib.pyplot as plt

from src.common import figures as F
from src.common import plots

HS = F.OK            # 고교 = 초록
PRO = F.VELO         # 프로 = 파랑
GAP = [("규정 위반 투수", "violating_pitchers"), ("규정은 지켰지만\n누적 부하 표시", "compliant_with_load"),
       ("7일 합\n150구 이상 경험", "pitchers_7d_150"), ("시즌\n500구 이상", "pitchers_season_500")]


def gap_values() -> dict[int, list[int]]:
    """highschool.json 전국 요약(totals)에서 해마다 GAP 순서의 투수 수."""
    d = json.loads((F.DASH / "highschool.json").read_text(encoding="utf-8"))
    return {x["season"]: [int(x["totals"][k]) for _, k in GAP] for x in d["datasets"] if x["mode"] == "season"}


NAVY, LINE, BAND = "#1f3b5c", "#b8b7b0", "#f5f5f2"


def _panel(ax, x, y, w, h, title, body, fs, title_color=NAVY):
    """제목 띠 + 본문 상자 (2026-10-25 사용자: 초록·파랑 테두리 상자 대신 — 남색 제목 띠, 흰 상자, 회색 선)."""
    from matplotlib.patches import FancyBboxPatch
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.012", facecolor="white", edgecolor=LINE, linewidth=1.0))
    ax.add_patch(FancyBboxPatch((x, y + h - 0.052), w, 0.052, boxstyle="round,pad=0,rounding_size=0.012", facecolor=title_color, edgecolor=title_color, linewidth=1.0))
    ax.add_patch(plt.Rectangle((x, y + h - 0.052), w, 0.02, facecolor=title_color, edgecolor="none"))   # 띠 아래쪽 모서리는 각지게
    ax.text(x + w / 2, y + h - 0.026, title, ha="center", va="center", fontsize=fs, fontweight="bold", color="white")
    ax.text(x + w / 2, y + (h - 0.052) / 2, body, ha="center", va="center", fontsize=fs - 0.3, color=plots.INK, linespacing=1.45)


def draw_service(path) -> None:
    """세 열(입력 → 처리 → 화면)과 두 갈래(고교·프로). 띠 두 개에 상자 — 색은 남색 하나만."""
    plots.use_style()
    fig, ax = plt.subplots(figsize=(9, 6.9))
    ax.set_xlim(-0.01, 1.01); ax.set_ylim(0.0, 1.0); ax.axis("off"); ax.grid(False)
    fs = 8.8
    for x, t in ((0.13, "입력"), (0.465, "처리"), (0.835, "화면")):
        ax.text(x, 0.985, t, ha="center", va="center", fontsize=11, fontweight="bold", color=plots.INK_SECONDARY)
    for (y0, y1, head, users) in ((0.515, 0.95, "고교 야구  —  투구 추적 장비 없음, 공식 기록과 손기록지로", "이용자  고교 선수 · 고교 지도자 · 대회 운영본부 · 스카우터 · 대학 감독"),
                                  (0.0, 0.435, "프로 (MLB · KBO)  —  투구 추적 장비, 공 하나하나의 구속과 폼", "이용자  구단 분석·트레이닝 · 불펜 운영 · 구단 해외 스카우트")):
        ax.add_patch(plt.Rectangle((0.0, y0), 1.0, y1 - y0, facecolor=BAND, edgecolor="none", zorder=0))
        ax.text(0.015, y1 - 0.03, head, fontsize=10.5, fontweight="bold", color=NAVY, va="center")
        ax.text(0.015, y0 + 0.028, users, fontsize=fs - 0.4, color=plots.INK_SECONDARY, va="center")
    L, M, R = (0.015, 0.235), (0.29, 0.36), (0.69, 0.295)     # 왼쪽·가운데·오른쪽 상자 (x, 폭)
    # 고교
    _panel(ax, L[0], 0.735, L[1], 0.135, "협회 경기 기록", "날짜 · 투구 수\n타석 결과", fs)
    _panel(ax, L[0], 0.575, L[1], 0.135, "손기록지 사진", "공마다 그린\n볼 · 스트라이크", fs)
    _panel(ax, M[0], 0.735, M[1], 0.135, "규정 판정 + 누적 부하", "하루 105구 · 의무 휴식 · 3일 연속\n7일 120·150구 · 3일 내 70·100구", fs)
    _panel(ax, M[0], 0.575, M[1], 0.135, "판독 모델", "모델 판정 → 확신 낮은 칸\n다시 읽기 → 검산", fs)
    _panel(ax, R[0], 0.575, R[1], 0.295, "고교 화면", "투구수 현황판\n선수 시즌 카드\n(누적 부하 · 볼 비율 · 성적)\n투수 운용 계획판\n전국체전 달력", fs)
    for y in (0.78, 0.62):
        F._arrow(ax, L[0] + L[1], y, M[0], y, color=NAVY)
    F._arrow(ax, M[0] + M[1], 0.7, R[0], 0.7, color=NAVY)
    # 연결
    ax.annotate("", xy=(0.5, 0.44), xytext=(0.5, 0.51), arrowprops=dict(arrowstyle="-|>", color=NAVY, lw=1.4))
    ax.text(0.52, 0.475, "같은 투수의 다음 단계", fontsize=fs - 0.3, color=plots.INK_SECONDARY, va="center")
    # 프로
    _panel(ax, L[0], 0.225, L[1], 0.135, "투구 추적 데이터", "공마다 구속 · 릴리스\n팔 각도", fs)
    _panel(ax, L[0], 0.065, L[1], 0.135, "경기 기록", "불펜 사용\n(등판일 · 투구 수)", fs)
    _panel(ax, M[0], 0.225, M[1], 0.135, "평소와 비교", "등판마다 갱신하는 평소 · 가변 표본 표준화\n구속 하락(주) · 폼 변화(보조) · 100등판에 1회", fs)
    _panel(ax, M[0], 0.065, M[1], 0.135, "사용 관리", "연투 · 3일 등판 · 최근 7일 75구", fs)
    _panel(ax, R[0], 0.065, R[1], 0.295, "프로 화면", "투수 시즌 상세 · 경보 카드\n팀 불펜 현황판\nKBO 외국인 투수\n영입 전 점검", fs)
    F._arrow(ax, L[0] + L[1], 0.27, M[0], 0.27, color=NAVY); F._arrow(ax, L[0] + L[1], 0.11, M[0], 0.11, color=NAVY)
    F._arrow(ax, M[0] + M[1], 0.19, R[0], 0.19, color=NAVY)
    fig.savefig(path)
    plt.close(fig)

def draw_hs_gap(path) -> None:
    plots.use_style()
    fig, ax = plt.subplots(figsize=(9, 3.9))
    xs = range(len(GAP)); w = 0.36; values = gap_values()
    for k, (year, color) in enumerate(((2025, "#9dc1ec"), (2026, F.VELO))):
        vals = values[year]
        bars = ax.bar([x + (k - 0.5) * w for x in xs], vals, width=w, color=color, label=f"{year}년 전국 고교")
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v + 4, f"{v}", ha="center", va="bottom", fontsize=9.5, color=plots.INK)
    ax.set_xticks(list(xs), [g[0] for g in GAP], fontsize=9.5)
    ax.set_ylabel("투수 수(명)"); ax.set_ylim(0, 310)
    ax.legend(frameon=False, fontsize=9, loc="upper left")
    fig.savefig(path)
    plt.close(fig)


if __name__ == "__main__":
    draw_service(F.FINAL / "00_service.png")
    draw_hs_gap(F.FINAL / "08_hs_gap.png")
    print("저장:", F.FINAL / "00_service.png", F.FINAL / "08_hs_gap.png")
