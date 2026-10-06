import { useState } from "react";
import { CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis, Legend } from "recharts";
import { fmt, useJson } from "../lib/data.js";
import { GRID, LABEL, LEGEND_STYLE, TICK, TIP_STYLE } from "../lib/chart.jsx";

const COLORS = { "구속 하락 신호": "#2a78d6", "폼 변화 신호": "#3f9b6c", "B2 WHIP CUSUM": "#8e6bbf", "B3 마할라노비스": "#c94f7c",
  "B4 구속 EWMA(양방향)": "#5d9ec7", "B1 구속 1mph": "#d9822b", "합의 규칙": "#8a8880" };
const LINES = ["구속 하락 신호", "폼 변화 신호", "B2 WHIP CUSUM", "B3 마할라노비스", "B4 구속 EWMA(양방향)"];
const POINTS = ["B1 구속 1mph", "합의 규칙"];
const GROUP = { all: "전체", SP: "선발", RP: "불펜" };

export default function Performance() {
  const { data } = useJson("performance.json");
  const [group, setGroup] = useState("all");
  const [tab, setTab] = useState("val");
  if (!data) return <div className="placeholder">성능 비교 자료를 읽는 중…</div>;
  const hasSealed = !!data.sealed;
  const set = tab === "sealed" && hasSealed ? data.sealed : data;
  const seasonsText = (tab === "sealed" && hasSealed ? data.sealed.seasons : data.seasons).join("~");
  const rows = set.results.filter((r) => r.group === group);
  const h1 = set.tests.find((t) => t.test.startsWith("H1"));
  const h2 = set.tests.find((t) => t.test.startsWith("H2"));
  const h3 = set.tests.find((t) => t.test.startsWith("H3"));
  const velo = set.results.find((r) => r.method === "구속 하락 신호" && r.group === "all");
  const followup = (data.followup || []).filter((f) => f.role === "all" && f.method === "구속 하락 신호");
  return (
    <div className="page">
      <h1>성능 비교</h1>
      <p className="lead">
        평가 계획을 고정한 뒤 한 번씩 계산한 결과입니다. 모든 방법은 같은 사례·대조군·관찰 창을 쓰고, 임계값은 개발셋(2021~2023)에서만 맞췄습니다.
        {hasSealed && " 2026 시즌은 봉인해 두었다가 10월 7일 한 번 평가했습니다 — 결과는 좋든 나쁘든 그대로 보고합니다."}
      </p>
      {hasSealed && (
        <div className="toolbar">
          <div className="seg" role="tablist">
            <button className={`btn ${tab === "val" ? "on" : ""}`} onClick={() => setTab("val")}>검증셋 {data.seasons.join("~")}</button>
            <button className={`btn ${tab === "sealed" ? "on" : ""}`} onClick={() => setTab("sealed")}>봉인 {data.sealed.seasons.join("~")} (1회 평가)</button>
          </div>
          <span className="caption" style={{ margin: 0 }}>{tab === "sealed" ? "사례 54건으로 검증셋(107건)보다 적어 구간이 넓습니다." : "주 결과. 아래 표·곡선이 제안서 4장의 숫자입니다."}</span>
        </div>
      )}
      <div className="card">
        <h2>미리 정한 가설 <span style={{ color: "var(--muted)", fontWeight: 500 }}>· {seasonsText}</span></h2>
        <div className="kpi">
          <div><div className="v">{fmt.num(h1?.value, 3)}</div><div className="l">H1 구속 하락 지수 일치도 · 95% 구간 {fmt.num(h1?.ci_lo, 3)}~{fmt.num(h1?.ci_hi, 3)} → <b>{h1?.supported ? "지지" : "지지 안 됨"}</b></div></div>
          <div><div className="v">{fmt.num(h2?.value, 1)}등판</div><div className="l">H2 첫 경보의 선행 등판 수 중앙값 (기준 2 이상) → <b>{h2?.supported ? "지지" : "지지 안 됨"}</b></div></div>
          {h3 && <div><div className="v">{fmt.num(h3.value, 2)} /100</div><div className="l">H3 실측 오경보 (두 신호 중 큰 값, 허용 2.0) → <b>{h3.supported ? "지지" : "지지 안 됨"}</b></div></div>}
          <div><div className="v">{velo?.cases} / {velo?.controls}</div><div className="l">사례 / 대조군</div></div>
        </div>
        <p className="caption">일치도는 사례의 창 지수가 짝지은 대조군보다 클 확률입니다. 0.5면 정보가 없고 1이면 사례가 늘 큽니다.</p>
      </div>
      <div className="card">
        <h2>운영 곡선 · 오경보를 얼마나 허용하느냐에 따른 탐지율 <span style={{ color: "var(--muted)", fontWeight: 500 }}>· {seasonsText}</span></h2>
        <ResponsiveContainer width="100%" height={360}>
          <ComposedChart margin={{ top: 10, right: 24, left: 4, bottom: 28 }}>
            <CartesianGrid stroke={GRID} />
            <XAxis dataKey="false_alarms_per100" type="number" name="오경보" domain={[0, "auto"]} tick={TICK} axisLine={{ stroke: GRID }} tickLine={false}
              label={{ value: "대조군 100등판당 오경보 수", position: "bottom", offset: 10, ...LABEL }} />
            <YAxis dataKey="detection" type="number" tick={TICK} width={46} axisLine={false} tickLine={false}
              label={{ value: "탐지율 (%)", angle: -90, position: "insideLeft", offset: 14, ...LABEL }} />
            <Tooltip {...TIP_STYLE} formatter={(v, n) => [fmt.num(v, 1), n]} labelFormatter={(v) => `오경보 ${fmt.num(v, 2)}/100`} />
            <Legend verticalAlign="top" wrapperStyle={LEGEND_STYLE} iconType="plainline" />
            <ReferenceLine x={data.design_far} stroke="var(--muted)" strokeDasharray="4 4" label={{ value: "설계점 1회", position: "insideTopLeft", ...LABEL, fill: "var(--muted)" }} />
            {LINES.map((name) => (
              <Line key={name} data={set.opcurve.filter((p) => p.method === name).sort((a, b) => a.false_alarms_per100 - b.false_alarms_per100)}
                dataKey="detection" name={name} stroke={COLORS[name]} strokeWidth={name === "구속 하락 신호" ? 3 : 1.5} dot={{ r: 3, strokeWidth: 1.5, fill: "#fff" }} isAnimationActive={false} />
            ))}
            {POINTS.map((name) => (
              <Scatter key={name} data={set.opcurve.filter((p) => p.method === name && p.scale === 1)} dataKey="detection" name={name} fill={COLORS[name]} shape="diamond" legendType="diamond" isAnimationActive={false} />
            ))}
          </ComposedChart>
        </ResponsiveContainer>
        <p className="caption">선은 한계에 배수를 곱해 가며 그린 것이고, B1(고정 임계)과 합의 규칙은 점입니다. 설계점(100등판당 1회)에서의 값이 아래 표입니다.</p>
      </div>
      <div className="card">
        <div className="card-head">
          <h2>결과표 · 100등판당 오경보 1회 기준 <span style={{ color: "var(--muted)", fontWeight: 500 }}>· {seasonsText}</span></h2>
          <div className="seg" role="group" aria-label="역할">
            {Object.entries(GROUP).map(([k, v]) => <button key={k} className={`btn ${group === k ? "on" : ""}`} onClick={() => setGroup(k)}>{v}</button>)}
          </div>
        </div>
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr><th>방법</th><th className="num">창 지수 일치도 (95% 구간)</th><th className="num">탐지율</th><th className="num">대조군 창 내 경보</th><th className="num">차이 %p (95% 구간)</th><th className="num">선행 등판 중앙값</th><th className="num">실측 오경보 /100</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.method} className={r.method === "구속 하락 신호" ? "hl" : ""}>
                  <td><span className="pill" style={{ margin: 0 }}><span className="dot" style={{ background: COLORS[r.method] }} />{r.method}</span></td>
                  <td className="num">{fmt.num(r.concordance, 3)} <span style={{ color: "var(--muted)" }}>({fmt.num(r.concordance_lo, 3)}~{fmt.num(r.concordance_hi, 3)})</span></td>
                  <td className="num">{fmt.pct(r.detection)}</td><td className="num">{fmt.pct(r.control_window)}</td>
                  <td className="num">{fmt.num(r.diff, 1)} <span style={{ color: "var(--muted)" }}>({fmt.num(r.diff_lo, 1)}~{fmt.num(r.diff_hi, 1)})</span></td>
                  <td className="num">{fmt.num(r.median_lead, 1)}</td>
                  <td className="num">{r.false_alarms_per100 == null ? "—" : fmt.num(r.false_alarms_per100, 2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="note">사례 {rows[0]?.cases}건, 대조군 {rows[0]?.controls}명. B1은 임계가 고정이라 오경보율을 맞추지 않았습니다(실측 그대로).</p>
      </div>
      {followup.length > 0 && (
        <div className="card">
          <h2>경보가 울린 뒤 실제로 어떻게 됐나 <span style={{ color: "var(--muted)", fontWeight: 500 }}>· 사후 지표 (사전 등록 아님)</span></h2>
          <p className="caption">구속 하락 경보가 울린 등판 뒤 30일 안에 그 투수가 팔꿈치·어깨 부상으로 IL에 오른 비율과, 경보가 없던 등판의 같은 비율입니다. 모든 감시 등판(사례·대조군 아닌 투수 포함)을 셉니다.</p>
          <div className="kpi">
            {followup.map((f) => (
              <div key={f.split}>
                <div className="v">{fmt.pct(100 * f.alarm_rate)} <span style={{ color: "var(--muted)", fontWeight: 500, fontSize: 15 }}>vs {fmt.pct(100 * f.other_rate)}</span></div>
                <div className="l">{f.split === "dev" ? "개발셋" : f.split === "val" ? "검증셋" : "봉인"} {f.seasons} · 경보 {f.alarms}개 중 {f.alarm_followed}개 → <b>{fmt.num(f.lift, 1)}배</b></div>
              </div>
            ))}
          </div>
          <p className="note">경보 뒤 30일 안 IL 비율이 경보 없는 등판의 약 2배(검증셋 2.2배, 봉인 2.0배)입니다. 다만 10건 중 9건은 30일 안에 IL로 이어지지 않으므로, 경보는 '점검을 시작할 때'이지 부상 판정이 아닙니다.</p>
        </div>
      )}
    </div>
  );
}
