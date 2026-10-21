import { useEffect, useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Bar, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis } from "recharts";
import { fmt, useJson } from "../lib/data.js";
import { ChartTip, GRID, LABEL, TICK, limitLabel } from "../lib/chart.jsx";
import { addDays, cautionReasons, dateRange, dayState, displayFlags, loadStatus } from "../lib/load.js";

const TEAM_KO = { ATH: "애슬레틱스", OAK: "오클랜드", ATL: "애틀랜타", AZ: "애리조나", BAL: "볼티모어", BOS: "보스턴", CHC: "시카고 컵스", CIN: "신시내티", CLE: "클리블랜드", COL: "콜로라도",
  CWS: "시카고 화이트삭스", DET: "디트로이트", HOU: "휴스턴", KC: "캔자스시티", LAA: "LA 에인절스", LAD: "LA 다저스", MIA: "마이애미", MIL: "밀워키", MIN: "미네소타", NYM: "뉴욕 메츠",
  NYY: "뉴욕 양키스", PHI: "필라델피아", PIT: "피츠버그", SD: "샌디에이고", SEA: "시애틀", SF: "샌프란시스코", STL: "세인트루이스", TB: "탬파베이", TEX: "텍사스", TOR: "토론토", WSH: "워싱턴" };
// 표시 기준을 현장 말로 (2026-10-16: ACWR 같은 용어를 화면에서 뺌). 1주/평소 비율은 '주의' 1.5배로만 (2026-10-21, load.displayFlags)
const FLAG_NAME = { consecutive: "3일 연속 등판", apps_3d: "3일 동안 3번 등판", p7d: "최근 7일 투구가 본인 평소보다 많음", long_short: "30구 이상 던지고 하루 이하 쉬고 등판" };
const reasons = (st) => [...displayFlags(st).map((f) => ({ t: FLAG_NAME[f], cls: "alarm" })), ...cautionReasons(st).map((t) => ({ t, cls: "warn" }))];
const STATUS_CLASS = { "평소": "ok", "주의": "warn", "표시": "alarm" };
const STATUS_ORDER = { "표시": 0, "주의": 1, "평소": 2 };
const SIGNAL_NAME = { velo: "구속 하락", change: "폼 변화" };
const PART = { elbow: "팔꿈치", shoulder: "어깨" };
const WINDOW = 14;                                            // 달력 칸 수(기준일 포함 지난 14일)
const ACTIVE_DAYS = 30;                                       // 이보다 오래 등판이 없으면(IL 등재 중이 아니면) 표 아래 접힌 줄로 내린다

function Mark({ cx, cy, payload }) {
  if (cx == null || !payload?.signals?.length) return null;
  return <circle cx={cx} cy={cy} r={5} fill="var(--alarm)" stroke="#fff" strokeWidth={1.5} />;
}

