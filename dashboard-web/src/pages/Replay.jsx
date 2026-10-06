import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  Area, ComposedChart, Line, ReferenceArea, ReferenceLine, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis, CartesianGrid,
} from "recharts";
import { FEATURE, FEATURE_HELP, PART, PITCH_NAME, ROLE, fmt, useJson } from "../lib/data.js";
import { ChartTip, GRID, LABEL, TICK, TIP_STYLE } from "../lib/chart.jsx";

const SIGNAL = { velo: { name: "구속 하락 신호", color: "var(--velo)" }, change: { name: "폼 변화 신호", color: "var(--change)" } };
const GROUP_NAME = { case: "사례", control: "대조군", other: "그 밖의 투수" };
const SEASON_OPTIONS = ["all", 2025, 2024, 2023, 2022, 2021];
const KIND = { all: "전체", case: "사례(팔 부상 IL)", alarm: "경보가 있던 투수", control: "대조군" };

function who(p) {
  const tail = p.split === "dev" || p.season <= 2023 ? " · 개발셋(한계를 맞춘 시즌)" : "";
  if (p.group === "case") return `사례 · ${PART[p.part]} · IL ${p.il_date}${p.detected ? " · 신호 있음" : " · 신호 없음"}${tail}`;
  if (p.group === "control") return `대조군 · 가상 기준일 ${p.il_date}${tail}`;
  return (p.il_date ? `팔 부상 IL ${p.il_date} (사례 기준 미충족)` : "팔 부상 IL 없음") + tail;
}

function AlarmDot({ cx, cy, payload, onPick }) {
  if (!payload?.alarm_here || cx == null) return null;
  return (
    <g style={{ cursor: "pointer" }} onClick={(e) => { e.stopPropagation(); onPick?.(payload); }}>
      <circle cx={cx} cy={cy} r={12} fill="transparent" />
      <circle cx={cx} cy={cy} r={5.5} fill="var(--alarm)" stroke="#fff" strokeWidth={1.5} />
    </g>
  );
}

function baselineCountOf(data) {
  return data.outings.filter((o) => o.phase === "baseline").length;
}

// 등판 순서 축: 정수 눈금만 (1, 5, 10, … 처럼 보기 좋은 간격)
function outingTicks(n) {
  const step = n <= 12 ? 1 : n <= 30 ? 2 : n <= 60 ? 5 : 10;
  const ticks = [1];
  for (let k = step; k <= n; k += step) ticks.push(k);
  return ticks;
}

