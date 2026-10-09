import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis } from "recharts";
import { PITCH_NAME, ROLE, fmt, useJson } from "../lib/data.js";
import { ChartTip, GRID, LABEL, TICK } from "../lib/chart.jsx";
import { analyze, parseInput } from "../lib/engine.js";
import { AlertCard, MultiplierControl, Pitcher } from "./Replay.jsx";

const PART = { elbow: "팔꿈치", shoulder: "어깨", hamstring: "햄스트링", other: "다른 부위", unknown: "부위 미상" };
const ARM = new Set(["elbow", "shoulder"]);
const STATUS = { new: "2026 신규", replacement: "2026 대체 영입", resigned: "재계약" };
const LEAGUE_COLOR = { MLB: "var(--ink)", AAA: "#8e6bbf" };
const EXAMPLE = `날짜,직구 평균구속(km/h),직구 수,전체 투구 수
2026-04-03,149.2,55,98
2026-04-09,148.7,60,101
2026-04-15,150.1,52,95
2026-04-21,149.5,58,104
2026-04-27,148.9,49,90
2026-05-03,149.8,61,99
2026-05-09,149.0,54,97
2026-05-15,148.4,57,102
2026-05-21,147.9,50,93
2026-05-27,147.1,53,96
2026-06-02,146.6,48,88
2026-06-08,146.0,51,94`;
const STORE = "ps-manual-input";

function load() {
  try { return JSON.parse(localStorage.getItem(STORE)) || null; } catch { return null; }
}

function AlarmDot({ cx, cy, payload }) {
  if (!payload?.alarm || cx == null || cy == null) return null;
  return <circle cx={cx} cy={cy} r={4.5} fill="var(--alarm)" stroke="#fff" strokeWidth={1.2} />;
}

