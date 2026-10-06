import { useEffect, useState } from "react";
import { Bar, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis, Legend } from "recharts";
import { fmt, useJson } from "../lib/data.js";
import { GRID, LABEL, LEGEND_STYLE, TICK, TIP_STYLE, limitLabel } from "../lib/chart.jsx";

const RULE_NAME = { daily_max: "하루 105구 초과", rest: "의무 휴식일 미준수", three_days: "3일 연속 등판", unknown: "투구 수 기록 없음(판정 불가)" };
const LOAD_CLASS = { "보통": "ok", "주의": "warn", "경보": "alarm", "계산 불가": "base" };

export default function HighSchool() {
  const { data } = useJson("highschool.json");
  const [school, setSchool] = useState(null);
  const [code, setCode] = useState(null);
  const [foreign, setForeign] = useState("none");
  useEffect(() => { if (data && !school) setSchool(data.schools[0]?.code); }, [data, school]);
  const s = data?.schools.find((x) => x.code === school);
  useEffect(() => { if (s && !s.pitchers.find((p) => p.code === code)) setCode(s.pitchers[0]?.code); }, [s, code]);
  if (!data) return <div className="placeholder">고교 현황판 자료를 읽는 중…</div>;
  const p = s?.pitchers.find((x) => x.code === code);
  const rule = foreign !== "none" ? data.foreign_rules[foreign] : null;
  const days = (p?.days || []).map((d) => ({ ...d, over: rule ? (d.sum_7d != null && d.sum_7d > rule.max_pitches) : false }));
  const summary = data.summary.find((r) => r["학교"] === school);
  return (
    <div className="page">
      <h1>고교 투구수 현황판 {data.synthetic && <span className="badge synthetic">가상 데이터</span>}</h1>
      <p className="lead">
        {data.season} 시즌 경기도 고교 {data.schools.length}곳. 학교는 S01~, 투수는 S01-P03 같은 가명 코드만 씁니다. 신호등 두 개는 서로 다른 뜻입니다.
        <b> 규정</b>은 KBSA 투구수 규정(하루 {data.kbsa.daily_max}구, 투구 수별 휴식일, 3일 연속 금지)을 지켰는지, <b>누적 부하</b>는 ACWR(최근 7일 ÷ 그 전 3주 주평균)이 {data.acwr_flag}을 넘은 적이 있는지입니다.
        {data.synthetic && " 지금 보이는 숫자는 양식을 보여 주기 위한 가상 기록이며, 실제 입력이 끝나면 바뀝니다."}
      </p>
      <div className="toolbar">
        <label><span>학교</span><select value={school || ""} onChange={(e) => setSchool(e.target.value)}>{data.schools.map((x) => <option key={x.code}>{x.code}</option>)}</select></label>
        <label><span>해외 규정 비교</span>
          <select value={foreign} onChange={(e) => setForeign(e.target.value)}>
            <option value="none">없음</option>
            {Object.entries(data.foreign_rules).map(([k, v]) => <option key={k} value={k}>{k === "japan" ? "일본" : k} {v.window_days}일 {v.max_pitches}구</option>)}
          </select>
        </label>
      </div>
      {summary && (
        <div className="kpi">
          <div><div className="v">{summary["투수 수"]}</div><div className="l">투수</div></div>
          <div><div className="v">{summary["규정 위반 건수"]}</div><div className="l">규정 위반 건수 · 투수 {summary["위반 투수 수"]}명</div></div>
          <div><div className="v">{summary["ACWR 기준 초과 투수 수"]}<span style={{ color: "var(--muted)", fontWeight: 500 }}> / {summary["ACWR 계산 가능 투수 수"]}</span></div><div className="l">ACWR {data.acwr_flag} 초과 경험 / 계산 가능 투수</div></div>
          <div><div className="v">{summary["위반 없이 누적 부하 표시"]}</div><div className="l">규정은 지켰지만 누적 부하 표시가 있던 투수</div></div>
        </div>
      )}
      <div className="grid2">
        <div className="card">
          <h2>{school} 투수 <span style={{ color: "var(--muted)", fontWeight: 500 }}>· 규정 / 누적 부하</span></h2>
          <div className="list">
            {s?.pitchers.map((x) => (
              <button key={x.code} className={x.code === code ? "on" : ""} onClick={() => setCode(x.code)}>
                <span className="code">{x.code}</span>
                <span className={`light ${x.rule_status === "준수" ? "ok" : "alarm"}`}>규정 {x.rule_status}</span>
                <span className={`light ${LOAD_CLASS[x.load_status]}`}>부하 {x.load_status}</span>
              </button>
            ))}
          </div>
        </div>
        <div className="card">
          <h2>{code} <span style={{ color: "var(--muted)", fontWeight: 500 }}>· 일별 투구 수와 ACWR</span></h2>
          <ResponsiveContainer width="100%" height={270}>
            <ComposedChart data={days} margin={{ top: 12, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke={GRID} />
              <XAxis dataKey="date" tickFormatter={fmt.date} tick={TICK} axisLine={{ stroke: GRID }} tickLine={false} minTickGap={24} />
              <YAxis yAxisId="p" tick={TICK} width={34} axisLine={false} tickLine={false} />
              <YAxis yAxisId="a" orientation="right" domain={[0, 4]} allowDataOverflow tick={TICK} width={34} axisLine={false} tickLine={false} />
              <Tooltip {...TIP_STYLE} labelFormatter={(d) => d} formatter={(v, n) => [v == null ? "계산 불가" : fmt.num(v, n === "ACWR" ? 2 : 0), n]} />
              <Legend wrapperStyle={LEGEND_STYLE} verticalAlign="top" iconType="plainline" />
              <Bar yAxisId="p" dataKey="pitches" name="투구 수" fill="var(--velo)" radius={[3, 3, 0, 0]} isAnimationActive={false} />
              <Line yAxisId="a" type="monotone" dataKey="acwr" name="ACWR" stroke="var(--warn)" strokeWidth={2} dot={{ r: 2.5 }} connectNulls isAnimationActive={false} />
              <ReferenceLine yAxisId="a" y={data.acwr_flag} stroke="var(--alarm)" strokeDasharray="4 4" label={limitLabel(`ACWR ${data.acwr_flag}`)} />
              {p?.violations.map((v) => <ReferenceLine key={v.date + v.rule} yAxisId="p" x={v.date} stroke="var(--alarm)" label={{ value: "위반", position: "insideTop", ...LABEL, fill: "var(--alarm)" }} />)}
            </ComposedChart>
          </ResponsiveContainer>
          <p className="caption">ACWR은 수집 기간이 4주 쌓인 뒤부터 계산되고, 투구 수를 모르는 날이 창에 들어가면 계산하지 않습니다. 오른쪽 축은 4까지만 보이며 그보다 큰 값은 잘립니다(값은 마우스를 올리면 보임).
            {rule && ` 해외 규정 비교: 7일 합이 ${rule.max_pitches}구를 넘은 날 ${days.filter((d) => d.over).length}일.`}</p>
          {p?.violations.length > 0 && (
            <div className="tbl-wrap" style={{ marginTop: 8 }}>
              <table className="tbl">
                <thead><tr><th>날짜</th><th>규정</th><th>내용</th></tr></thead>
                <tbody>{p.violations.map((v) => <tr key={v.date + v.rule}><td>{v.date}</td><td><span className="light alarm">{RULE_NAME[v.rule] || v.rule}</span></td><td style={{ whiteSpace: "normal" }}>{v.detail}</td></tr>)}</tbody>
              </table>
            </div>
          )}
        </div>
      </div>
      <p className="note">한계: 공식 경기 투구 수만 반영되고 연습·불펜 투구는 빠집니다. 고교에는 공식 부상 기록이 없어 이 화면은 '규정이 보지 못하는 부하를 보여 주는 현황판'이지 탐지 성능을 검증한 것이 아닙니다.</p>
    </div>
  );
}
