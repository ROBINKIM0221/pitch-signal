"""제안서·발표용 최종 그림 (단계 11.3). reports/figures/final/에 같은 스타일로 그린다.

입력은 모두 저장소에 있는 결과 파일(reports/tables/*.csv, dashboard-web/public/data/*.json)이라 data/ 없이도 다시 그릴 수 있다.
가상 데이터는 쓰지 않는다: 고교 그림(⑥)은 대시보드 자료가 가상(meta.json의 synthetic)인 동안 그리지 않는다.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

from src.common import plots
from src.common.config import ROOT

TABLES = ROOT / "reports" / "tables"
DASH = ROOT / "dashboard-web" / "public" / "data"
FINAL = ROOT / "reports" / "figures" / "final"
OK, WARN, ALARM, GRAY = "#2e8b57", "#d9822b", "#c8352e", "#9a9890"      # 상태 색: 초록·주황·빨강·회색 (대시보드와 같은 값)
VELO = plots.SERIES
METHOD_COLORS = {"구속 하락 신호": VELO, "폼 변화 신호": "#3f9b6c", "B2 WHIP CUSUM": "#8e6bbf", "B3 마할라노비스": "#c94f7c",
                 "B4 구속 EWMA(양방향)": "#5d9ec7", "B1 구속 1mph": WARN, "합의 규칙": GRAY}
CURVES = ["구속 하락 신호", "폼 변화 신호", "B2 WHIP CUSUM", "B3 마할라노비스", "B4 구속 EWMA(양방향)"]
POINTS = ["B1 구속 1mph", "합의 규칙"]            # 임계가 고정이거나(B1) 조정하지 않는(합의) 방식은 점 하나
ROLE = {"SP": "선발", "RP": "불펜"}
PART = {"elbow": "팔꿈치", "shoulder": "어깨"}
# 리플레이 파일: 대시보드 ① 화면에 올라간 검증셋 사례와 같은 자료 (src/13_export_dashboard.py가 뽑음)
CASES = {"detected": "647336_2025", "missed": "667755_2025"}
# 2026 KBO 외국인 투수 부상 이후 결정까지. 날짜 출처: 각 선수의 2026 시즌 경력 기록(나무위키), 2026-10-01 확인
KBO = [
    {"pitcher": "요니 치리노스", "team": "LG", "removed": "2026-04-22", "decided": "2026-06-02", "returned": None,
     "kind": "완전 교체", "note": "팔꿈치 통증 말소 → 방출, 이튿날 후임 계약"},
    {"pitcher": "미치 화이트", "team": "SSG", "removed": "2026-05-01", "decided": "2026-06-06", "returned": None,
     "kind": "완전 교체", "note": "어깨 회전근개 미세 손상 말소 → 후임 계약 발표"},
    {"pitcher": "오웬 화이트", "team": "한화", "removed": "2026-04-01", "decided": "2026-04-04", "returned": "2026-05-16",
     "kind": "6주 대체", "note": "수비 중 햄스트링 파열(투구와 무관) → 6주 대체 영입 → 복귀"},
    {"pitcher": "아리엘 후라도", "team": "삼성", "removed": "2026-07-14", "decided": "2026-07-20", "returned": "2026-09-06",
     "kind": "6주 대체", "note": "어깨 근막 손상 발표 → 6주 대체 영입 → 복귀"},
]


# ---------- 자료 준비 (그림과 분리해 두어 시험할 수 있게) ----------

def sim_rows(table: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """tools/sim_short_outings.py 결과표를 '등판 하나 오경보율(투구 수별)'과 '10등판 시나리오' 둘로 나눈다."""
    n = table["항목"].str.extract(r"등판 하나 오경보율 \((\d+)구\)")[0]
    per = table[n.notna()].assign(n=n.dropna().astype(int).to_numpy())[["n", "분산 하나", "가변 표본"]].reset_index(drop=True)
    scen = table[table["항목"].str.contains("10등판")].copy()
    scen["항목"] = scen["항목"].str.split(", 10등판").str[0]
    return {"per_outing": per, "scenarios": scen[["항목", "분산 하나", "가변 표본"]].reset_index(drop=True)}


def replay_story(d: dict) -> dict:
    """리플레이 JSON 하나를 그림용으로 편다: 감시 등판의 날짜·구속·예상·지수·경보, 관찰 창 표시, 선행 등판 수."""
    mon = [o for o in d["outings"] if o["phase"] == "monitor"]
    window = set(d["window"])
    in_window = np.array([o["game_pk"] in window for o in mon])
    alarm = np.array([bool(o["velo_alarm"]) for o in mon])
    dates = pd.to_datetime([o["date"] for o in mon])
    lead = None
    if (alarm & in_window).any():
        w = np.flatnonzero(in_window)
        first = w[np.flatnonzero(alarm[w])[0]]
        lead = int(len(w) - np.searchsorted(w, first))
    before = dates < dates[in_window].min()
    return {"name": d["name"], "role": d["role"], "part": d["part"], "season": d["season"], "il_date": pd.Timestamp(d["il_date"]),
            "baseline_end": pd.Timestamp(d["baseline_end"]), "detected": bool(d["detected"]),
            "baseline": pd.DataFrame([{"date": pd.Timestamp(o["date"]), "velo": o["velo"]} for o in d["outings"] if o["phase"] == "baseline"]),
            "dates": dates, "velo": np.array([o["velo"] for o in mon]), "exp": np.array([o["exp"]["velo"] for o in mon]),
            "sd": np.array([o["sd"]["velo"] for o in mon]), "index": np.array([o["velo_index"] for o in mon]),
            "alarm": alarm, "in_window": in_window, "lead": lead, "pre_window_alarms": int((alarm & before & ~in_window).sum())}


def kbo_timeline(rows: list[dict]) -> pd.DataFrame:
    """부상(말소·진단)일부터 결정일까지 며칠 걸렸는지."""
    out = pd.DataFrame(rows)
    for col in ("removed", "decided", "returned"):
        out[col] = pd.to_datetime(out[col]) if col in out else pd.NaT
    out["days"] = (out["decided"] - out["removed"]).dt.days
    return out


HS_TOURNAMENT = DASH / "highschool" / "tournament_2025.json"


def highschool_season_file(region: str = "경기") -> Path | None:
    """시즌(전국) 데이터셋에서 한 권역의 payload 파일. 목록(highschool.json)에서 찾는다."""
    index_path = DASH / "highschool.json"
    if not index_path.exists():
        return None
    for d in json.loads(index_path.read_text(encoding="utf-8")).get("datasets", []):
        for r in d.get("regions", []):
            if r["name"] == region:
                return DASH / r["file"]
    return None


def highschool_is_real() -> bool:
    meta = json.loads((DASH / "meta.json").read_text(encoding="utf-8"))
    season = highschool_season_file()
    return "highschool.json" not in meta.get("synthetic", []) and season is not None and season.exists() and HS_TOURNAMENT.exists()


# ---------- 그림 ----------

def _box(ax, x, y, w, h, text, color, fill="white", fontsize=9.5, weight=None):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.015,rounding_size=0.02", linewidth=1.6,
                                edgecolor=color, facecolor=fill))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fontsize, color=plots.INK, fontweight=weight, linespacing=1.4)


def _arrow(ax, x0, y0, x1, y1, color=plots.MUTED):
    ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle="-|>", mutation_scale=12, linewidth=1.2, color=color))


def draw_system(path: Path) -> None:
    """① 시스템 구성: 입력 → 감시 엔진 → 화면, 아래에 검증 절차."""
    plots.use_style()
    fig, ax = plt.subplots(figsize=(11, 6.2))
    ax.set_xlim(0, 1); ax.set_ylim(-0.2, 1.03); ax.axis("off"); ax.grid(False)
    # 열 제목
    for x, t in ((0.11, "입력"), (0.5, "감시 엔진"), (0.885, "화면과 사용")):
        ax.text(x, 0.985, t, ha="center", va="center", fontsize=11, fontweight="bold", color=plots.INK_SECONDARY)
    # 입력: 품질 채널은 트래킹 데이터, 부하 채널은 경기 기록만 있으면 된다
    _box(ax, 0.02, 0.66, 0.18, 0.2, "투구 추적 데이터\n구속 · 수직 릴리스 · 팔 각도\n(등판마다 투구 수가 다름)", VELO)
    _box(ax, 0.02, 0.03, 0.18, 0.2, "경기 기록\n날짜 · 투구 수 · 아웃\n(고교는 수기 입력)", OK)
    # 엔진: 품질 채널
    _box(ax, 0.27, 0.80, 0.46, 0.12, "움직이는 기준선 — 투수마다 '평소'를 등판마다 갱신", VELO, weight="bold")
    _box(ax, 0.27, 0.64, 0.46, 0.12, "가변 표본 표준화 — 투구 수가 적은 등판은 그만큼 덜 믿는다", VELO, weight="bold")
    _box(ax, 0.27, 0.44, 0.215, 0.15, "구속 하락 신호 (주)\n한 방향 EWMA, 지수 ≥ 1이면 경보", ALARM)
    _box(ax, 0.515, 0.44, 0.215, 0.15, "폼 변화 신호 (보조)\nT² + MEWMA, 원인 분해 카드", WARN)
    _box(ax, 0.27, 0.27, 0.46, 0.12, "오경보 설계 — 정상이면 100등판에 1회, 선발·불펜 따로 실측 보정", GRAY, weight="bold")
    # 엔진: 부하 채널
    _box(ax, 0.27, 0.03, 0.46, 0.15, "부하 채널 — 연투 · 3일 등판 · 7일 투구 수 · ACWR\n고교는 KBSA 투구수 규정 엔진(하루 105구 · 휴식일 · 3일 연속)", OK)
    # 출력
    _box(ax, 0.79, 0.52, 0.19, 0.2, "경보 카드 · 리플레이\n'무엇이 얼마나 달라졌나'\n점검 시작 신호", ALARM)
    _box(ax, 0.79, 0.03, 0.19, 0.2, "고교 투구수 현황판\n규정 준수 + 누적 부하\n(가명 코드)", OK)
    # 화살표
    _arrow(ax, 0.2, 0.76, 0.27, 0.86); _arrow(ax, 0.2, 0.105, 0.27, 0.105)
    _arrow(ax, 0.5, 0.80, 0.5, 0.765); _arrow(ax, 0.5, 0.64, 0.5, 0.595); _arrow(ax, 0.5, 0.44, 0.5, 0.395)
    _arrow(ax, 0.73, 0.515, 0.79, 0.62); _arrow(ax, 0.73, 0.105, 0.79, 0.13)
    # 검증 절차 띠
    ax.text(0.5, -0.12, "검증 절차:  개발셋 2021~2023 (한계 조정)  →  평가 계획 고정 · GitHub Release  →  검증셋 2024~2025 (한 번)  →  봉인 2026 (한 번)",
            ha="center", va="center", fontsize=9.5, color=plots.INK_SECONDARY,
            bbox={"boxstyle": "round,pad=0.5", "facecolor": "#f4f3ee", "edgecolor": plots.GRID})
    fig.savefig(path, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)


def _bars(ax, labels, a, b, name_a, name_b, fmt):
    x = np.arange(len(labels)); w = 0.36
    ax.bar(x - w / 2, a, w, color=GRAY, label=name_a)
    ax.bar(x + w / 2, b, w, color=VELO, label=name_b)
    for xs, vals in ((x - w / 2, a), (x + w / 2, b)):
        for xi, v in zip(xs, vals):
            ax.text(xi, v, fmt(v), ha="center", va="bottom", fontsize=8.5, color=plots.INK_SECONDARY)
    ax.set_xticks(x, labels)


def draw_short_outings(sim: dict[str, pd.DataFrame], path: Path) -> None:
    """② 짧은 등판 처리 비교: 두 방식 모두 ARL0 = 100으로 맞춘 뒤 투구 수별 오경보율과 10등판 시나리오."""
    plots.use_style()
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), gridspec_kw={"width_ratios": [1.15, 1]})
    per, scen = sim["per_outing"], sim["scenarios"]
    _bars(axes[0], [f"{n}구" for n in per["n"]], 100 * per["분산 하나"], 100 * per["가변 표본"],
          "분산 하나로 모든 등판을 같게", "가변 표본 표준화 (채택)", lambda v: f"{v:.2f}")
    axes[0].axhline(1.0, color=ALARM, linewidth=1, linestyle="--", label="목표 1% (두 방식 모두 ARL0 = 100)")
    axes[0].set_title("등판 하나의 오경보율 (%) — 패스트볼 투구 수별")
    axes[0].set_xlabel("등판 안 패스트볼 투구 수")
    axes[0].legend(frameon=False, fontsize=8.5, loc="upper right")
    _bars(axes[1], scen["항목"], 100 * scen["분산 하나"], 100 * scen["가변 표본"], "분산 하나", "가변 표본", lambda v: f"{v:.1f}")
    axes[1].set_title("10등판 안에 경보가 울린 비율 (%)")
    axes[1].set_xlabel("시나리오 (앞 둘은 오경보, 셋째는 탐지)")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def draw_opcurve(points: pd.DataFrame, results: pd.DataFrame, design_far: float, path: Path) -> None:
    """③ 검증셋 운영 곡선: 오경보를 얼마나 허용하느냐에 따른 탐지율. 선은 한계에 배수를 곱한 것, 점은 조정하지 않는 방식."""
    plots.use_style()
    fig, ax = plt.subplots(figsize=(8.2, 5.2))
    for name in CURVES:
        part = points[points["method"] == name].sort_values("false_alarms_per100")
        ax.plot(part["false_alarms_per100"], part["detection"], marker="o", markersize=4, color=METHOD_COLORS[name], label=name,
                linewidth=3 if name == "구속 하락 신호" else 1.5, zorder=3 if name == "구속 하락 신호" else 2)
    for name in POINTS:
        row = results[(results["method"] == name) & (results["group"] == "all")].iloc[0]
        ax.scatter(row["false_alarms_per100"], row["detection"], marker="D", s=46, color=METHOD_COLORS[name], label=f"{name} (점)", zorder=4)
    b1 = results[(results["method"] == "B1 구속 1mph") & (results["group"] == "all")].iloc[0]
    ax.text(b1["false_alarms_per100"], b1["detection"] - 2.2, f"고정 -1mph 규칙: 오경보 {b1['false_alarms_per100']:.1f}/100", ha="center", va="top",
            fontsize=8.5, color=METHOD_COLORS["B1 구속 1mph"])
    ax.axvline(design_far, color=plots.MUTED, linewidth=0.9, linestyle="--")
    velo = results[(results["method"] == "구속 하락 신호") & (results["group"] == "all")].iloc[0]
    ax.annotate(f"설계점: 오경보 {velo['false_alarms_per100']:.2f}/100에서 탐지 {velo['detection']:.1f}%\n(대조군 창 안 경보 {velo['control_window']:.1f}%)",
                xy=(velo["false_alarms_per100"], velo["detection"]), xytext=(2.2, 44), fontsize=9, color=plots.INK,
                arrowprops={"arrowstyle": "-", "color": plots.MUTED, "linewidth": 0.8})
    ax.set_xlim(0, 8); ax.set_ylim(0, 65)
    ax.set_xlabel("대조군 100등판당 오경보 수 (점선: 설계점 1회)")
    ax.set_ylabel("탐지율 (%) — 관찰 창 안에 경보가 있는 사례 비율")
    ax.set_title("운영 곡선 (검증셋 2024~2025, 사례 107 · 대조군 214)")
    ax.legend(frameon=False, fontsize=8.5, loc="upper right")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def draw_case(s: dict, path: Path) -> None:
    """④⑤ 리플레이: 위는 구속과 예상 범위, 아래는 구속 하락 지수. 관찰 창·IL 등재일·경보를 표시한다."""
    plots.use_style()
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9.5, 5.8), sharex=True, gridspec_kw={"height_ratios": [1.25, 1], "hspace": 0.08})
    base = s["baseline"]
    for ax in (ax1, ax2):
        ax.axvspan(base["date"].min(), s["baseline_end"], color="#f1f0ea", zorder=0)
        ax.axvspan(s["dates"][s["in_window"]].min(), s["dates"][s["in_window"]].max(), color="#fdebd3", alpha=0.7, zorder=0)
        ax.axvline(s["il_date"], color=ALARM, linewidth=1.2, linestyle="--")
    ax1.plot(base["date"], base["velo"], marker="o", markersize=4, color=GRAY, linewidth=1.5, label="시작 구간 (기준선 학습)")
    ax1.fill_between(s["dates"], s["exp"] - 2 * s["sd"], s["exp"] + 2 * s["sd"], color=VELO, alpha=0.12, linewidth=0, label="예상 범위 (±2σ)")
    ax1.plot(s["dates"], s["exp"], color=VELO, linewidth=1.2, linestyle=":", label="예상 구속 (평소)")
    ax1.plot(s["dates"], s["velo"], marker="o", markersize=4.5, color=plots.INK, linewidth=1.5, label="등판 평균 구속")
    ax1.scatter(s["dates"][s["alarm"]], s["velo"][s["alarm"]], s=90, facecolor="none", edgecolor=ALARM, linewidth=1.8, zorder=5, label="구속 하락 경보")
    ax1.set_ylabel("패스트볼 구속 (mph)")
    near_right = s["il_date"] > s["dates"].max() - 0.15 * (s["dates"].max() - base["date"].min())
    ax1.text(s["il_date"], ax1.get_ylim()[1], f" IL 등재 {s['il_date']:%m/%d} ", color=ALARM, fontsize=9, va="top", ha="right" if near_right else "left")
    ax1.text(s["baseline_end"], ax1.get_ylim()[1], " 감시 시작 ", color=plots.INK_SECONDARY, fontsize=8.5, va="top", ha="right")
    ax1.legend(frameon=False, fontsize=8, loc="lower left", ncol=3)
    ax2.axhline(1.0, color=ALARM, linewidth=1, linestyle="--")
    ax2.axhline(0, color=plots.AXIS, linewidth=0.8)
    ax2.plot(s["dates"], s["index"], marker="o", markersize=4, color=VELO, linewidth=1.5)
    ax2.scatter(s["dates"][s["alarm"]], s["index"][s["alarm"]], s=60, color=ALARM, zorder=5)
    ax2.set_ylabel("구속 하락 지수 (1 이상 = 경보)")
    ax2.set_ylim(min(-1.6, s["index"].min() - 0.2), max(1.6, s["index"].max() + 0.25))
    w = s["dates"][s["in_window"]]
    ax2.text(w.min(), ax2.get_ylim()[0], " 관찰 창 (IL 전 5등판)", fontsize=8.5, color=WARN, va="bottom")
    if s["lead"]:
        note = f"창 안 첫 경보 → IL 등재까지 {s['lead']}등판"
    else:
        note = "관찰 창 안 경보 없음 (놓침)"
    ax2.text(0.01, 0.06, note, transform=ax2.transAxes, ha="left", va="bottom", fontsize=9, color=plots.INK,
             bbox={"boxstyle": "round,pad=0.35", "facecolor": "white", "edgecolor": plots.GRID})
    kind = "탐지 사례" if s["detected"] else "놓친 사례"
    ax1.set_title(f"{kind}: {s['name']} — {ROLE[s['role']]} · {PART[s['part']]} · {s['season']}  (회색 띠 = 시작 구간, 주황 띠 = 관찰 창)")
    fig.autofmt_xdate(rotation=0, ha="center")
    fig.savefig(path)
    plt.close(fig)


def _rest_days(pitches, rest_table) -> int:
    for upper, rest in rest_table:
        if pitches <= upper:
            return rest
    return rest_table[-1][1]


HEAT = [(30, "#eaf2fc", plots.INK), (60, "#9dc1ec", plots.INK), (90, "#4f8fdc", "white"), (10 ** 6, "#1d4f8f", "white")]


def draw_highschool_season(payload: dict, path: Path) -> None:
    """⑥ 경기도 23팀 투수 208명의 2025 시즌 투구 수: 팀마다 점 하나가 투수 한 명(크기는 등판 수). 빨간 테두리는 KBSA 규정 위반이 있던 투수.
    팀은 팀 투구 수가 많은 순, 점선은 500구."""
    plots.use_style()
    schools = sorted(payload["schools"], key=lambda s: -(s["pitches_total"] or 0))
    fig, ax = plt.subplots(figsize=(11, 4.8))
    rng = np.random.default_rng(0)
    for i, s in enumerate(schools):
        for p in s["pitchers"]:
            if p["pitches_total"] is None:
                continue
            x = i + rng.uniform(-0.18, 0.18)
            ax.scatter(x, p["pitches_total"], s=14 + 5 * p["outings"], color=VELO, alpha=0.55, edgecolor="none", zorder=3)
            if p["rule_status"] == "위반":
                ax.scatter(x, p["pitches_total"], s=40 + 5 * p["outings"], facecolor="none", edgecolor=ALARM, linewidth=1.6, zorder=4)
        top = max((p for p in s["pitchers"] if p["pitches_total"] is not None), key=lambda p: p["pitches_total"], default=None)
        if top and top["pitches_total"] >= 850:
            ax.text(i, top["pitches_total"] + (25 if i % 2 == 0 else 60), f"{top['label']} {top['pitches_total']:,}구 · {top['outings']}등판", ha="center", va="bottom", fontsize=7.5, color=plots.INK_SECONDARY)
    ax.axhline(500, color=ALARM, linewidth=1, linestyle="--")
    ax.text(len(schools) - 0.5, 505, "시즌 500구", ha="right", va="bottom", fontsize=8.5, color=ALARM)
    ax.set_xticks(range(len(schools)), [s["name"] for s in schools], rotation=45, ha="right", fontsize=8.5)
    ax.set_xlim(-0.7, len(schools) - 0.3)
    ax.set_ylabel("시즌 투구 수 (공식 경기)")
    k = payload["totals"]
    ax.set_title(f"2025 {payload['dataset'].get('region') or ''} 고교 {k['schools']}팀 투수 {k['pitchers']}명의 시즌 투구 수 — 점 하나가 투수 한 명(크기는 등판 수), 빨간 테두리는 규정 위반 투수. "
                 f"규정 위반 {k['violations']}건, 시즌 500구 이상 {k['pitchers_season_500']}명", fontsize=10, loc="left")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def draw_highschool(payload: dict, path: Path) -> None:
    """⑥b 전국체전 결승 진출 두 학교의 대회 등판 달력(학교 실명, 투수는 등번호). 칸의 숫자는 그날 투구 수(짙을수록 많음), 빗금은 직전 투구 수가 요구하는 의무 휴식일, ?는 투구 수 미공개."""
    plots.use_style()
    rest_table = [tuple(r) for r in payload["kbsa"]["rest_table"]]
    days = pd.date_range(min(g["date"] for g in payload["games"]), max(g["date"] for g in payload["games"])).strftime("%Y-%m-%d").tolist()
    schools = sorted(payload["schools"], key=lambda x: (-x["games"], x["name"]))[:2]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), gridspec_kw={"wspace": 0.28, "top": 0.8})
    for ax, school in zip(axes, schools):
        pitchers = sorted(school["pitchers"], key=lambda x: -(x["pitches_total"] if x["pitches_total"] is not None else -1))
        rounds = {g["date"]: g["round"] for g in payload["games"] if school["name"] in g["teams"]}     # 그 학교가 그날 치른 경기의 라운드
        ax.set_xlim(0, len(days)); ax.set_ylim(len(pitchers), -0.9); ax.axis("off"); ax.grid(False)
        for j, d in enumerate(days):
            ax.text(j + 0.5, -0.55, d[5:].replace("-", "/"), ha="center", va="center", fontsize=8.5, color=plots.INK_SECONDARY)
            ax.text(j + 0.5, -0.15, rounds.get(d, ""), ha="center", va="center", fontsize=7.5, color=plots.MUTED)
        for i, p in enumerate(pitchers):
            ax.text(-0.15, i + 0.5, p["label"], ha="right", va="center", fontsize=9, color=plots.INK)
            by_date = {g["date"]: g for g in p["games"]}
            rest = set()
            for g in p["games"]:
                if g["pitches"] is not None:
                    for k in range(1, _rest_days(g["pitches"], rest_table) + 1):
                        rest.add((pd.Timestamp(g["date"]) + pd.Timedelta(days=k)).strftime("%Y-%m-%d"))
            for j, d in enumerate(days):
                g = by_date.get(d)
                if g is not None and g["pitches"] is None:
                    ax.add_patch(plt.Rectangle((j + 0.06, i + 0.08), 0.88, 0.84, facecolor="#f1f0ea", edgecolor=GRAY, linestyle="--", linewidth=0.9))
                    ax.text(j + 0.5, i + 0.5, "?", ha="center", va="center", fontsize=9.5, color=plots.INK_SECONDARY)
                elif g is not None:
                    fill, ink = next((c, t) for upper, c, t in HEAT if g["pitches"] <= upper)
                    ax.add_patch(plt.Rectangle((j + 0.06, i + 0.08), 0.88, 0.84, facecolor=fill, edgecolor="none"))
                    ax.text(j + 0.5, i + 0.5, f"{g['pitches']:.0f}", ha="center", va="center", fontsize=9.5, color=ink, fontweight="bold")
                elif d in rest:
                    ax.add_patch(plt.Rectangle((j + 0.06, i + 0.08), 0.88, 0.84, facecolor="#f3f2ec", edgecolor="#d6d5ce", hatch="///", linewidth=0.6))
                else:
                    ax.add_patch(plt.Rectangle((j + 0.06, i + 0.08), 0.88, 0.84, facecolor="#f7f7f4", edgecolor="none"))
        total = sum(p["pitches_total"] or 0 for p in school["pitchers"])
        ax.set_title(f"{school['name']} — {school['games']}경기, 투수 {len(pitchers)}명, 팀 합계 {total:.0f}구", fontsize=10.5, loc="left", pad=10)
    t = payload["dataset"]
    fig.suptitle(f"{t['short']} 18세 이하부 결승 진출 두 학교의 등판 달력 — 칸 숫자는 그날 투구 수(짙을수록 많음), 빗금은 의무 휴식일, ?는 투구 수 미공개 (투수는 등번호)",
                 fontsize=10.5, x=0.02, y=0.97, ha="left")
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def draw_kbo(timeline: pd.DataFrame, path: Path) -> None:
    """⑦ 2026 KBO 외국인 투수: 부상(말소·진단)부터 결정까지, 6주 대체는 복귀일까지 옅게."""
    plots.use_style()
    fig, ax = plt.subplots(figsize=(9.5, 3.4))
    ax.grid(axis="x"); ax.grid(False, axis="y")
    for i, r in timeline.iloc[::-1].reset_index().iterrows():
        color = ALARM if r["kind"] == "완전 교체" else WARN
        if pd.notna(r["returned"]):
            ax.barh(i, (r["returned"] - r["decided"]).days, left=r["decided"], height=0.5, color=color, alpha=0.25)
            ax.text(r["returned"], i, f" 복귀 {r['returned']:%m/%d}", va="center", fontsize=8.5, color=plots.INK_SECONDARY)
        ax.barh(i, max(r["days"], 1), left=r["removed"], height=0.5, color=color)
        ax.text(r["removed"], i + 0.3, f"{r['kind']} 결정까지 {r['days']}일 ({r['removed']:%m/%d} → {r['decided']:%m/%d})",
                va="bottom", ha="left", fontsize=8.5, color=plots.INK)
    ax.set_yticks(range(len(timeline)), [f"{r['pitcher']} ({r['team']})" for _, r in timeline.iloc[::-1].iterrows()])
    ax.set_ylim(-0.5, len(timeline) - 0.2)
    ax.set_xlim(pd.Timestamp("2026-03-20"), pd.Timestamp("2026-09-20"))
    ax.set_title("2026 KBO 외국인 투수 부상 이후 결정까지 걸린 기간 — 완전 교체는 한 달 넘게, 6주 대체는 며칠 만에")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


# ---------- 전체 ----------

def highschool_season_caption(payload: dict) -> str:
    t, k = payload["dataset"], payload["totals"]
    worst = sorted((p for s in payload["schools"] for p in s["pitchers"] if p["pitches_total"] is not None), key=lambda p: -p["pitches_total"])[:3]
    return (f"그림 6. {t['name']} 중 {t['region']} 권역 {k['schools']}팀({t['dates']}, {k['games']}경기)의 투수 {k['pitchers']}명이 던진 시즌 투구 수. 점 하나가 투수 한 명이고 크기는 등판 수, "
            f"팀은 팀 투구 수가 많은 순이다. 투수는 등번호로만 표시했다. 등판 {k['outings']}회에서 KBSA 규정 위반은 {k['violations']}건(하루 105구 초과 1, 의무 휴식일 미준수 1)뿐이지만 "
            f"시즌 500구 이상이 {k['pitchers_season_500']}명, 7일 합 150구 이상을 경험한 투수가 {k['pitchers_7d_150']}명, 100구 이상 등판이 {k['games_100plus']}회였고 "
            f"가장 많이 던진 세 투수는 {', '.join(f'{p['pitches_total']:,}구({p['outings']}등판)' for p in worst)}였다. 연투 {k['back_to_back']}건은 모두 45구 이하 뒤라 규정상 허용이다. "
            f"누적 부하 신호등(7일 합 120/150구, 3일 안 두 등판 합 70/100구)은 높음 {k['pitchers_load_high']}명·주의 {k['pitchers_load_caution']}명이고, "
            f"규정 위반 없이 높음·주의가 켜진 투수가 {k['compliant_with_load']}명이다.")


def highschool_caption(payload: dict) -> str:
    t, k = payload["dataset"], payload["totals"]
    finalists = sorted(payload["schools"], key=lambda x: (-x["games"], x["name"]))[:2]
    return (f"그림 6b. {t['short']} 18세 이하부({t['dates']}, 15개교 {t['games']}경기) 결승 진출 두 학교({', '.join(s['name'] for s in finalists)})의 등판 달력. "
            f"투수는 등번호로만 표시했고 숫자는 KBSA 기록실 경기 기록의 투구 수다. 대회 전체 투수 {k['pitchers']}명·등판 {k['outings']}회에서 규정 위반은 {k['violations']}건이었지만, "
            f"연투 {k['back_to_back']}건, 의무 휴식일을 꼭 채운 뒤 첫날 등판 {k['min_rest_exact']}건, 91구 이상 등판 {k['games_91plus']}회가 있었고 한 투수가 7일 동안 최대 {k['max_total']:.0f}구를 던졌다. "
            f"규정은 지켰어도 부하가 몇 명에게 몰리는 모습을 현황판이 보여 준다. 상세 기록이 공개되지 않은 {len(t['no_detail_games'])}경기는 '?'로 표시했다.")


def captions(results: pd.DataFrame, tests: pd.DataFrame, sim: dict, stories: dict, timeline: pd.DataFrame, names: list[str], hs_caption: str = "", hs_season_caption: str = "") -> str:
    velo = results[(results["method"] == "구속 하락 신호") & (results["group"] == "all")].iloc[0]
    b1 = results[(results["method"] == "B1 구속 1mph") & (results["group"] == "all")].iloc[0]
    h1 = tests[tests["test"].str.startswith("H1")].iloc[0]
    per = sim["per_outing"]; scen = sim["scenarios"].set_index("항목")
    det, mis = stories["detected"], stories["missed"]
    items = {
        "01_system.png": ("그림 1. 피치시그널 시스템 구성. 투구 추적 데이터가 있는 팀에는 품질 채널(구속 하락 신호·폼 변화 신호)을, 경기 기록만 있는 고교·대회에는 "
                          "부하 채널과 규정 엔진을 제공한다. 오경보율은 정상 상태에서 100등판에 1회로 설계하고 선발·불펜 따로 실측 보정한다.",
                          "docs/SPEC.md 3.7~3.11절"),
        "02_short_outings.png": (f"그림 2. 짧은 등판 처리 방식 비교. 두 방식 모두 정상 상태 100등판에 1회 경보(ARL0 = 100)로 맞춘 뒤, 분산 하나로 모든 등판을 같게 처리하면 "
                                 f"{per['n'].min()}구 등판의 오경보율이 {100 * per.loc[per['n'].idxmin(), '분산 하나']:.2f}%로 목표(1%)의 두 배가 되고, 투구는 그대로인데 기용만 짧아져도 "
                                 f"10등판 안 경보가 {100 * scen.loc['기용만 짧아짐', '분산 하나']:.1f}%로 늘어난다(평소 {100 * scen.loc['평소 그대로', '분산 하나']:.1f}%). "
                                 f"가변 표본 표준화는 투구 수와 무관하게 1%를 지키고 기용만 짧아진 시나리오에서도 평소 수준({100 * scen.loc['기용만 짧아짐', '가변 표본']:.1f}%)에 머물며, 실제 변화의 탐지율은 같다"
                                 f"({100 * scen.loc['구속 0.5 하락', '분산 하나']:.1f}% vs {100 * scen.loc['구속 0.5 하락', '가변 표본']:.1f}%).",
                                 "reports/tables/sim_short_outings.csv (tools/sim_short_outings.py, 개발셋 실제 σ_w·σ_b 사용, 2만 회 반복)"),
        "03_opcurve_val.png": (f"그림 3. 검증셋(2024~2025) 운영 곡선. 같은 사례·대조군·관찰 창에서 오경보 허용량을 바꿔 가며 탐지율을 그렸다. 설계점(100등판당 1회)에서 "
                               f"구속 하락 신호는 실측 오경보 {velo['false_alarms_per100']:.2f}/100, 탐지율 {velo['detection']:.1f}%(대조군 창 안 경보 {velo['control_window']:.1f}%), "
                               f"창 지수 일치도 {h1['value']:.3f}(95% 구간 {h1['ci_lo']:.3f}~{h1['ci_hi']:.3f}). 흔히 쓰는 고정 규칙 B1(−1mph)은 탐지율 {b1['detection']:.1f}%지만 "
                               f"오경보가 {b1['false_alarms_per100']:.1f}/100이다.",
                               "reports/tables/val_opcurve.csv, val_results.csv, val_tests.csv"),
        "04_case_detected.png": (f"그림 4. 탐지 사례 — {det['name']}({ROLE[det['role']]}, {PART[det['part']]}, {det['season']}). 시작 구간에서 학습한 평소 구속에서 "
                                 f"예상보다 낮은 등판이 이어지자 구속 하락 지수가 1을 넘어 경보가 울렸고, 관찰 창 안 첫 경보부터 IL 등재까지 {det['lead']}등판이었다"
                                 + (f"(창 밖 경보 {det['pre_window_alarms']}회 포함하면 더 이르다)." if det["pre_window_alarms"] else "."),
                                 f"dashboard-web/public/data/replay/{CASES["detected"]}.json (data/processed/monitor_val.parquet에서 내보냄)"),
        "05_case_missed.png": (f"그림 5. 놓친 사례 — {mis['name']}({ROLE[mis['role']]}, {PART[mis['part']]}, {mis['season']}). 관찰 창 다섯 등판의 구속이 평소 범위 안에 머물러 "
                               f"구속 하락 지수가 1에 이르지 못했다(창 안 최댓값 {mis['index'][mis['in_window']].max():.2f}). 구속이 떨어지지 않는 부상은 이 신호로 잡히지 않는다.",
                               f"dashboard-web/public/data/replay/{CASES["missed"]}.json"),
        "06_highschool.png": (hs_season_caption, "dashboard-web/public/data/highschool/korea_2025/ 경기 권역 파일 (src/17_kbsa_records.py가 KBSA 기록실 2025 고교 경기 기록 976경기를 변환, 2026-10-07 1회 수집)"),
        "06b_tournament.png": (hs_caption, "dashboard-web/public/data/highschool/tournament_2025.json (src/17_kbsa_records.py가 KBSA 기록실 경기 기록 14경기를 변환, 2026-10-07 1회 수집)"),
        "07_kbo_timeline.png": (f"그림 7. 2026 KBO 외국인 투수 부상 이후 결정까지. 완전 교체 두 건은 {timeline[timeline['kind'] == '완전 교체']['days'].min()}~"
                                f"{timeline[timeline['kind'] == '완전 교체']['days'].max()}일, 6주 대체 두 건은 {timeline[timeline['kind'] == '6주 대체']['days'].min()}~"
                                f"{timeline[timeline['kind'] == '6주 대체']['days'].max()}일 만에 결정되었다. 오웬 화이트는 수비 중 하체 부상이라 투구 신호 감시 대상이 아니지만 "
                                f"결정 속도의 대비를 보여 준다.",
                                "각 선수의 2026 시즌 경력 기록(나무위키, 2026-10-01 확인) — 날짜만 사용"),
    }
    lines = ["# 최종 그림 캡션과 출처", "", "가상 데이터는 쓰지 않는다. ⑥ 고교 그림은 highschool.json이 실제 기록일 때만 그린다.", ""]
    for name in names:
        cap, src = items.get(name, (f"그림. {name}", ""))
        lines += [f"## {name}", "", cap, "", f"출처: {src}", ""]
    return "\n".join(lines)


def draw_all(out: Path | str = FINAL) -> list[str]:
    """최종 그림을 모두 그리고 captions.md를 쓴다. 돌려주는 값은 만든 그림 파일 이름."""
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    results = pd.read_csv(TABLES / "val_results.csv")
    tests = pd.read_csv(TABLES / "val_tests.csv")
    points = pd.read_csv(TABLES / "val_opcurve.csv")
    sim = sim_rows(pd.read_csv(TABLES / "sim_short_outings.csv"))
    stories = {k: replay_story(json.loads((DASH / f"replay/{v}.json").read_text(encoding="utf-8"))) for k, v in CASES.items()}
    timeline = kbo_timeline(KBO)
    names, hs_caption, hs_season_caption = [], "", ""
    draw_system(out / "01_system.png"); names.append("01_system.png")
    draw_short_outings(sim, out / "02_short_outings.png"); names.append("02_short_outings.png")
    draw_opcurve(points, results, 1.0, out / "03_opcurve_val.png"); names.append("03_opcurve_val.png")
    draw_case(stories["detected"], out / "04_case_detected.png"); names.append("04_case_detected.png")
    draw_case(stories["missed"], out / "05_case_missed.png"); names.append("05_case_missed.png")
    if highschool_is_real():
        season = json.loads(highschool_season_file().read_text(encoding="utf-8"))
        draw_highschool_season(season, out / "06_highschool.png"); names.append("06_highschool.png"); hs_season_caption = highschool_season_caption(season)
        payload = json.loads(HS_TOURNAMENT.read_text(encoding="utf-8"))
        draw_highschool(payload, out / "06b_tournament.png"); names.append("06b_tournament.png"); hs_caption = highschool_caption(payload)
    draw_kbo(timeline, out / "07_kbo_timeline.png"); names.append("07_kbo_timeline.png")
    (out / "captions.md").write_text(captions(results, tests, sim, stories, timeline, names, hs_caption, hs_season_caption), encoding="utf-8")
    return names