export default function Replay() {
  const { data: index } = useJson("pitchers.json");
  const { data: alerts } = useJson("alerts.json");
  const [query, setQuery] = useState("");
  const [season, setSeason] = useState("all");
  const [kind, setKind] = useState("all");
  const [open, setOpen] = useState(false);
  const [params, setParams] = useSearchParams();
  const id = params.get("p");
  const setId = (next) => setParams(next ? { p: next } : {}, { replace: false });
  const [shown, setShown] = useState(null);
  const [side, setSide] = useState(false);
  const [picked, setPicked] = useState(null);

  const sorted = useMemo(() => (index || []).slice().sort((a, b) => a.name.localeCompare(b.name) || b.season - a.season), [index]);
  useEffect(() => {
    if (sorted.length && (!id || !sorted.some((p) => p.id === id))) setParams({ p: (sorted.find((p) => p.group === "case" && p.detected) || sorted[0]).id }, { replace: true });
  }, [sorted, id]);
  const q = query.trim().toLowerCase();
  const matches = useMemo(() => sorted.filter((p) =>
    (season === "all" || p.season === Number(season)) &&
    (kind === "all" || (kind === "case" && p.group === "case") || (kind === "control" && p.group === "control") || (kind === "alarm" && (p.alarms_velo + p.alarms_change) > 0)) &&
    (!q || p.name.toLowerCase().includes(q) || p.name.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().includes(q))),
  [sorted, season, kind, q]);

  const entry = index?.find((p) => p.id === id);
  const partner = entry?.case_id != null ? index?.find((p) => p.case_id === entry.case_id && p.group !== entry.group && (entry.group === "case" ? p.group === "control" : p.group === "case")) : null;
  const { data: me } = useJson(id ? `replay/${id}.json` : null);
  const { data: other } = useJson(side && partner ? `replay/${partner.id}.json` : null);
  useEffect(() => { if (me) { setShown(me.outings.length); setPicked(null); } }, [me]);

  if (!index) return <div className="placeholder">투수 목록을 읽는 중…</div>;
  const baselineCount = me ? me.outings.filter((o) => o.phase === "baseline").length : 0;
  const counts = { all: index.length, case: index.filter((p) => p.group === "case").length, control: index.filter((p) => p.group === "control").length,
    alarm: index.filter((p) => p.alarms_velo + p.alarms_change > 0).length };
  return (
    <div className="page">
      <h1>리플레이 · 경보 카드</h1>
      <p className="lead">
        2021~2025 시즌에서 시작 구간을 채워 감시가 돌아간 <b>투수-시즌 {index.length.toLocaleString()}개</b>를 모두 찾아볼 수 있습니다. 2024~2025는 계획을 고정한 뒤 한 번 계산한 검증셋이고,
        2021~2023은 경보 한계를 맞추는 데 쓴 개발셋입니다(표시해 둠). 회색 띠는 평소를 잡는 시작 구간, 선은 두 신호의 지수(1을 넘으면 경보), 빨간 점은 경보,
        검은 세로선은 팔 부상 IL 등재(대조군은 짝지은 사례의 기준일)입니다. 경보 점이나 경보 칩을 누르면 카드가 열립니다.
      </p>
      <div className="toolbar search">
        <label className="search-box"><span>투수 검색</span>
          <input type="search" value={query} placeholder="이름 (예: Soroka, Skubal)" onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
            onFocus={() => setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 150)} aria-label="투수 이름 검색" />
        </label>
        <label><span>시즌</span>
          <select value={season} onChange={(e) => { setSeason(e.target.value); setOpen(true); }}>
            {SEASON_OPTIONS.map((s) => <option key={s} value={s}>{s === "all" ? "2021~2025 전체" : `${s}${s <= 2023 ? " (개발셋)" : " (검증셋)"}`}</option>)}
          </select>
        </label>
        <label><span>구분</span>
          <select value={kind} onChange={(e) => { setKind(e.target.value); setOpen(true); }}>
            {Object.entries(KIND).map(([k, v]) => <option key={k} value={k}>{v} ({counts[k].toLocaleString()})</option>)}
          </select>
        </label>
        <span className="caption" style={{ margin: 0 }}>검색 결과 {matches.length.toLocaleString()}명</span>
        {partner && <button className={`btn ${side ? "on" : ""}`} style={{ marginLeft: "auto" }} onClick={() => setSide(!side)}>{side ? "짝 닫기" : entry.group === "case" ? "대조군 나란히 보기" : "짝지은 사례 보기"}</button>}
        {open && (
          <ul className="results" role="listbox">
            {matches.slice(0, 40).map((p) => (
              <li key={p.id} role="option" aria-selected={p.id === id} className={p.id === id ? "on" : ""}
                onMouseDown={() => { setId(p.id); setQuery(""); setOpen(false); }}>
                <span className="who">{p.name} <small>{p.season} {ROLE[p.role]}{p.split === "dev" ? " · 개발셋" : ""}</small></span>
                <span className="tags">
                  {p.group === "case" && <span className={`light ${p.detected ? "alarm" : "base"}`}>{p.detected ? "사례 · 신호 있음" : "사례 · 신호 없음"}</span>}
                  {p.group === "control" && <span className="light base">대조군</span>}
                  {p.group === "other" && p.il_date && <span className="light warn">팔 부상 IL</span>}
                  {p.alarms_velo > 0 && <span className="light velo">구속 경보 {p.alarms_velo}</span>}
                  {p.alarms_change > 0 && <span className="light change">폼 경보 {p.alarms_change}</span>}
                </span>
              </li>
            ))}
            {matches.length === 0 && <li className="empty">일치하는 투수가 없습니다</li>}
            {matches.length > 40 && <li className="empty">{matches.length - 40}명 더 있음 — 이름을 더 입력하세요</li>}
          </ul>
        )}
      </div>
      {me && (
        <div className="toolbar" style={{ gap: 14 }}>
          <label><span>재생 위치</span>
            <input type="range" min={Math.max(1, baselineCount)} max={me.outings.length} value={shown ?? me.outings.length}
              onChange={(e) => setShown(Number(e.target.value))} aria-label="재생 위치" />
            <span className="range-value">{shown}/{me.outings.length} 등판</span>
          </label>
          <span className="caption" style={{ margin: 0 }}>슬라이더를 왼쪽으로 돌리면 그 등판까지만 보고, 경보가 언제 울렸는지 확인할 수 있습니다.</span>
        </div>
      )}
      {me && <Pitcher data={me} shown={shown ?? me.outings.length} alerts={alerts} setPicked={setPicked} />}
      {side && other && <Pitcher data={other} shown={other.outings.length} alerts={alerts} setPicked={setPicked} compact />}
      {picked && <AlertCard alert={picked} onClose={() => setPicked(null)} />}
    </div>
  );
}