export default function Bullpen() {
  const { data: index } = useJson("teams.json");
  const [params, setParams] = useSearchParams();
  const seasons = useMemo(() => (index ? [...new Set(index.teams.map((t) => t.season))].sort((a, b) => b - a) : []), [index]);
  const season = Number(params.get("s")) || seasons[0];
  const teams = useMemo(() => (index ? index.teams.filter((t) => t.season === season).sort((a, b) => (TEAM_KO[a.team] || a.team).localeCompare(TEAM_KO[b.team] || b.team, "ko")) : []), [index, season]);
  const team = teams.find((t) => t.team === params.get("t"))?.team || teams.find((t) => t.team === "LAD")?.team || teams[0]?.team;
  const { data } = useJson(team && season ? `teams/${team}_${season}.json` : null);
  const dates = data?.dates || [];
  const date = dates.includes(params.get("d")) ? params.get("d") : dates[dates.length - 1];
  const set = (next) => setParams({ t: team, s: String(season), d: date, ...next }, { replace: true });
  const pid = params.get("p");
  useEffect(() => { if (data && pid && !data.pitchers.some((p) => p.id === pid)) set({ p: undefined }); }, [data]);   // eslint-disable-line react-hooks/exhaustive-deps

  const board = useMemo(() => {
    if (!data || !date) return [];
    const from = addDays(date, -(WINDOW - 1));
    return data.pitchers
      .filter((p) => {
        const here = p.outings.filter((o) => o.here && o.date <= date).map((o) => o.date);             // 기준일까지 이 팀에서 던진 등판
        return here.length > 0 && !p.outings.some((o) => !o.here && o.date > here.at(-1) && o.date <= date);   // 그 뒤 다른 팀에서 던졌으면 떠난 것
      })
      .map((p) => {
        const st = dayState(p.outings, date, index.rules, p.p7d_limit, p.p7d_from);
        const recent = p.outings.filter((o) => o.date >= from && o.date <= date);
        const alarms = recent.filter((o) => o.signals.length);
        const onIl = p.il && p.il.date <= date && !p.outings.some((o) => o.date > p.il.date && o.date <= date);
        return { p, st, status: loadStatus(st), recent, alarms, onIl };
      })
      .sort((a, b) => STATUS_ORDER[a.status] - STATUS_ORDER[b.status] || b.st.p7d - a.st.p7d || (a.st.daysSince ?? 999) - (b.st.daysSince ?? 999) || a.p.name.localeCompare(b.p.name));
  }, [data, date, index]);
  const active = board.filter((r) => r.onIl || (r.st.daysSince != null && r.st.daysSince <= ACTIVE_DAYS));
  const idle = board.filter((r) => !active.includes(r));

  if (!index) return <div className="placeholder">팀 불펜 자료를 읽는 중…</div>;
  const counts = { "평소": 0, "주의": 0, "표시": 0 };
  active.forEach((r) => { counts[r.status] += 1; });
  const weekFrom = date ? addDays(date, -6) : null;
  const weekPitches = board.reduce((s, r) => s + r.p.outings.filter((o) => o.here && o.date >= weekFrom && o.date <= date).reduce((x, o) => x + o.pitches, 0), 0);
  const weekAlarms = board.reduce((s, r) => s + r.p.outings.filter((o) => o.here && o.date >= weekFrom && o.date <= date && o.signals.length).length, 0);
  const days = date ? dateRange(addDays(date, -(WINDOW - 1)), date) : [];
  const teamDates = new Set(dates);
  const idx = dates.indexOf(date);
  const picked = board.find((r) => r.p.id === pid) || null;
  return (
    <div className="page">
      <h1>팀 불펜 현황판</h1>
      <p className="lead">MLB 팀과 날짜를 고르면 그날 경기 뒤 기준으로 불펜 투수마다 등판 부담을 신호등으로 보여 줍니다. 구속 하락 같은 투구 품질 경보는 섞지 않고 따로 표시합니다.</p>
      <details className="more">
        <summary>신호등 기준 보기</summary>
        <p><b>표시</b>: 3일 연속 등판 · 3일 동안 3번 등판 · 최근 7일 투구가 본인 평소(시즌 초 7일 합의 상위 5%)보다 많음 · 30구 이상 던지고 하루 이하 쉬고 등판 중 하나라도 해당.<br />
          <b>주의</b>: 연투 · 최근 1주 투구가 평소(그 앞 3주의 주평균)의 1.5배 이상 — 스포츠과학에서 흔히 쓰는 주의 기준 · 2이닝 이상 던지고 하루 이하 쉬고 등판.<br />
          부상 예측이 아니라 등판 관리용 신호이며, 2024~2025 시즌 검증에서 부상 투수에게 더 자주 켜지지는 않았습니다.</p>
      </details>
      <div className="toolbar">
        <label><span>팀</span>
          <select value={team || ""} onChange={(e) => set({ t: e.target.value, d: undefined, p: undefined })}>
            {teams.map((t) => <option key={t.team} value={t.team}>{TEAM_KO[t.team] || t.team} ({t.team}) · 불펜 {t.relievers}명</option>)}
          </select>
        </label>
        <label><span>시즌</span>
          <select value={season || ""} onChange={(e) => set({ s: e.target.value, d: undefined, p: undefined })}>{seasons.map((s) => <option key={s} value={s}>{s}</option>)}</select>
        </label>
        <label style={{ flex: "1 1 320px" }}><span>기준일</span>
          <button className="btn" onClick={() => idx > 0 && set({ d: dates[idx - 1] })} disabled={idx <= 0} aria-label="앞 경기일">◀</button>
          <input type="range" min={0} max={Math.max(0, dates.length - 1)} value={Math.max(0, idx)} onChange={(e) => set({ d: dates[Number(e.target.value)] })} aria-label="기준일" />
          <button className="btn" onClick={() => idx < dates.length - 1 && set({ d: dates[idx + 1] })} disabled={idx >= dates.length - 1} aria-label="다음 경기일">▶</button>
          <span className="range-value">{date ?? "—"}</span>
        </label>
      </div>
      {!data && <div className="placeholder">{TEAM_KO[team] || team} {season} 불펜 자료를 읽는 중…</div>}
      {data && (
        <>
          <div className="kpi">
            <div><div className="v">{active.length}<span className="sub"> 명</span></div><div className="l">불펜 투수 · 평소 {counts["평소"]} · <span style={{ color: "var(--warn)" }}>주의 {counts["주의"]}</span> · <span style={{ color: "var(--alarm)" }}>표시 {counts["표시"]}</span></div></div>
            <div><div className="v">{weekPitches}<span className="sub"> 구</span></div><div className="l">지난 7일 팀 불펜 투구 수</div></div>
            <div><div className="v">{weekAlarms}<span className="sub"> 건</span></div><div className="l">지난 7일 구속 하락·폼 변화 경보</div></div>
            <div><div className="v">{board.filter((r) => r.onIl).length}<span className="sub"> 명</span></div><div className="l">팔 부상 IL, 아직 복귀 전</div></div>
          </div>
          <div className="card">
            <div className="card-head">
              <h2>{TEAM_KO[team] || team} 불펜 <span style={{ color: "var(--muted)", fontWeight: 500, fontSize: 13 }}>{date} 경기 뒤</span></h2>
              <div className="legend">
                <span><i className="band" style={{ background: "var(--velo-bg)" }} />1~15구</span>
                <span><i className="band" style={{ background: "#9dc1ec" }} />16~25구</span>
                <span><i className="band" style={{ background: "#4f8fdc" }} />26~35구</span>
                <span><i className="band" style={{ background: "#1d4f8f" }} />36구~</span>
                <span><i className="dot" style={{ background: "var(--alarm)" }} />품질 경보</span>
                <span><i className="band" style={{ background: "var(--base-bg)", border: "1px dashed var(--base)" }} />다른 팀 소속 등판</span>
              </div>
            </div>
            <div className="tbl-wrap">
              <table className="tbl board">
                <thead>
                  <tr>
                    <th>투수</th><th>상태</th><th>마지막 등판</th><th className="num">연속 등판</th><th className="num">3일 등판</th><th className="num" title="최근 7일 투구 수 · 본인 평소(시즌 초 7일 합의 상위 5%)를 넘으면 빨간색">7일 투구</th><th>이유</th><th>품질 경보 (14일)</th>
                    <th className="cal">지난 {WINDOW}일 <small>{days[0].slice(5).replace("-", "/")} → {date.slice(5).replace("-", "/")}</small></th>
                  </tr>
                </thead>
                <tbody>
                  {active.map(({ p, st, status, alarms, onIl }) => (
                    <tr key={p.id} className={p.id === pid ? "hl" : ""} onClick={() => set({ p: p.id })} style={{ cursor: "pointer" }}>
                      <td><b>{p.name}</b>{onIl && <span className="light alarm" style={{ marginLeft: 6 }}>IL {PART[p.il.part]} {fmt.date(p.il.date)}</span>}</td>
                      <td><span className={`light ${STATUS_CLASS[status]}`}>{status}</span></td>
                      <td>{st.lastDate ? <>{st.daysSince === 0 ? "오늘" : `${st.daysSince}일 전`} <span style={{ color: "var(--muted)" }}>· {st.lastPitches}구</span></> : <span style={{ color: "var(--muted)" }}>—</span>}</td>
                      <td className="num">{st.consecutive ? `${st.consecutive}일` : "—"}</td>
                      <td className="num">{st.apps3d}</td>
                      <td className="num" title={p.p7d_limit != null ? `본인 평소 ${fmt.num(p.p7d_limit, 0)}구 (시즌 초 7일 합의 상위 5%)` : "시즌 초 등판이 모자라 본인 평소를 아직 정하지 못함"}
                        style={st.flags.includes("p7d") ? { color: "var(--alarm)", fontWeight: 700 } : undefined}>{st.p7d}</td>
                      <td>{reasons(st).map((r) => <span key={r.t} className={`light ${r.cls}`} style={{ marginRight: 4 }}>{r.t}</span>)}</td>
                      <td>{alarms.length ? alarms.map((o) => <span key={o.date} className="light alarm" style={{ marginRight: 4 }}>{fmt.date(o.date)} {o.signals.map((s) => SIGNAL_NAME[s]).join("·")}</span>) : <span style={{ color: "var(--muted)" }}>없음</span>}</td>
                      <td className="cal"><Strip p={p} days={days} teamDates={teamDates} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {idle.length > 0 && (
              <p className="caption" style={{ marginTop: 10 }}>최근 {ACTIVE_DAYS}일 등판 없음(마이너 이동·IL 등 공개 기록에 없는 사유 포함) · {idle.length}명:{" "}
                {idle.map((r) => <button key={r.p.id} className="pill" onClick={() => set({ p: r.p.id })}>{r.p.name} <span style={{ color: "var(--muted)" }}>{fmt.date(r.st.lastDate)}</span></button>)}
              </p>
            )}
            <p className="caption">7일 투구가 빨간색이면 그 투수의 평소(시즌 초 등판으로 정함)보다 많이 던진 것입니다. 줄을 누르면 시즌 전체 그래프가 열립니다. <span className="hover-hint">'지난 14일' 칸과 '7일 투구' 제목에 커서를 올리면 날짜별 투구 수와 설명</span></p>
          </div>
          {picked && <Detail row={picked} rules={index.rules} date={date} />}
          <p className="note">불펜에서 몸만 풀고 등판하지 않은 투구는 기록에 없어 실제 부담은 이보다 큽니다. 다른 팀에서 던진 등판도 계산에 넣습니다(달력에서 점선 칸).</p>
        </>
      )}
    </div>
  );
}

function heat(pitches) {
  return pitches > 35 ? "h4" : pitches > 25 ? "h3" : pitches > 15 ? "h2" : "h1";
}

/** 지난 14일 칸: 팀 경기일은 옅은 바탕, 등판한 날은 투구 수와 짙기, 다른 팀 소속 등판은 점선, 품질 경보는 점. */
function Strip({ p, days, teamDates }) {
  const by = new Map();
  p.outings.forEach((o) => { const cur = by.get(o.date); by.set(o.date, cur ? { ...cur, pitches: cur.pitches + o.pitches, signals: [...cur.signals, ...o.signals] } : { ...o }); });
  return (
    <div className="strip">
      {days.map((d) => {
        const o = by.get(d);
        const cls = o ? `on ${heat(o.pitches)}${o.here ? "" : " away"}` : teamDates.has(d) ? "game" : "off";
        return <span key={d} className={cls} title={`${d}${o ? ` · ${o.pitches}구${o.here ? "" : " (다른 팀)"}${o.signals.length ? " · 경보" : ""}` : teamDates.has(d) ? " · 등판 없음" : " · 팀 경기 없음"}`}>{o ? o.pitches : ""}{o?.signals.length ? <i /> : null}</span>;
      })}
    </div>
  );
}

/** 고른 투수의 시즌 전체: 등판 투구 수 막대, 등판일마다 다시 계산한 ACWR 선, 품질 경보 점, IL 등재일 선, 기준일 선. */
function Detail({ row, rules, date }) {
  const { p } = row;
  const rows = p.outings.map((o) => {
    const st = dayState(p.outings, o.date, rules, p.p7d_limit, p.p7d_from);
    return { ...o, acwr: st.acwr, apps3d: st.apps3d, p7d: st.p7d, flags: st.flags, why: reasons(st), marker: o.signals.length ? o.pitches : null };
  });
  let ilX = p.il ? rows.find((r) => r.date >= p.il.date)?.date : null;
  if (p.il && !ilX) { rows.push({ date: p.il.date, pitches: null, acwr: null, flags: [], signals: [], marker: null, placeholder: true }); ilX = p.il.date; }
  const dateX = rows.find((r) => !r.placeholder && r.date >= date)?.date ?? null;
  const flagged = rows.filter((r) => r.why?.length || r.signals?.length);
  return (
    <div className="card">
      <div className="card-head">
        <h2>{p.name} <span style={{ color: "var(--muted)", fontWeight: 500 }}>· {p.id.split("_")[1]} 시즌 등판 {p.outings.length}회{p.il && ` · 팔 부상 IL ${fmt.date(p.il.date)} (${PART[p.il.part]})`}</span></h2>
        <div className="legend">
          <span><i className="band" style={{ background: "var(--navy-2)" }} />등판 투구 수</span>
          <span><i style={{ background: "var(--warn)" }} />7일 투구 수</span>
          {p.p7d_limit != null && <span><i className="dash" />본인 평소 {fmt.num(p.p7d_limit, 0)}구</span>}
          <span><i className="dot" style={{ background: "var(--alarm)" }} />품질 경보</span>
          <span><i style={{ background: "var(--ink)" }} />IL 등재일</span>
          <Link to={`/replay?p=${p.id}`} style={{ marginLeft: 8 }}>투수 시즌 상세에서 구속·폼 보기 →</Link>
        </div>
      </div>
      <ResponsiveContainer width="100%" height={280}>
        <ComposedChart data={rows} margin={{ top: 16, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke={GRID} />
          <XAxis dataKey="date" tickFormatter={fmt.date} tick={TICK} axisLine={{ stroke: GRID }} tickLine={false} minTickGap={24} />
          <YAxis yAxisId="p" tick={TICK} width={34} axisLine={false} tickLine={false} />
          <Tooltip content={<ChartTip render={(payload) => <LoadTip d={payload[0].payload} />} />} cursor={{ fill: "rgba(20,20,19,0.04)" }} />
          <Bar yAxisId="p" dataKey="pitches" name="등판 투구 수" fill="var(--navy-2)" maxBarSize={14} radius={[2, 2, 0, 0]} isAnimationActive={false} />
          <Line yAxisId="p" type="monotone" dataKey="p7d" name="7일 투구 수" stroke="var(--warn)" strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
          <Scatter yAxisId="p" dataKey="marker" name="품질 채널 경보" shape={<Mark />} isAnimationActive={false} tooltipType="none" />
          {p.p7d_limit != null && <ReferenceLine yAxisId="p" y={p.p7d_limit} stroke="var(--alarm)" strokeDasharray="4 4" label={limitLabel(`본인 평소 ${fmt.num(p.p7d_limit, 0)}구`)} />}
          {ilX && <ReferenceLine yAxisId="p" x={ilX} stroke="var(--ink)" strokeWidth={1.2} label={{ value: `IL 등재일 ${fmt.date(p.il.date)}`, position: "insideTopRight", ...LABEL }} />}
          {dateX && <ReferenceLine yAxisId="p" x={dateX} stroke="var(--velo)" strokeDasharray="3 3" label={{ value: `기준일 ${fmt.date(date)}`, position: "insideTopLeft", ...LABEL, fill: "var(--velo)" }} />}
        </ComposedChart>
      </ResponsiveContainer>
      <p className="caption"><span className="hover-hint">그래프에 커서를 올리면 그날 투구 수·3일 등판·7일 투구와 이유</span></p>
      <details className="more" style={{ margin: "4px 0 0" }}>
      <summary>지난 표시·주의·품질 경보 등판 보기 ({flagged.length}건)</summary>
      <div className="tbl-wrap" style={{ marginTop: 8 }}>
        <table className="tbl">
          <thead><tr><th>날짜</th><th className="num">투구 수</th><th className="num">3일 등판</th><th className="num">7일 투구</th><th>이유</th><th>품질 경보</th></tr></thead>
          <tbody>
            {flagged.map((d) => (
              <tr key={d.date}>
                <td>{d.date}{!d.here && <span style={{ color: "var(--muted)" }}> (다른 팀)</span>}</td><td className="num">{d.pitches}</td><td className="num">{d.apps3d}</td><td className="num">{d.p7d}</td>
                <td>{d.why.map((r) => <span key={r.t} className={`light ${r.cls}`} style={{ marginRight: 4 }}>{r.t}</span>)}</td>
                <td>{d.signals.map((s) => <span key={s} className="light alarm" style={{ marginRight: 4 }}>{SIGNAL_NAME[s]}</span>)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      </details>
    </div>
  );
}

function LoadTip({ d }) {
  return (
    <>
      {d.placeholder ? <div><b>{d.date}</b> · IL 등재일</div> : <div><b>{d.date}</b> · 투구 {d.pitches}구{d.here === false ? " · 다른 팀 소속" : ""}</div>}
      {!d.placeholder && <div>3일 등판 {d.apps3d}회 · 7일 투구 {d.p7d}구{d.acwr != null && ` · 최근 1주는 평소의 ${fmt.num(d.acwr, 1)}배`}</div>}
      {d.why?.length > 0 && <div>{d.why.map((r) => r.t).join(", ")}</div>}
      {d.signals?.length > 0 && <div className="alarm">품질 채널 경보: {d.signals.map((s) => SIGNAL_NAME[s]).join(", ")}</div>}
    </>
  );
}
