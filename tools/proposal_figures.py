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


def draw_service(path) -> None:
    """세 열(입력 → 엔진 → 화면)과 두 갈래(고교·프로). 이용자는 갈래 아래 한 줄 — 본문 폭(16cm)에서도 글자가 읽히게 9인치 폭으로."""
    plots.use_style()
    fig, ax = plt.subplots(figsize=(9, 7.4))
    ax.set_xlim(-0.02, 1.02); ax.set_ylim(0.02, 1.03); ax.axis("off"); ax.grid(False)
    fs = 9.5
    for x, t in ((0.12, "입력"), (0.455, "엔진"), (0.82, "화면")):
        ax.text(x, 1.01, t, ha="center", va="center", fontsize=12, fontweight="bold", color=plots.INK_SECONDARY)
    ax.text(0.5, 0.925, "같은 원리 — 선수끼리가 아니라 ‘평소의 나’와 비교한다\n경보는 드물게 울리도록 설계한다",
            ha="center", va="center", fontsize=fs, color=plots.INK, linespacing=1.5,
            bbox=dict(boxstyle="round,pad=0.45", facecolor="#f4f3ee", edgecolor="#d8d6cc"))
    # 1부: 고교 (장비 없음)
    ax.text(0.01, 0.845, "고교 야구 — 투구 추적 장비 없음", fontsize=11.5, fontweight="bold", color=HS)
    F._box(ax, 0.01, 0.71, 0.22, 0.10, "협회 경기 기록\n날짜 · 투구 수 · 타석 결과", HS, fontsize=fs)
    F._box(ax, 0.01, 0.575, 0.22, 0.10, "손기록지 사진\n공마다 그린 볼·스트라이크", HS, fontsize=fs)
    F._box(ax, 0.285, 0.71, 0.34, 0.10, "규정 엔진 + 누적 부하\n7일 120·150구 · 3일 내 70·100구", HS, fontsize=fs)
    F._box(ax, 0.285, 0.575, 0.34, 0.10, "기록지 판독\n자동 판독 → AI 재판독 → 검산", HS, fontsize=fs)
    F._box(ax, 0.68, 0.575, 0.31, 0.235, "고교 투구수 현황판\n선수 시즌 카드\n(누적 부하 · 볼 비율 · 성적)\n투수 운용 계획판\n전국체전 달력", HS, fontsize=fs)
    for y in (0.76, 0.625):
        F._arrow(ax, 0.23, y, 0.285, y)
    F._arrow(ax, 0.625, 0.69, 0.68, 0.69)
    ax.text(0.01, 0.525, "이용자: 고교 선수 · 고교 지도자 · 프로 구단 아마추어 스카우트 · 대회 운영본부", fontsize=fs, color=plots.INK_SECONDARY, va="center")
    # 연결
    ax.annotate("", xy=(0.5, 0.425), xytext=(0.5, 0.49), arrowprops=dict(arrowstyle="-|>", color=plots.MUTED, lw=1.5))
    ax.text(0.52, 0.457, "같은 투수의 다음 단계 — 프로 구장에는 추적 장비가 있다", fontsize=fs - 0.5, color=plots.INK_SECONDARY, va="center")
    # 2부: 프로 (추적 장비)
    ax.text(0.01, 0.385, "프로 (MLB · KBO) — 투구 추적 장비", fontsize=11.5, fontweight="bold", color=PRO)
    F._box(ax, 0.01, 0.24, 0.22, 0.11, "투구 추적 데이터\n공마다 구속·릴리스·팔 각도", PRO, fontsize=fs)
    F._box(ax, 0.01, 0.105, 0.22, 0.095, "경기 기록\n(불펜 사용)", PRO, fontsize=fs)
    F._box(ax, 0.285, 0.24, 0.34, 0.11, "움직이는 ‘평소’ + 가변 표본 표준화\n구속 하락(주) · 폼 변화(보조)\n정상이면 100등판에 1회", PRO, fontsize=fs)
    F._box(ax, 0.285, 0.105, 0.34, 0.095, "부하 채널\n연투 · 최근 7일 75구", PRO, fontsize=fs)
    F._box(ax, 0.68, 0.105, 0.31, 0.245, "투수 시즌 상세 · 경보 카드\n팀 불펜 현황판\nKBO 외국인 투수\n영입 전 점검", PRO, fontsize=fs)
    F._arrow(ax, 0.23, 0.295, 0.285, 0.295); F._arrow(ax, 0.23, 0.155, 0.285, 0.155)
    F._arrow(ax, 0.625, 0.23, 0.68, 0.23)
    ax.text(0.01, 0.06, "이용자: 구단 분석 · 트레이닝 · 불펜 운영 · 해외 스카우트", fontsize=fs, color=plots.INK_SECONDARY, va="center")
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
