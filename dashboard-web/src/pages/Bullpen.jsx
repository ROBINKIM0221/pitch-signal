import { useEffect, useState } from "react";
import { Bar, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis, Legend } from "recharts";
import { fmt, useJson } from "../lib/data.js";

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
  return (
    <div className="page">
      <h1>⑤ 불펜 부하</h1>
      <p className="lead">불펜은 투구 품질보다 사용 패턴에서 혹사가 먼저 드러납니다. 부하 채널(연투, 3일 등판 수, 7일 투구 수, ACWR, 긴 등판 뒤 짧은 휴식)과 품질 채널의 경보를 섞지 않고 같은 시간축에 나란히 둡니다. 표시 기준은 개발셋 대조군을 보고 정한 값입니다.</p>
      <div className="row">
        <label>불펜 투수
          {" "}
          <select value={id || ""} onChange={(e) => setId(e.target.value)}>
            {data.pitchers.map((x) => <option key={x.id} value={x.id}>{x.name} · {x.season} · {x.group === "case" ? "사례" : "대조군"}</option>)}
          </select>
        </label>
      </div>
      {p && (
        <div className="card">
          <h2>{p.name} · {p.season} · {p.group === "case" ? `사례 (IL ${p.il_date})` : `대조군 (가상 기준일 ${p.il_date})`}</h2>
          <ResponsiveContainer width="100%" height={300}>
            <ComposedChart data={days} margin={{ top: 16, right: 10, left: 0, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke="var(--line)" />
              <XAxis dataKey="date" tickFormatter={fmt.date} tick={{ fontSize: 11 }} />
              <YAxis yAxisId="p" tick={{ fontSize: 11 }} width={34} />
              <YAxis yAxisId="a" orientation="right" domain={[0, "auto"]} tick={{ fontSize: 11 }} width={34} />
              <Tooltip content={<LoadTip names={data.flag_names} />} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar yAxisId="p" dataKey="pitches" name="등판 투구 수" fill="var(--velo)" radius={[3, 3, 0, 0]} isAnimationActive={false} />
              <Line yAxisId="a" type="monotone" dataKey="acwr" name="ACWR" stroke="var(--warn)" strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
              <Scatter yAxisId="p" dataKey="marker" name="품질 채널 경보" shape={<Mark />} isAnimationActive={false} />
              <ReferenceLine yAxisId="p" x={p.il_date} stroke="var(--ink)" label={{ value: p.group === "case" ? "IL" : "기준일", position: "top", fontSize: 11 }} />
            </ComposedChart>
          </ResponsiveContainer>
          <h3>부하 표시가 켜진 등판</h3>
          <div style={{ overflowX: "auto" }}>
            <table className="tbl">
              <thead><tr><th>날짜</th><th>투구 수</th><th>3일 등판</th><th>7일 투구</th><th>ACWR</th><th>표시</th><th>품질 경보</th></tr></thead>
              <tbody>
                {days.filter((d) => d.flags.length || d.signals.length).map((d) => (
                  <tr key={d.date}>
                    <td>{d.date}</td><td>{d.pitches}</td><td>{d.apps_3d}</td><td>{fmt.num(d.p7d, 0)}</td><td>{fmt.num(d.acwr)}</td>
                    <td>{d.flags.map((f) => <span key={f} className="pill">{data.flag_names[f] || f}</span>)}</td>
                    <td>{d.signals.map((s) => <span key={s} className="light alarm">{s === "velo" ? "구속 하락" : "폼 변화"}</span>)}</td>
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

function LoadTip({ active, payload, names }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="card" style={{ padding: "8px 10px", fontSize: 12 }}>
      <div><b>{d.date}</b> 투구 {d.pitches}구 {d.back_to_back ? "· 연투" : ""}</div>
      <div>3일 등판 {d.apps_3d}회 · 7일 투구 {fmt.num(d.p7d, 0)}구 · ACWR {fmt.num(d.acwr)}</div>
      {d.flags.length > 0 && <div>표시: {d.flags.map((f) => names[f] || f).join(", ")}</div>}
      {d.signals.length > 0 && <div style={{ color: "var(--alarm)" }}>품질 채널 경보: {d.signals.map((s) => (s === "velo" ? "구속 하락" : "폼 변화")).join(", ")}</div>}
    </div>
  );
}