function Pitcher({ data, shown, alerts, setPicked, compact }) {
  const n = data.outings.length;
  // IL 등재(기준일) 위치: 그 날짜 전 등판 수 + 0.5. 시즌 마지막 등판 뒤라면 축을 한 칸 늘려 오른쪽에 그린다.
  const before = data.il_date ? data.outings.filter((o) => o.date < data.il_date).length : null;
  const ilAt = before == null ? null : before + 0.5;
  const xMax = ilAt != null && ilAt > n ? n + 1.5 : n + 0.5;
  // 기준일 앞뒤로 선을 끊는다: 앞은 실선(_pre), 뒤는 점선(_post). 두 계열을 따로 그리면 기준일에서 이어지지 않는다.
  const split = (value, i) => (ilAt != null && i + 1 > ilAt ? [null, value] : [value, null]);
  const rows = data.outings.slice(0, shown).map((o, i) => {
    const [vp, vq] = split(o.velo_index, i), [cp, cq] = split(o.change_index, i);
    return {
      ...o, i: i + 1, alarm_here: o.velo_alarm || o.change_alarm,
      vidx_pre: vp, vidx_post: vq, cidx_pre: cp, cidx_post: cq,          // 지수 (특징 velo_pre와 이름이 겹치지 않게)
      ...Object.fromEntries(Object.keys(FEATURE).flatMap((f) => {
        const [a, b] = split(o[f], i);
        return [[`${f}_pre`, a], [`${f}_post`, b], [`band_${f}`, o.exp ? [o.exp[f] - 2 * o.sd[f], o.exp[f] + 2 * o.sd[f]] : null]];
      })),
    };
  });
  const afterIl = ilAt != null && ilAt < n;          // 기준일 뒤에도 등판이 있다
  const baseline = rows.filter((r) => r.phase === "baseline").length;
  const myAlerts = (alerts || []).filter((a) => a.id === data.id);
  const visibleAlerts = myAlerts.filter((a) => a.date <= (rows.at(-1)?.date ?? ""));
  const openAlert = (row) => {
    const hit = myAlerts.filter((a) => a.date === row.date);
    if (hit.length) setPicked({ ...hit[0], others: hit.slice(1), who: data.name, row });
  };
  const onClick = (state) => {
    const row = state?.activePayload?.[0]?.payload;
    if (!row) return;
    // 가리킨 등판에 경보가 없으면 바로 옆 등판(±1)의 경보를 연다 — 툴팁을 보고 누를 때 손이 조금 비껴가도 열리게
    const target = row.alarm_here ? row : rows.find((r) => r.alarm_here && Math.abs(r.i - row.i) <= 1);
    if (target) openAlert(target);
  };
  const yMax = Math.max(1.6, ...rows.flatMap((r) => [r.velo_index ?? 0, r.change_index ?? 0])) * 1.08;
  const ilLabel = data.group === "control" ? "기준일" : `IL 등재 ${fmt.date(data.il_date)}`;
  const ticks = outingTicks(n);
  const monitored = data.outings.filter((o) => o.phase === "monitor").length;
  const gaps = data.outings.slice(1).map((o, i) => ({ from: data.outings[i].date, to: o.date, days: Math.round((new Date(o.date) - new Date(data.outings[i].date)) / 86400000) }))
    .filter((g) => g.days > 30);
  const notes = [];
  if (monitored <= 3) notes.push(`감시 등판이 ${monitored}개뿐입니다. 시작 구간(${ROLE[data.role]} ${baselineCountOf(data)}등판)을 ${fmt.date(data.baseline_end)}에야 채웠고, 그 뒤 등판에서만 지수가 계산됩니다.`);
  if (gaps.length) notes.push(`등판 공백 ${gaps.map((g) => `${fmt.date(g.from)}→${fmt.date(g.to)} ${g.days}일`).join(", ")}: 긴 공백 뒤의 등판도 같은 '평소'와 비교하므로 복귀 직후에는 폼 변화 신호가 울리기 쉽습니다.`);
  const dateOf = (i) => fmt.date(data.outings[i - 1]?.date);
  // 띠·선의 글자는 첫 차트(지수)에만 적는다. 특징 차트는 선이 띠 안을 지나가 글자와 겹친다.
  const common = (withText) => (
    <>
      <CartesianGrid vertical={false} stroke={GRID} />
      {baseline > 0 && <ReferenceArea x1={0.5} x2={baseline + 0.5} fill="var(--base)" fillOpacity={0.12}
        label={withText ? { value: `시작 구간 · 평소를 배우는 첫 ${baseline}등판`, position: "insideBottom", ...LABEL, fill: "var(--muted)", dy: -6 } : undefined} />}
      {afterIl && <ReferenceArea x1={ilAt} x2={xMax} fill="var(--alarm)" fillOpacity={0.045}
        label={withText ? { value: data.group === "control" ? "기준일 뒤" : "IL 등재 뒤 (복귀 등판)", position: "insideBottom", ...LABEL, fill: "var(--alarm)", dy: -6 } : undefined} />}
      {ilAt != null && <ReferenceLine x={ilAt} stroke="var(--ink)" strokeWidth={1.2}
        label={withText ? { value: ilLabel, position: ilAt > n * 0.8 ? "insideTopRight" : "insideTopLeft", ...LABEL, dy: -2 } : undefined} />}
    </>
  );
  const xAxis = (hideLabel) => (
    <XAxis dataKey="i" type="number" domain={[0.5, xMax]} ticks={ticks} tickFormatter={dateOf} interval="preserveStartEnd" minTickGap={28} tick={TICK} axisLine={{ stroke: GRID }} tickLine={false}
      label={hideLabel ? undefined : { value: "등판 (날짜순, 간격은 등판 순서)", position: "bottom", offset: 2, ...LABEL }} />
  );
  return (
    <div className="card">
      <div className="card-head">
        <h2>{data.name} <span style={{ color: "var(--muted)", fontWeight: 500 }}>· {data.season} {ROLE[data.role]} · {who(data)}</span></h2>
        <div className="legend">
          <span><i style={{ background: "var(--velo)" }} />구속 하락 지수</span>
          <span><i style={{ background: "var(--change)" }} />폼 변화 지수</span>
          <span><i className="dot" style={{ background: "var(--alarm)" }} />경보 (지수 &gt; 1)</span>
          <span><i className="dash" />경보 한계 1</span>
          <span><i className="band" style={{ background: "var(--base-bg)", border: "1px solid var(--line-2)" }} />시작 구간</span>
          <span><i style={{ background: "var(--ink)" }} />IL 등재(기준일)</span>
        </div>
      </div>
      {visibleAlerts.length > 0 ? (
        <p className="chips">
          <span className="caption" style={{ margin: 0 }}>경보 {visibleAlerts.length}건 — 누르면 카드가 열립니다:</span>
          {visibleAlerts.map((a) => {
            const s = SIGNAL[a.signal === "velo_drop" ? "velo" : "change"];
            return (
              <button key={a.date + a.signal} className="pill" onClick={() => setPicked({ ...a, who: data.name })}>
                <span className="dot" style={{ background: s.color }} />{fmt.date(a.date)} {s.name}
              </button>
            );
          })}
        </p>
      ) : rows.some((r) => r.phase === "monitor") ? <p className="caption">여기까지 경보가 없습니다.</p> : null}
      {notes.length > 0 && <p className="notice">{notes.join(" ")}</p>}
      <h3 className="chart-title">신호 지수 <small>1을 넘으면 경보 · 경보 뒤에는 0에서 다시 시작</small></h3>
      <ResponsiveContainer width="100%" height={compact ? 220 : 250}>
        <ComposedChart data={rows} onClick={onClick} margin={{ top: 14, right: 16, left: 0, bottom: compact ? 16 : 4 }}>
          {common(true)}
          {xAxis(!compact)}
          <YAxis domain={[Math.floor(Math.min(-0.5, ...rows.map((r) => r.velo_index ?? 0)) * 2) / 2, Math.ceil(yMax * 2) / 2]} tickFormatter={(v) => v.toFixed(1)}
            tickCount={6} tick={TICK} width={40} axisLine={false} tickLine={false} />
          <Tooltip content={<ChartTip render={(payload, label) => <IndexTip r={rows[Math.round(label) - 1] || payload[0].payload} />} />} cursor={{ stroke: "var(--line-2)" }} />
          <ReferenceLine y={1} stroke="var(--alarm)" strokeDasharray="4 4" />
          <ReferenceLine y={0} stroke="var(--line-2)" />
          <Line type="monotone" dataKey="vidx_pre" stroke="var(--velo)" dot={{ r: 2, strokeWidth: 0, fill: "var(--velo)" }} strokeWidth={2.2} connectNulls name="구속 하락 지수" isAnimationActive={false} />
          <Line type="monotone" dataKey="cidx_pre" stroke="var(--change)" dot={{ r: 2, strokeWidth: 0, fill: "var(--change)" }} strokeWidth={1.8} connectNulls name="폼 변화 지수" isAnimationActive={false} />
          {afterIl && <Line type="monotone" dataKey="vidx_post" stroke="var(--velo)" strokeOpacity={0.55} strokeDasharray="4 3" dot={{ r: 2, strokeWidth: 0, fill: "var(--velo)", fillOpacity: 0.55 }} strokeWidth={2} connectNulls name="구속 하락 지수 (IL 뒤)" isAnimationActive={false} />}
          {afterIl && <Line type="monotone" dataKey="cidx_post" stroke="var(--change)" strokeOpacity={0.55} strokeDasharray="4 3" dot={{ r: 2, strokeWidth: 0, fill: "var(--change)", fillOpacity: 0.55 }} strokeWidth={1.6} connectNulls name="폼 변화 지수 (IL 뒤)" isAnimationActive={false} />}
          <Scatter dataKey="velo_index" shape={<AlarmDot onPick={openAlert} />} isAnimationActive={false} legendType="none" tooltipType="none" data={rows.filter((r) => r.velo_alarm)} />
          <Scatter dataKey="change_index" shape={<AlarmDot onPick={openAlert} />} isAnimationActive={false} legendType="none" tooltipType="none" data={rows.filter((r) => r.change_alarm)} />
        </ComposedChart>
      </ResponsiveContainer>
      {!compact && Object.entries(FEATURE).map(([f, name], k, arr) => (
        <div key={f}>
          <h3 className="chart-title">{name} <small>{FEATURE_HELP[f]} 파란 띠는 평소 범위(예상 ± 2σ, 투구 수 반영).</small></h3>
          <ResponsiveContainer width="100%" height={k === arr.length - 1 ? 230 : 210}>
            <ComposedChart data={rows} onClick={onClick} margin={{ top: 14, right: 16, left: 0, bottom: k === arr.length - 1 ? 16 : 4 }}>
              {common(false)}
              {xAxis(k !== arr.length - 1)}
              <YAxis domain={["auto", "auto"]} tick={TICK} width={40} axisLine={false} tickLine={false} tickFormatter={(v) => fmt.num(v, f === "rel_z" ? 2 : 1)} />
              <Tooltip content={<ChartTip render={(payload, label) => <FeatureTip r={rows[Math.round(label) - 1] || payload[0].payload} f={f} name={name} />} />} cursor={{ stroke: "var(--line-2)" }} />
              <Area dataKey={`band_${f}`} stroke="none" fill="var(--velo)" fillOpacity={0.14} connectNulls isAnimationActive={false} name="평소 범위" />
              <Line type="monotone" dataKey={`${f}_pre`} stroke="var(--ink-2)" strokeWidth={1.6} dot={{ r: 2.5, strokeWidth: 1 }} connectNulls isAnimationActive={false} name={name} />
              {afterIl && <Line type="monotone" dataKey={`${f}_post`} stroke="var(--ink-2)" strokeOpacity={0.5} strokeDasharray="4 3" strokeWidth={1.4} dot={{ r: 2.5, strokeWidth: 1, strokeOpacity: 0.6 }} connectNulls isAnimationActive={false} name={`${name} (IL 뒤)`} />}
              <Scatter dataKey={f} name={name} shape={<AlarmDot onPick={openAlert} />} isAnimationActive={false} legendType="none" tooltipType="none" data={rows.filter((r) => r.alarm_here)} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      ))}
    </div>
  );
}

