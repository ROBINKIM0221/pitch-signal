import { useEffect, useMemo, useState } from "react";
import {
  Area, ComposedChart, Line, ReferenceArea, ReferenceLine, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis, CartesianGrid,
} from "recharts";
import { FEATURE, PART, ROLE, fmt, useJson } from "../lib/data.js";

const SIGNAL = { velo: { name: "구속 하락 신호", color: "var(--velo)" }, change: { name: "폼 변화 신호", color: "var(--change)" } };

function label(p) {
  const who = p.group === "case" ? (p.detected ? "사례 · 신호 있음" : "사례 · 신호 없음") : "대조군";
  return `${p.name} · ${p.season} ${ROLE[p.role]} · ${who}`;
}

function AlarmDot({ cx, cy, payload }) {
  if (!payload?.alarm_here || cx == null) return null;
  return <circle cx={cx} cy={cy} r={5} fill="var(--alarm)" stroke="#fff" strokeWidth={1.5} />;
}

export default function Replay() {
  const { data: index } = useJson("replay_index.json");
  const { data: alerts } = useJson("alerts.json");
  const [id, setId] = useState(null);
  const [shown, setShown] = useState(null);
  const [side, setSide] = useState(false);
  const [picked, setPicked] = useState(null);
  const cases = useMemo(() => (index || []).filter((p) => p.group === "case"), [index]);
  useEffect(() => { if (cases.length && !id) setId(cases[0].id); }, [cases, id]);
  const entry = index?.find((p) => p.id === id);
  const partner = index?.find((p) => p.case_id === entry?.case_id && p.group !== entry?.group);
  const { data: me } = useJson(id ? `replay_${id}.json` : null);
  const { data: other } = useJson(side && partner ? `replay_${partner.id}.json` : null);
  useEffect(() => { if (me) { setShown(me.outings.length); setPicked(null); } }, [me]);

  if (!index) return <div className="placeholder">리플레이 목록을 읽는 중…</div>;
  const baselineCount = me ? me.outings.filter((o) => o.phase === "baseline").length : 0;
  return (
    <div className="page">
      <h1>① 리플레이 · ② 경보 카드</h1>
      <p className="lead">
        한 투수의 시즌을 등판 순서대로 다시 돌려 봅니다. 회색 띠는 평소를 잡는 시작 구간, 선은 두 신호의 지수(1을 넘으면 경보), 빨간 점은 경보,
        세로선은 IL 등재(대조군은 짝지은 사례의 기준일)입니다. 경보 점을 누르면 카드가 열립니다.
      </p>
      <div className="row">
        <label>투수
          {" "}
          <select value={id || ""} onChange={(e) => setId(e.target.value)}>
            {cases.map((p) => <option key={p.id} value={p.id}>{label(p)}</option>)}
          </select>
        </label>
        {me && (
          <label>재생 위치 {shown}/{me.outings.length} 등판
            {" "}
            <input type="range" min={Math.max(1, baselineCount)} max={me.outings.length} value={shown ?? me.outings.length}
              onChange={(e) => setShown(Number(e.target.value))} />
          </label>
        )}
        {partner && <button className={`btn ${side ? "on" : ""}`} onClick={() => setSide(!side)}>대조군 나란히 보기</button>}
      </div>
      {me && <Pitcher data={me} shown={shown ?? me.outings.length} alerts={alerts} picked={picked} setPicked={setPicked} />}
      {side && other && <Pitcher data={other} shown={other.outings.length} alerts={alerts} picked={picked} setPicked={setPicked} compact />}
      {picked && <AlertCard alert={picked} onClose={() => setPicked(null)} />}
    </div>
  );
}

