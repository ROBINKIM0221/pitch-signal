import { useEffect, useState } from "react";
import { CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis, Legend } from "recharts";
import { fmt, useJson } from "../lib/data.js";

const PART = { elbow: "팔꿈치", shoulder: "어깨", hamstring: "햄스트링" };

export default function Kbo() {
  const { data } = useJson("kbo_case.json");
  const [name, setName] = useState(null);
  useEffect(() => { if (data && !name) setName(data.pitchers[0]?.name); }, [data, name]);
  if (!data) return <div className="placeholder">KBO 사례 자료를 읽는 중…</div>;
  const p = data.pitchers.find((x) => x.name === name);
  const rows = (p?.series || []).map((r) => ({ ...r }));
  return (
    <div className="page">
      <h1>⑥ KBO 2026 사례 {data.synthetic && <span className="badge synthetic">구속 그래프는 가상 데이터</span>}</h1>
      <p className="lead">2026 시즌 팔꿈치·어깨 문제로 1군에서 말소된 외국인 투수 세 명. '신호 → 말소 → 결정'의 날짜는 공개 기록이고, 구속 그래프는 수집 전이라 가상으로 그린 자리입니다. 구속 하나로 같은 움직이는 기준선과 한 방향 EWMA를 적용합니다.</p>
      <div className="row">
        {data.pitchers.map((x) => <button key={x.name} className={`btn ${x.name === name ? "on" : ""}`} onClick={() => setName(x.name)}>{x.name} ({x.team})</button>)}
      </div>
      {p && (
        <div className="card">
          <h2>{p.name} · {p.team} · {PART[p.part] || p.part}</h2>
          <div className="kpi">
            <div><div className="v">{p.removed}</div><div className="l">1군 말소</div></div>
            <div><div className="v">{p.decision}</div><div className="l">구단 결정 ({p.decision_type})</div></div>
            <div><div className="v">{Math.round((new Date(p.decision) - new Date(p.removed)) / 86400000)}일</div><div className="l">말소에서 결정까지</div></div>
            <div><div className="v" style={{ fontSize: 15 }}>{p.replacement}</div><div className="l">대체 선수 · {p.outcome}</div></div>
          </div>
          <ResponsiveContainer width="100%" height={260}>
            <ComposedChart data={rows} margin={{ top: 16, right: 10, left: 0, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke="var(--line)" />
              <XAxis dataKey="date" tickFormatter={fmt.date} tick={{ fontSize: 11 }} />
              <YAxis yAxisId="v" domain={["auto", "auto"]} tick={{ fontSize: 11 }} width={40} />
              <YAxis yAxisId="i" orientation="right" domain={[-1, 2]} tick={{ fontSize: 11 }} width={34} />
              <Tooltip formatter={(v, n) => [fmt.num(v, n === "구속 (km/h)" ? 1 : 2), n]} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Line yAxisId="v" type="monotone" dataKey="velo" name="구속 (km/h)" stroke="var(--ink-2)" strokeWidth={1.5} dot={{ r: 3 }} isAnimationActive={false} />
              <Line yAxisId="i" type="monotone" dataKey="index" name="구속 하락 지수" stroke="var(--velo)" strokeWidth={2} dot={false} isAnimationActive={false} />
              <ReferenceLine yAxisId="i" y={1} stroke="var(--alarm)" strokeDasharray="4 4" label={{ value: "경보 한계 1", position: "right", fontSize: 11 }} />
            </ComposedChart>
          </ResponsiveContainer>
          <p className="note">타임라인: 말소 {p.removed} → 결정 {p.decision} ({p.decision_type}). 대체 선수 {p.replacement}, 경과: {p.outcome}.</p>
        </div>
      )}
      <div className="card">
        <h2>대응 사례 (감시 대상 아님)</h2>
        {data.response_only.map((x) => (
          <p key={x.name} className="note" style={{ margin: "4px 0" }}>
            <b>{x.name}</b> ({x.team}) · {PART[x.part] || x.part} · 말소 {x.removed} → 결정 {x.decision} ({x.decision_type}) · 대체 {x.replacement} · {x.outcome}. {x.note}
          </p>
        ))}
      </div>
      <p className="note">한계: KBO 사례는 구속만 쓰며 사후 사례 연구입니다. 대체 후보 추천은 만들지 않고 로드맵에 둡니다.</p>
    </div>
  );
}
