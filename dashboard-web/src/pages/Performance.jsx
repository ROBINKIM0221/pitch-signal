import { useState } from "react";
import { Link } from "react-router-dom";
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
      <p className="lead">평가 계획을 고정한 뒤 한 번 계산한 결과입니다. 모든 방법을 같은 투수·같은 기간으로 비교했고, 기준값은 2021~2023 시즌에서만 맞췄습니다.</p>
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
          <p className="caption">구속 하락 경보가 울린 등판 뒤 30일 안에 그 투수가 팔꿈치·어깨 부상으로 IL에 오른 비율과, 경보가 없던 등판의 같은 비율입니다. 분석한 모든 등판(사례·대조군 아닌 투수 포함)을 셉니다.</p>
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

/** 리플레이 아래 '검증 요약' (2026-10-16 외부 검토: 성능 비교 화면을 메뉴에서 빼고 결론만). 숫자는 performance.json에서 읽는다. */
export function ValidationSummary() {
  const { data } = useJson("performance.json");
  if (!data) return null;
  const velo = data.results.find((r) => r.method === "구속 하락 신호" && r.group === "all");
  const form = data.results.find((r) => r.method === "폼 변화 신호" && r.group === "all");
  const b1 = data.results.find((r) => r.method === "B1 구속 1mph" && r.group === "all");
  const baselines = data.results.filter((r) => r.group === "all" && /^B[2-4]/.test(r.method));
  const sealedH1 = data.sealed?.tests.find((t) => t.test.startsWith("H1"));
  const fu = (split) => (data.followup || []).find((f) => f.role === "all" && f.method === "구속 하락 신호" && f.split === split);
  const val = fu("val"), sealed = fu("sealed");
  const formFu = (data.followup || []).find((f) => f.role === "all" && f.method === "폼 변화 신호" && f.split === "val");
  const curve = (name) => data.opcurve.filter((q) => q.method === name).sort((a, b) => a.false_alarms_per100 - b.false_alarms_per100);
  return (
    <div className="card">
      <div className="card-head">
        <h2>검증 요약 <span style={{ color: "var(--muted)", fontWeight: 500, fontSize: 13 }}>MLB {data.seasons.join("~")} 검증셋 · 평가 계획을 고정한 뒤 한 번 계산</span></h2>
        <Link to="/performance" className="caption" style={{ margin: 0 }}>자세한 결과표 →</Link>
      </div>
      <div className="grid2" style={{ alignItems: "start" }}>
        <ol className="findings">
          <li><b>같은 오경보 수준(부상 없는 투수 100등판에 1번)에서, 부상 투수의 IL 직전 5등판 안 경보는 {fmt.pct(velo?.detection)}, 부상 없는 투수는 {fmt.pct(velo?.control_window)}입니다.</b>
            {" "}미리 정한 주 지표(일치도: 부상 투수의 경보 지수가 짝지은 부상 없는 투수보다 클 확률)로 둘을 구별한 방법은 구속 하락 신호뿐이었습니다({fmt.num(velo?.concordance, 2)}, 95% 구간 하한 {fmt.num(velo?.concordance_lo, 2)}). 기존 방법(WHIP 관리도, 다변량 거리, 양방향 구속)은 구간이 0.5를 포함했습니다.</li>
          <li><b>경보가 울린 뒤 30일 안에 팔 부상으로 IL에 오른 비율은 {fmt.pct(100 * (val?.alarm_rate ?? 0))}로, 경보 없는 등판({fmt.pct(100 * (val?.other_rate ?? 0))})의 {fmt.num(val?.lift, 1)}배입니다.</b>
            {sealed && ` 봉인해 둔 2026 시즌에서도 ${fmt.num(sealed.lift, 1)}배였습니다.`} 그래도 열 번 중 아홉 번은 부상으로 이어지지 않으므로, 경보는 점검을 시작할 때이지 부상 판정이 아닙니다.</li>
          <li><b>폼 변화 지수는 구속 하락 경보와 함께 보는 보조 정보입니다.</b> 경보 뒤 30일 안 팔 IL 비율은 {fmt.num(formFu?.lift, 1)}배로 방향은 같지만, IL 직전 5등판 안 경보({fmt.pct(form?.detection)} vs {fmt.pct(form?.control_window)})와 주 지표(일치도 {fmt.num(form?.concordance, 2)}) 모두 우연과 구별될 만큼 차이 나지 않았습니다.
            <details className="more" style={{ margin: "8px 0 0" }}>
              <summary>한계 보기</summary>
              <p>흔히 쓰는 '구속 1mph(1.6km/h) 하락' 규칙은 더 많이 잡지만({fmt.pct(b1?.detection)}) 부상 없는 투수에게도 100등판에 {fmt.num(b1?.false_alarms_per100, 1)}번 울립니다.
                {sealedH1 && ` 2026 봉인 시즌에서는 구속 하락 신호의 순위 비교(일치도 ${fmt.num(sealedH1.value, 2)})가 재현되지 않았습니다 — 경보 뒤 IL 비율(위 2번)은 재현됐습니다.`}</p>
            </details></li>
        </ol>
        <div>
          <ResponsiveContainer width="100%" height={260}>
            <ComposedChart margin={{ top: 8, right: 16, left: 0, bottom: 24 }}>
              <CartesianGrid stroke={GRID} />
              <XAxis dataKey="false_alarms_per100" type="number" domain={[0, 8]} tick={TICK} axisLine={{ stroke: GRID }} tickLine={false}
                label={{ value: "부상 없는 투수 100등판당 경보 수", position: "bottom", offset: 8, ...LABEL }} />
              <YAxis dataKey="detection" type="number" tick={TICK} width={40} axisLine={false} tickLine={false} unit="%" />
              <Tooltip {...TIP_STYLE} formatter={(v, n) => [`${fmt.num(v, 1)}%`, n]} labelFormatter={(v) => `경보 ${fmt.num(v, 2)}/100등판`} />
              <ReferenceLine x={data.design_far} stroke="var(--muted)" strokeDasharray="4 4" label={{ value: "설계점", position: "insideTopLeft", ...LABEL, fill: "var(--muted)" }} />
              {baselines.map((r) => <Line key={r.method} data={curve(r.method)} dataKey="detection" name={r.method} stroke="#b8c0cc" strokeWidth={1.2} dot={false} isAnimationActive={false} />)}
              <Line data={curve("구속 하락 신호")} dataKey="detection" name="구속 하락 신호" stroke="var(--navy-2)" strokeWidth={3} dot={{ r: 3, fill: "#fff", strokeWidth: 1.5 }} isAnimationActive={false} />
              <Scatter data={data.opcurve.filter((q) => q.method === "B1 구속 1mph" && q.scale === 1)} dataKey="detection" name="구속 1mph 하락 규칙" fill="var(--warn)" shape="diamond" isAnimationActive={false} />
            </ComposedChart>
          </ResponsiveContainer>
          <p className="caption">경보를 더 자주 허용할수록 더 많이 잡습니다. 굵은 선이 구속 하락 신호, 회색 선이 기존 방법, 주황 마름모가 '구속 1mph 하락' 규칙입니다. <span className="hover-hint">선에 커서를 올리면 값</span></p>
        </div>
      </div>
    </div>
  );
}
