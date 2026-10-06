import { useEffect, useState } from "react";
import { Bar, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis } from "recharts";
import { fmt, useJson } from "../lib/data.js";
import { ChartTip, GRID, LABEL, TICK, limitLabel } from "../lib/chart.jsx";

function Mark({ cx, cy, payload }) {
  if (cx == null || !payload?.signals?.length) return null;
  return <circle cx={cx} cy={cy} r={5} fill="var(--alarm)" stroke="#fff" strokeWidth={1.5} />;
}

export default function Bullpen() {
  const { data } = useJson("bullpen.json");
  const [id, setId] = useState(null);
  useEffect(() => { if (data && !id) setId(data.pitchers[0]?.id); }, [data, id]);
  if (!data) return <div className="placeholder">불펜 부하 자료를 읽는 중…</div>;
  const p = data.pitchers.find((x) => x.id === id);
  const alarmDates = new Map((p?.alarms || []).map((a) => [a.date, a.signals]));
  const days = (p?.days || []).map((d) => ({ ...d, signals: alarmDates.get(d.date) || [], marker: alarmDates.has(d.date) ? d.pitches : null }));
  const flagged = days.filter((d) => d.flags.length || d.signals.length);
  // IL 등재(기준일) 선: 날짜 축은 등판 날짜만 있으므로, 그 날 이후 첫 등판 자리에 긋고 등판이 없으면 빈 칸을 하나 덧붙인다
  let ilX = p ? days.find((d) => d.date >= p.il_date)?.date : null;
  if (p && !ilX) { days.push({ date: p.il_date, pitches: null, acwr: null, flags: [], signals: [], marker: null, placeholder: true }); ilX = p.il_date; }
  const acwrMax = Math.max(data.acwr_flag + 0.5, ...days.map((d) => d.acwr ?? 0));
  return (
    <div className="page">
      <h1>불펜 부하</h1>
      <p className="lead">불펜은 투구 품질보다 사용 패턴에서 혹사가 먼저 드러납니다. 부하 채널(연투, 3일 등판 수, 7일 투구 수, ACWR, 긴 등판 뒤 짧은 휴식)과 품질 채널의 경보를 섞지 않고 같은 시간축에 나란히 둡니다. 표시 기준은 개발셋 대조군을 보고 정한 값입니다.</p>
      <div className="toolbar">
        <label><span>불펜 투수</span>
          <select value={id || ""} onChange={(e) => setId(e.target.value)} style={{ maxWidth: 360 }}>
            {data.pitchers.map((x) => <option key={x.id} value={x.id}>{x.name} · {x.season} · {x.group === "case" ? "사례" : "대조군"}</option>)}
          </select>
        </label>
      </div>
      {p && (
        <div className="card">
          <div className="card-head">
            <h2>{p.name} <span style={{ color: "var(--muted)", fontWeight: 500 }}>· {p.season} · {p.group === "case" ? `사례 · IL ${p.il_date}` : `대조군 · 가상 기준일 ${p.il_date}`}</span></h2>
            <div className="legend">
              <span><i className="band" style={{ background: "var(--velo)" }} />등판 투구 수</span>
              <span><i style={{ background: "var(--warn)" }} />ACWR (오른쪽 축)</span>
              <span><i className="dot" style={{ background: "var(--alarm)" }} />품질 채널 경보</span>
              <span><i className="dash" />ACWR 표시 기준 {data.acwr_flag}</span>
              <span><i style={{ background: "var(--ink)" }} />IL 등재(기준일)</span>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={300}>
            <ComposedChart data={days} margin={{ top: 16, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke={GRID} />
              <XAxis dataKey="date" tickFormatter={fmt.date} tick={TICK} axisLine={{ stroke: GRID }} tickLine={false} minTickGap={24} />
              <YAxis yAxisId="p" tick={TICK} width={34} axisLine={false} tickLine={false} />
              <YAxis yAxisId="a" orientation="right" domain={[0, Math.ceil(acwrMax * 2) / 2]} tickCount={6} tickFormatter={(v) => v.toFixed(1)} tick={TICK} width={36} axisLine={false} tickLine={false} />
              <Tooltip content={<ChartTip render={(payload) => <LoadTip d={payload[0].payload} names={data.flag_names} />} />} cursor={{ fill: "rgba(20,20,19,0.04)" }} />
              <Bar yAxisId="p" dataKey="pitches" name="등판 투구 수" fill="var(--velo)" radius={[3, 3, 0, 0]} isAnimationActive={false} />
              <Line yAxisId="a" type="monotone" dataKey="acwr" name="ACWR" stroke="var(--warn)" strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
              <Scatter yAxisId="p" dataKey="marker" name="품질 채널 경보" shape={<Mark />} isAnimationActive={false} tooltipType="none" />
              <ReferenceLine yAxisId="a" y={data.acwr_flag} stroke="var(--alarm)" strokeDasharray="4 4" label={limitLabel(`ACWR ${data.acwr_flag}`)} />
              <ReferenceLine yAxisId="p" x={ilX} stroke="var(--ink)" strokeWidth={1.2} label={{ value: p.group === "case" ? `IL 등재 ${fmt.date(p.il_date)}` : `기준일 ${fmt.date(p.il_date)}`, position: "insideTopRight", ...LABEL }} />
            </ComposedChart>
          </ResponsiveContainer>
          <h3>부하 표시가 켜진 등판 <span style={{ color: "var(--muted)", fontWeight: 500 }}>· {flagged.length}건</span></h3>
          <div className="tbl-wrap">
            <table className="tbl">
              <thead><tr><th>날짜</th><th className="num">투구 수</th><th className="num">3일 등판</th><th className="num">7일 투구</th><th className="num">ACWR</th><th>표시</th><th>품질 경보</th></tr></thead>
              <tbody>
                {flagged.map((d) => (
                  <tr key={d.date}>
                    <td>{d.date}</td><td className="num">{d.pitches}</td><td className="num">{d.apps_3d}</td><td className="num">{fmt.num(d.p7d, 0)}</td><td className="num">{fmt.num(d.acwr)}</td>
                    <td>{d.flags.map((f) => <span key={f} className="light warn" style={{ marginRight: 4 }}>{data.flag_names[f] || f}</span>)}</td>
                    <td>{d.signals.map((s) => <span key={s} className="light alarm" style={{ marginRight: 4 }}>{s === "velo" ? "구속 하락" : "폼 변화"}</span>)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="note">한계: 불펜에서 몸만 풀고 등판하지 않은 투구는 기록에 없어 실제 부하는 이보다 큽니다.</p>
        </div>
      )}
    </div>
  );
}

function LoadTip({ d, names }) {
  return (
    <>
      {d.placeholder ? <div><b>{d.date}</b> · IL 등재(기준일)</div> : <div><b>{d.date}</b> · 투구 {d.pitches}구 {d.back_to_back ? "· 연투" : ""}</div>}
      {!d.placeholder && <div>3일 등판 {d.apps_3d}회 · 7일 투구 {fmt.num(d.p7d, 0)}구 · ACWR {fmt.num(d.acwr)}</div>}
      {d.flags.length > 0 && <div>표시: {d.flags.map((f) => names[f] || f).join(", ")}</div>}
      {d.signals.length > 0 && <div className="alarm">품질 채널 경보: {d.signals.map((s) => (s === "velo" ? "구속 하락" : "폼 변화")).join(", ")}</div>}
    </>
  );
}