function Pitcher({ data, shown, alerts, picked, setPicked, compact }) {
  const rows = data.outings.slice(0, shown).map((o, i) => ({
    ...o, i: i + 1, alarm_here: o.velo_alarm || o.change_alarm,
    velo_index: o.velo_index, change_index: o.change_index,
    ...Object.fromEntries(Object.keys(FEATURE).map((f) => [`band_${f}`, o.exp ? [o.exp[f] - 2 * o.sd[f], o.exp[f] + 2 * o.sd[f]] : null])),
  }));
  const ilAt = (() => {
    const before = data.outings.filter((o) => o.date < data.il_date).length;
    return before < data.outings.length ? before + 0.5 : data.outings.length + 0.5;
  })();
  const baseline = rows.filter((r) => r.phase === "baseline").length;
  const myAlerts = (alerts || []).filter((a) => a.id === data.id);
  const onClick = (state) => {
    const row = state?.activePayload?.[0]?.payload;
    if (!row?.alarm_here) return;
    const hit = myAlerts.filter((a) => a.date === row.date);
    if (hit.length) setPicked({ ...hit[0], others: hit.slice(1), who: data.name, row });
  };
  const yMax = Math.max(1.6, ...rows.flatMap((r) => [r.velo_index ?? 0, r.change_index ?? 0])) * 1.08;
  return (
    <div className="card">
      <h2>{data.name} · {data.season} {ROLE[data.role]} · {data.group === "case" ? `사례 (${PART[data.part]}, IL ${data.il_date})` : `대조군 (가상 기준일 ${data.il_date})`}</h2>
      <div className="legend">
        <span><i style={{ background: "var(--velo)" }} />구속 하락 지수</span>
        <span><i style={{ background: "var(--change)" }} />폼 변화 지수</span>
        <span><i className="dot" style={{ background: "var(--alarm)" }} />경보 (지수 &gt; 1)</span>
        <span><i style={{ background: "var(--base)", height: 10 }} />시작 구간</span>
        <span><i style={{ background: "var(--ink)" }} />IL 등재(기준일)</span>
      </div>
      <ResponsiveContainer width="100%" height={compact ? 200 : 260}>
        <ComposedChart data={rows} onClick={onClick} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke="var(--line)" />
          <XAxis dataKey="i" type="number" domain={[0.5, data.outings.length + 0.5]} tickCount={8} tick={{ fontSize: 11 }} label={{ value: "등판 순서", position: "insideBottomRight", offset: -4, fontSize: 11 }} />
          <YAxis domain={[Math.floor(Math.min(-0.5, ...rows.map((r) => r.velo_index ?? 0)) * 2) / 2, Math.ceil(yMax * 2) / 2]} tickFormatter={(v) => v.toFixed(1)} tick={{ fontSize: 11 }} width={34} />
          <Tooltip content={<IndexTip />} />
          {baseline > 0 && <ReferenceArea x1={0.5} x2={baseline + 0.5} fill="var(--base)" fillOpacity={0.18} />}
          <ReferenceLine y={1} stroke="var(--alarm)" strokeDasharray="4 4" label={{ value: "경보 한계 1", position: "right", fontSize: 11, fill: "var(--ink-2)" }} />
          <ReferenceLine y={0} stroke="var(--line)" />
          {ilAt <= data.outings.length && <ReferenceLine x={ilAt} stroke="var(--ink)" label={{ value: "IL", position: "top", fontSize: 11 }} />}
          <Line type="monotone" dataKey="velo_index" stroke="var(--velo)" dot={false} strokeWidth={2} connectNulls name="구속 하락 지수" isAnimationActive={false} />
          <Line type="monotone" dataKey="change_index" stroke="var(--change)" dot={false} strokeWidth={2} connectNulls name="폼 변화 지수" isAnimationActive={false} />
          <Scatter dataKey="velo_index" shape={<AlarmDot />} isAnimationActive={false} legendType="none" data={rows.filter((r) => r.velo_alarm)} />
          <Scatter dataKey="change_index" shape={<AlarmDot />} isAnimationActive={false} legendType="none" data={rows.filter((r) => r.change_alarm)} />
        </ComposedChart>
      </ResponsiveContainer>
      {!compact && (
        <div className="grid3">
          {Object.entries(FEATURE).map(([f, name]) => (
            <div key={f}>
              <h3>{name} · 띠는 평소 범위(예상 ± 2σ, 투구 수 반영)</h3>
              <ResponsiveContainer width="100%" height={150}>
                <ComposedChart data={rows} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
                  <CartesianGrid vertical={false} stroke="var(--line)" />
                  <XAxis dataKey="i" type="number" domain={[0.5, data.outings.length + 0.5]} hide />
                  <YAxis domain={["auto", "auto"]} tick={{ fontSize: 10 }} width={40} />
                  <Tooltip formatter={(v) => (Array.isArray(v) ? `${fmt.num(v[0])} ~ ${fmt.num(v[1])}` : fmt.num(v))} labelFormatter={(i) => `${i}번째 등판`} />
                  {baseline > 0 && <ReferenceArea x1={0.5} x2={baseline + 0.5} fill="var(--base)" fillOpacity={0.18} />}
                  <Area dataKey={`band_${f}`} stroke="none" fill="var(--velo)" fillOpacity={0.14} connectNulls isAnimationActive={false} />
                  <Line type="monotone" dataKey={f} stroke="var(--ink-2)" strokeWidth={1.5} dot={{ r: 2 }} isAnimationActive={false} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          ))}
        </div>
      )}
      {myAlerts.length > 0 && (
        <p className="note">
          이 투수의 경보 {myAlerts.filter((a) => a.date <= (rows.at(-1)?.date ?? "")).length}건:
          {" "}{myAlerts.filter((a) => a.date <= (rows.at(-1)?.date ?? "")).map((a) => (
            <button key={a.date + a.signal} className="pill" style={{ cursor: "pointer" }} onClick={() => setPicked({ ...a, who: data.name })}>
              {fmt.date(a.date)} {SIGNAL[a.signal === "velo_drop" ? "velo" : "change"].name}
            </button>
          ))}
        </p>
      )}
    </div>
  );
}