function pitches(r) {
  return `${PITCH_NAME[r.fb] || r.fb || "패스트볼"} ${r.n_fb}구 / 전체 ${r.n_all ?? "—"}구`;
}

function FeatureTip({ r, f, name }) {
  const band = r[`band_${f}`];
  const digits = f === "rel_z" ? 2 : 1;
  return (
    <>
      <div><b>{r.date}</b> · {r.i}번째 등판 · {pitches(r)} · {r.phase === "baseline" ? "시작 구간" : "감시"}</div>
      <div>{name}: <b>{fmt.num(r[f], digits)}</b>{band && <> · 평소 범위 {fmt.num(band[0], digits)} ~ {fmt.num(band[1], digits)} (예상 {fmt.num(r.exp[f], digits)})</>}</div>
      {r.alarm_here && <div className="alarm">이 등판에서 경보 — 빨간 점을 누르면 카드가 열립니다</div>}
    </>
  );
}

function IndexTip({ r }) {
  return (
    <>
      <div><b>{r.date}</b> · {r.i}번째 등판 · {pitches(r)} · {r.phase === "baseline" ? "시작 구간" : "감시"}</div>
      {r.phase !== "baseline" && (
        <div>구속 하락 지수 {fmt.num(r.velo_index)} · 폼 변화 지수 {fmt.num(r.change_index)} {r.alarm_here && <span className="alarm">· 경보 — 빨간 점을 누르면 카드가 열립니다</span>}</div>
      )}
    </>
  );
}