// 여러 시즌의 등판 구속을 한 줄로: 시즌 사이는 끊고, 리그별 색, 경보 점, IL 세로선
function CareerChart({ pitcher }) {
  const rows = pitcher.timeline.map((t, i) => ({ ...t, i: i + 1, [`velo_${t.league}_${t.season}`]: t.velo, alarm_y: t.alarm ? t.velo : null }));   // 경보 점은 별도 data 없이 열로 (툴팁이 모든 등판에 뜨게)
  const seriesKeys = [...new Set(pitcher.timeline.map((t) => `velo_${t.league}_${t.season}`))];
  const starts = [];
  pitcher.timeline.forEach((t, i) => { if (i === 0 || t.season !== pitcher.timeline[i - 1].season || t.league !== pitcher.timeline[i - 1].league) starts.push({ i: i + 1, label: `${t.league} ${t.season}` }); });
  const ilMarks = pitcher.il.map((il) => ({ ...il, i: rows.filter((r) => r.date < il.date).length + 0.5 }));
  if (!rows.length) return null;
  return (
    <ResponsiveContainer width="100%" height={200}>
      <ComposedChart data={rows} margin={{ top: 18, right: 12, left: 0, bottom: 4 }}>
        <CartesianGrid vertical={false} stroke={GRID} />
        <XAxis dataKey="i" type="number" domain={[0.5, rows.length + 0.5]} ticks={starts.map((s) => s.i)} tickFormatter={(i) => starts.find((s) => s.i === i)?.label ?? ""} tick={TICK} axisLine={{ stroke: GRID }} tickLine={false} />
        <YAxis domain={["auto", "auto"]} allowDecimals={false} tickFormatter={(v) => v.toFixed(0)} tick={TICK} width={34} axisLine={false} tickLine={false} />
        <Tooltip content={<ChartTip render={(payload, label) => { const r = rows[Math.round(label) - 1]; return r ? <><div><b>{r.date}</b> · {r.league} {r.season} · {r.phase === "baseline" ? "시작 구간" : "감시"}</div><div>평균 구속 {fmt.num(r.velo, 1)} mph{r.velo_index != null && <> · 구속 하락 지수 {fmt.num(r.velo_index)}</>}{r.alarm && <span className="alarm"> · 경보</span>}</div></> : null; }} />} cursor={{ stroke: "var(--line-2)" }} />
        {starts.slice(1).map((s) => <ReferenceLine key={s.i} x={s.i - 0.5} stroke="var(--line-2)" />)}
        {ilMarks.map((il) => <ReferenceLine key={il.date} x={il.i} stroke={ARM.has(il.part) ? "var(--alarm)" : "var(--base)"} strokeWidth={1.2} strokeDasharray={ARM.has(il.part) ? undefined : "4 3"} label={{ value: `IL ${fmt.date(il.date)} ${PART[il.part] || il.part}`, position: "insideTopLeft", ...LABEL, fill: ARM.has(il.part) ? "var(--alarm)" : "var(--muted)" }} />)}
        {seriesKeys.map((k) => <Line key={k} type="monotone" dataKey={k} stroke={LEAGUE_COLOR[k.split("_")[1]]} strokeWidth={1.6} dot={{ r: 2, strokeWidth: 0, fill: LEAGUE_COLOR[k.split("_")[1]] }} connectNulls={false} isAnimationActive={false} />)}
        <Scatter dataKey="alarm_y" shape={<AlarmDot />} isAnimationActive={false} legendType="none" tooltipType="none" />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

function ScoutCard({ p }) {
  const has = p.seasons.length > 0;
  return (
    <div className="card scout">
      <div className="card-head">
        <h2>{p.name_ko} <span style={{ color: "var(--muted)", fontWeight: 500 }}>{p.name} · {p.team}</span></h2>
        <span className={`light ${p.status === "resigned" ? "base" : p.status === "replacement" ? "warn" : "ok"}`}>{STATUS[p.status]}</span>
      </div>
      {!has && <p className="caption" style={{ margin: 0 }}>2021년 이후 MLB·2023년 이후 트리플A 추적 기록이 없습니다(더블A 이하·독립리그·NPB·KBO 기록은 공개 추적 자료가 없음).</p>}
      {has && (
        <>
          <div className="legend" style={{ marginBottom: 2 }}>
            <span><i style={{ background: LEAGUE_COLOR.MLB }} />MLB 등판 평균 구속</span>
            <span><i style={{ background: LEAGUE_COLOR.AAA }} />트리플A (구장 보정 없음 · 참고용)</span>
            <span><i className="dot" style={{ background: "var(--alarm)" }} />경보</span>
            <span><i style={{ background: "var(--alarm)" }} />팔 부상 IL (MLB 거래 기록, 수기 검토)</span>
            <span><i className="dash" style={{ borderColor: "var(--base)" }} />IL 등재 · 부위 미상 (트리플A 거래 기록)</span>
          </div>
          <CareerChart pitcher={p} />
          <div className="tbl-wrap" style={{ marginTop: 6 }}>
            <table className="tbl">
              <thead><tr><th>시즌</th><th>역할 · 주력</th><th className="num">등판 / 감시</th><th className="num">시작 구간 구속</th><th className="num">마지막 5등판</th><th className="num">변화</th><th className="num">경보 (구속/폼)</th><th>IL 등재</th><th></th></tr></thead>
              <tbody>
                {p.seasons.map((s) => (
                  <tr key={`${s.league}${s.season}`}>
                    <td><span className="pill" style={{ margin: 0 }}><span className="dot" style={{ background: LEAGUE_COLOR[s.league] }} />{s.league} {s.season}</span></td>
                    <td>{ROLE[s.role]} · {PITCH_NAME[s.fb] || s.fb || "—"}</td>
                    <td className="num">{s.outings} / {s.monitored}{s.monitored === 0 && <span style={{ color: "var(--muted)" }}> (시작 구간 못 채움)</span>}</td>
                    <td className="num">{fmt.num(s.velo_start, 1)}</td>
                    <td className="num">{fmt.num(s.velo_last5, 1)}</td>
                    <td className="num" style={{ color: s.velo_change != null && s.velo_change <= -1 ? "var(--alarm)" : "inherit" }}>{s.velo_change == null ? "—" : `${s.velo_change > 0 ? "+" : ""}${fmt.num(s.velo_change, 1)}`}</td>
                    <td className="num">{s.alarms_velo} / {s.alarms_change}</td>
                    <td>{s.il ? <span className={`light ${ARM.has(s.il.part) ? "alarm" : "base"}`} title={s.il.reason || undefined}>{fmt.date(s.il.date)} {PART[s.il.part] || s.il.part}{s.il.count > 1 && ` · ${s.il.count}회`}</span> : <span style={{ color: "var(--muted)" }}>없음</span>}</td>
                    <td>{s.replay && <Link to={`/?p=${s.replay}`}>리플레이 →</Link>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

export default function Kbo() {
  const { data } = useJson("kbo_case.json");
  const { data: scout } = useJson("scout.json");
  const { data: params } = useJson("engine_params.json");
  const [team, setTeam] = useState("all");
  const [onlyData, setOnlyData] = useState(true);
  const saved = useMemo(load, []);
  const [name, setName] = useState(saved?.name ?? "");
  const [role, setRole] = useState(saved?.role ?? "SP");
  const [unit, setUnit] = useState(saved?.unit ?? "km/h");
  const [text, setText] = useState(saved?.text ?? "");
  const [season, setSeason] = useState(saved?.season ?? new Date().getFullYear());
  const [result, setResult] = useState(null);
  const [problems, setProblems] = useState([]);
  const [picked, setPicked] = useState(null);
  const [mult, setMult] = useState(1);
  useEffect(() => { if (result) run(); }, [mult]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { try { localStorage.setItem(STORE, JSON.stringify({ name, role, unit, text, season })); } catch { /* 저장 못 해도 동작엔 지장 없음 */ } }, [name, role, unit, text, season]);

  const run = () => {
    if (!params) return;
    const { rows, problems: bad } = parseInput(text, Number(season));
    setProblems(bad);
    if (rows.length < 3) { setResult(null); setProblems([...bad, "등판이 3개 이상 있어야 합니다."]); return; }
    const out = analyze(rows, role, params.roles, params.rules, unit, mult);
    const label = name.trim() || "직접 입력한 투수";
    setResult({
      data: { id: "manual", manual: true, name: label, season: Number(season), role, group: "other", il_date: null,
              baseline_end: out.outings[out.nStart - 1]?.date ?? null, outings: out.outings, limits: {} },
      alerts: out.alerts.map((a) => ({ ...a, id: "manual", who: label, unit, velo_delta: a.velo, rule: "EWMA" })),
      monitored: out.monitored, nStart: out.nStart,
    });
    setPicked(null);
  };

  if (!data || !scout) return <div className="placeholder">KBO 화면 자료를 읽는 중…</div>;
  const teams = [...new Set(scout.pitchers.map((p) => p.team))];
  const shown = scout.pitchers.filter((p) => (team === "all" || p.team === team) && (!onlyData || p.seasons.length > 0));
  const withData = scout.pitchers.filter((p) => p.seasons.length > 0).length;
  return (
    <div className="page">
      <h1>KBO · 외국인 투수 영입 전 점검</h1>
      <p className="lead">
        KBO 구단은 해마다 외국인 투수를 MLB·트리플A에서 데려옵니다. 그 선수들의 지난 시즌은 공개 추적 기록(MLB 2021~2026, 트리플A 2023~2025)에 남아 있어, 영입 전에 같은 엔진으로
        '평소와 달라진 흐름이 있었는지'를 볼 수 있습니다. 2026년 KBO 외국인 투수 {scout.pitchers.length}명 중 <b>{withData}명</b>의 기록을 돌렸습니다.
        트리플A는 구장 보정 없이, 한계값은 MLB 개발셋 값을 그대로 쓴 <b>참고용</b>입니다. IL 등재는 MLB(거래 기록 + 수기 검토로 팔꿈치·어깨만)와 트리플A(거래 기록 자동 추출, 사유 문구가 거의 없어 대부분 '부위 미상') 공개 기록에서 가져왔고, KBO 시즌의 부상은 표시되지 않습니다.
      </p>
      <div className="toolbar">
        <label><span>구단</span>
          <select value={team} onChange={(e) => setTeam(e.target.value)}><option value="all">전체</option>{teams.map((t) => <option key={t}>{t}</option>)}</select>
        </label>
        <button className={`btn ${onlyData ? "on" : ""}`} onClick={() => setOnlyData(!onlyData)}>{onlyData ? "기록 있는 투수만" : "전체 보기"}</button>
        <span className="caption" style={{ margin: 0 }}>{shown.length}명 · 표의 '리플레이 →'를 누르면 그 시즌의 네 그래프를 봅니다</span>
      </div>
      {shown.map((p) => <ScoutCard key={p.name} p={p} />)}
      <div className="card">
        <h2>2026 시즌 중 부상 대응 사례 <span style={{ color: "var(--muted)", fontWeight: 500 }}>· 날짜는 공개 기록</span></h2>
        <div className="kpi">
          {data.pitchers.map((p) => (
            <div key={p.name}>
              <div className="v" style={{ fontSize: 18 }}>{p.name} <span style={{ color: "var(--muted)", fontWeight: 500, fontSize: 13 }}>{p.team} · {PART[p.part] || p.part}</span></div>
              <div className="l">말소 {p.removed} → 결정 {p.decision} ({p.decision_type}) · <b>{Math.round((new Date(p.decision) - new Date(p.removed)) / 86400000)}일</b><br />대체 {p.replacement} · {p.outcome}</div>
            </div>
          ))}
        </div>
        {data.response_only.map((x) => (
          <p key={x.name} className="note" style={{ margin: "4px 0" }}>
            <b>{x.name}</b> ({x.team}) · {PART[x.part] || x.part} · 말소 {x.removed} → 결정 {x.decision} ({x.decision_type}) · 대체 {x.replacement} · {x.outcome}. {x.note}
          </p>
        ))}
      </div>
      <div className="card">
        <div className="card-head">
          <h2>직접 입력 <span style={{ color: "var(--muted)", fontWeight: 500 }}>· 공개 추적 기록이 없는 투수(KBO 시즌, 고교 측정기)용 간이 분석</span></h2>
          <div className="row" style={{ margin: 0 }}>
            <div className="seg" role="group" aria-label="역할">
              {[["SP", "선발"], ["RP", "불펜"]].map(([k, v]) => <button key={k} className={`btn ${role === k ? "on" : ""}`} onClick={() => setRole(k)}>{v}</button>)}
            </div>
            <div className="seg" role="group" aria-label="단위">
              {["km/h", "mph"].map((u) => <button key={u} className={`btn ${unit === u ? "on" : ""}`} onClick={() => setUnit(u)}>{u}</button>)}
            </div>
          </div>
        </div>
        <div className="row" style={{ marginBottom: 8 }}>
          <label className="toolbar-label"><span>이름(표시용)</span> <input className="text" value={name} placeholder="예: 투수 A" onChange={(e) => setName(e.target.value)} /></label>
          <label className="toolbar-label"><span>시즌</span> <input className="text" style={{ width: 80 }} value={season} onChange={(e) => setSeason(e.target.value)} /></label>
        </div>
        <textarea className="paste" rows={7} value={text} onChange={(e) => setText(e.target.value)} spellCheck={false}
          placeholder={"한 줄에 한 등판: 날짜, 직구 평균 구속, 직구 투구 수[, 전체 투구 수]\n" + EXAMPLE.split("\n").slice(0, 4).join("\n") + "\n…"} />
        <div className="row" style={{ marginTop: 10, marginBottom: 4 }}>
          <button className="btn on" onClick={run} disabled={!params}>분석</button>
          <button className="btn" onClick={() => setText(EXAMPLE)}>예시 넣기</button>
          <button className="btn" onClick={() => { setText(""); setResult(null); setProblems([]); }}>지우기</button>
          <span className="caption" style={{ margin: 0 }}>쉼표·탭·공백 구분 모두 됩니다. 머리글 줄은 건너뜁니다. 날짜는 2026-04-03, 2026.04.03, 4/3 형식.</span>
        </div>
        {problems.length > 0 && <ul className="problems">{problems.map((p) => <li key={p}>{p}</li>)}</ul>}
        <p className="notice" style={{ marginTop: 10 }}>
          <b>간이 분석(참고용)입니다.</b> ① 경기 평균만 있으므로 투구별 흔들림, 평소가 움직이는 크기, 경보 한계(선발 {params?.roles.SP.k} · 불펜 {params?.roles.RP.k})는
          MLB 개발셋에서 추정한 값을 빌려 씁니다 — <b>'정상이면 100등판에 1회'라는 오경보 보장은 MLB에서만 검증된 것</b>이고 KBO에서는 확인되지 않았습니다.
          ② 폼 변화 신호(릴리스 높이·팔 각도)는 공개 자료가 없어 그리지 않습니다. ③ 이미 다친 선수를 골라 넣는 사후 입력은 사례 연구이지 탐지 성능의 근거가 아닙니다.
        </p>
        {result && (
          <>
            <div className="toolbar"><MultiplierControl value={mult} onChange={setMult} /></div>
            <p className="caption">등판 {result.data.outings.length}개 중 시작 구간 {result.nStart}개, 감시 {result.monitored}개 · 경보 {result.alerts.length}건. 시작 구간은 {role === "SP" ? "선발 첫 8등판" : "불펜 첫 15등판과 직구 120구 중 늦은 시점"}입니다.{mult !== 1 && ` 한계 배수 ${mult.toFixed(2)} (설계점 1.0이 아닌 조정값).`}</p>
            <Pitcher data={result.data} shown={result.data.outings.length} alerts={result.alerts} setPicked={setPicked} features={["velo"]} signals={["velo"]} unit={unit} />
          </>
        )}
      </div>
      {picked && <AlertCard alert={picked} onClose={() => setPicked(null)} />}
      <p className="note">한계: 영입 전 점검은 공개 기록이 있는 선수에게만 가능하고, 트리플A 결과는 참고용입니다. KBO 시즌 자체의 추적 기록은 공개돼 있지 않습니다.</p>
    </div>
  );
}