function IndexTip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const r = payload[0].payload;
  return (
    <div className="card" style={{ padding: "8px 10px", fontSize: 12 }}>
      <div><b>{r.i}번째 등판</b> {r.date} · 주력 패스트볼 {r.n_fb}구 · {r.phase === "baseline" ? "시작 구간" : "감시"}</div>
      {r.phase !== "baseline" && (
        <div>구속 하락 지수 {fmt.num(r.velo_index)} · 폼 변화 지수 {fmt.num(r.change_index)} {r.alarm_here ? "· 경보 (눌러서 카드 보기)" : ""}</div>
      )}
    </div>
  );
}

function AlertCard({ alert, onClose }) {
  const velo = alert.signal === "velo_drop";
  const feats = velo ? [] : Object.keys(FEATURE);
  const total = velo ? 0 : feats.reduce((s, f) => s + Math.max(0, alert.step[f]), 0);
  return (
    <div className={`card alert-card ${velo ? "velo" : ""}`}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h2 style={{ margin: 0 }}>경보 카드 · {alert.who} · {alert.date} · {velo ? "구속 하락 신호" : `폼 변화 신호 (${alert.rule})`}</h2>
        <button className="btn" onClick={onClose}>닫기</button>
      </div>
      <p style={{ fontSize: 15, margin: "6px 0 10px" }}>{alert.card}</p>
      {velo ? (
        <p className="note">구속 하락 지수 {fmt.num(alert.index)} (1을 넘으면 경보). 이 등판의 구속은 예상보다 {Math.abs(alert.velo_mph).toFixed(1)} mph {alert.velo_mph < 0 ? "낮았습니다" : "높았습니다"}.
          구속이 예상보다 낮은 흐름이 이어졌다는 뜻이며, 점검을 시작하라는 신호입니다.</p>
      ) : (
        <div>
          <p className="note">세 특징이 함께 평소와 달라졌습니다. 아래는 어떤 특징이 얼마나 벗어났는지(표준화 이탈, σ)와 T² 기여 몫입니다.</p>
          <table className="tbl">
            <thead><tr><th>특징</th><th>표준화 이탈</th><th>기여 몫</th><th></th></tr></thead>
            <tbody>
              {feats.map((f) => (
                <tr key={f}>
                  <td>{FEATURE[f]}</td>
                  <td>{alert.z[f] > 0 ? "+" : ""}{fmt.num(alert.z[f], 1)}σ</td>
                  <td>{fmt.num(alert.step[f], 1)}</td>
                  <td style={{ width: "40%" }}><div className="bar"><span style={{ width: `${total ? (100 * Math.max(0, alert.step[f])) / total : 0}%` }} /></div></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="note" style={{ marginBottom: 0 }}>관리도가 낸 점검 시작 신호입니다. 부상 여부의 판단은 사람이 합니다.</p>
    </div>
  );
}