function AlertCard({ alert, onClose }) {
  const velo = alert.signal === "velo_drop";
  const feats = velo ? [] : Object.keys(FEATURE);
  const total = velo ? 0 : feats.reduce((s, f) => s + Math.max(0, alert.step[f]), 0);
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="modal-back" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
    <div className={`card alert-card modal ${velo ? "velo" : ""}`} role="dialog" aria-modal="true" aria-label="경보 카드">
      <div className="card-head">
        <h2>경보 카드 · {alert.who} · {alert.date} · {velo ? "구속 하락 신호" : `폼 변화 신호 (${alert.rule})`}</h2>
        <button className="btn" onClick={onClose}>닫기</button>
      </div>
      <p className="headline">{alert.card}</p>
      {velo ? (
        <p className="note" style={{ margin: 0 }}>구속 하락 지수 {fmt.num(alert.index)} (1을 넘으면 경보). 이 등판의 구속은 예상보다 {Math.abs(alert.velo_mph).toFixed(1)} mph {alert.velo_mph < 0 ? "낮았습니다" : "높았습니다"}.
          구속이 예상보다 낮은 흐름이 이어졌다는 뜻이며, 점검을 시작하라는 신호입니다.</p>
      ) : (
        <div>
          <p className="note" style={{ margin: "0 0 8px" }}>세 특징이 함께 평소와 달라졌습니다. 아래는 어떤 특징이 얼마나 벗어났는지(표준화 이탈, σ)와 T² 기여 몫입니다.</p>
          <div className="tbl-wrap">
            <table className="tbl">
              <thead><tr><th>특징</th><th className="num">표준화 이탈</th><th className="num">기여 몫</th><th style={{ width: "40%" }}></th></tr></thead>
              <tbody>
                {feats.map((f) => (
                  <tr key={f}>
                    <td>{FEATURE[f]}</td>
                    <td className="num">{alert.z[f] > 0 ? "+" : ""}{fmt.num(alert.z[f], 1)}σ</td>
                    <td className="num">{fmt.num(alert.step[f], 1)}</td>
                    <td><div className="bar"><span style={{ width: `${total ? (100 * Math.max(0, alert.step[f])) / total : 0}%` }} /></div></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      <p className="note">관리도가 낸 점검 시작 신호입니다. 부상 여부의 판단은 사람이 합니다.</p>
    </div>
    </div>
  );
}
