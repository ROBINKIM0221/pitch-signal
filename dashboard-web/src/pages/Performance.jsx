import { useState } from "react";
import { CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis, Legend } from "recharts";
import { fmt, useJson } from "../lib/data.js";

const COLORS = { "구속 하락 신호": "#2a78d6", "폼 변화 신호": "#3f9b6c", "B2 WHIP CUSUM": "#8e6bbf", "B3 마할라노비스": "#c94f7c",
  "B4 구속 EWMA(양방향)": "#5d9ec7", "B1 구속 1mph": "#d9822b", "합의 규칙": "#8a8880" };
const LINES = ["구속 하락 신호", "폼 변화 신호", "B2 WHIP CUSUM", "B3 마할라노비스", "B4 구속 EWMA(양방향)"];
const POINTS = ["B1 구속 1mph", "합의 규칙"];
const GROUP = { all: "전체", SP: "선발", RP: "불펜" };

export default function Performance() {
  const { data } = useJson("performance.json");
  const [group, setGroup] = useState("all");
  if (!data) return <div className="placeholder">성능 비교 자료를 읽는 중…</div>;
  const rows = data.results.filter((r) => r.group === group);
  const h1 = data.tests.find((t) => t.test.startsWith("H1"));
  const h2 = data.tests.find((t) => t.test.startsWith("H2"));
  return (
    <div className="page">
      <h1>③ 성능 비교</h1>
      <p className="lead">검증셋 {data.seasons.join("~")}: 평가 계획을 고정한 뒤 한 번 계산한 결과입니다. 모든 방법은 같은 사례·대조군·관찰 창을 쓰고, 임계값은 개발셋에서만 맞췄습니다.</p>
      <div className="card">
        <h2>미리 정한 가설</h2>
        <div className="kpi">
          <div><div className="v">{fmt.num(h1?.value, 3)}</div><div className="l">H1 구속 하락 지수 일치도 (95% 구간 {fmt.num(h1?.ci_lo, 3)}~{fmt.num(h1?.ci_hi, 3)}) → {h1?.supported ? "지지" : "지지 안 됨"}</div></div>
          <div><div className="v">{fmt.num(h2?.value, 0)}등판</div><div className="l">H2 첫 경보의 선행 등판 수 중앙값 → {h2?.supported ? "지지" : "지지 안 됨"}</div></div>
        </div>
        <p className="note">일치도는 사례의 창 지수가 짝지은 대조군보다 클 확률입니다. 0.5면 정보가 없고 1이면 사례가 늘 큽니다.</p>
      </div>
      <div className="card">
        <h2>운영 곡선 · 오경보를 얼마나 허용하느냐에 따른 탐지율</h2>
        <ResponsiveContainer width="100%" height={340}>
          <ComposedChart margin={{ top: 10, right: 24, left: 4, bottom: 24 }}>
            <CartesianGrid stroke="var(--line)" />
            <XAxis dataKey="false_alarms_per100" type="number" name="오경보" domain={[0, "auto"]} tick={{ fontSize: 11 }}
              label={{ value: "대조군 100등판당 오경보 수", position: "bottom", offset: 6, fontSize: 12 }} />
            <YAxis dataKey="detection" type="number" tick={{ fontSize: 11 }} width={44} label={{ value: "탐지율 (%)", angle: -90, position: "insideLeft", offset: 12, fontSize: 12 }} />
            <Tooltip formatter={(v, n) => [fmt.num(v, 1), n]} labelFormatter={(v) => `오경보 ${fmt.num(v, 2)}/100`} />
            <Legend verticalAlign="top" wrapperStyle={{ fontSize: 12, paddingBottom: 6 }} />
            <ReferenceLine x={data.design_far} stroke="var(--muted)" strokeDasharray="4 4" label={{ value: "설계점 1회", position: "top", fontSize: 11 }} />
            {LINES.map((name) => (
              <Line key={name} data={data.opcurve.filter((p) => p.method === name).sort((a, b) => a.false_alarms_per100 - b.false_alarms_per100)}
                dataKey="detection" name={name} stroke={COLORS[name]} strokeWidth={name === "구속 하락 신호" ? 3 : 1.5} dot={{ r: 3 }} isAnimationActive={false} />
            ))}
            {POINTS.map((name) => (
              <Scatter key={name} data={data.opcurve.filter((p) => p.method === name)} dataKey="detection" name={name} fill={COLORS[name]} shape="diamond" legendType="diamond" isAnimationActive={false} />
            ))}
          </ComposedChart>
        </ResponsiveContainer>
        <p className="note">선은 한계에 배수를 곱해 가며 그린 것이고, B1(고정 임계)과 합의 규칙은 점입니다. 설계점(100등판당 1회)에서의 값이 아래 표입니다.</p>
      </div>
      <div className="card">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <h2 style={{ margin: 0 }}>결과표 (100등판당 오경보 1회 기준)</h2>
          <div>{Object.entries(GROUP).map(([k, v]) => <button key={k} className={`btn ${group === k ? "on" : ""}`} onClick={() => setGroup(k)} style={{ marginLeft: 4 }}>{v}</button>)}</div>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table className="tbl">
            <thead><tr><th>방법</th><th>창 지수 일치도 (95% 구간)</th><th>탐지율</th><th>대조군 창 내 경보</th><th>차이 (95% 구간)</th><th>선행 등판 중앙값</th><th>실측 오경보 /100</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.method} className={r.method === "구속 하락 신호" ? "hl" : ""}>
                  <td>{r.method}</td>
                  <td>{fmt.num(r.concordance, 3)} ({fmt.num(r.concordance_lo, 3)}~{fmt.num(r.concordance_hi, 3)})</td>
                  <td>{fmt.pct(r.detection)}</td><td>{fmt.pct(r.control_window)}</td>
                  <td>{fmt.num(r.diff, 1)} ({fmt.num(r.diff_lo, 1)}~{fmt.num(r.diff_hi, 1)})</td>
                  <td>{fmt.num(r.median_lead, 1)}</td>
                  <td>{r.false_alarms_per100 == null ? "—" : fmt.num(r.false_alarms_per100, 2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="note">사례 {rows[0]?.cases}건, 대조군 {rows[0]?.controls}명. B1은 임계가 고정이라 오경보율을 맞추지 않았습니다(실측 그대로).</p>
      </div>
    </div>
  );
}
