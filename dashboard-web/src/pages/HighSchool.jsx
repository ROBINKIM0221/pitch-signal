import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Bar, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis, Legend } from "recharts";
import { fmt, useJson } from "../lib/data.js";
import { GRID, LABEL, LEGEND_STYLE, TICK, TIP_STYLE, limitLabel } from "../lib/chart.jsx";

const RULE_NAME = { daily_max: "하루 105구 초과", rest: "의무 휴식일 미준수", three_days: "3일 연속 등판", unknown: "투구 수 기록 없음(판정 불가)" };
const LOAD_CLASS = { "보통": "ok", "주의": "warn", "경보": "alarm", "계산 불가": "base" };
const STATUS_CLASS = { "준수": "ok", "위반": "alarm", "판정 불가": "base" };

export default function HighSchool() {
  const { data } = useJson("highschool.json");
  if (!data) return <div className="placeholder">고교 현황판 자료를 읽는 중…</div>;
  return data.mode === "tournament" ? <TournamentBoard data={data} /> : <SeasonBoard data={data} />;
}

/* ---------- 대회 모드: 2025 전국체전 18세 이하부 (KBSA 기록실 실제 기록) ---------- */

function requiredRest(pitches, table) {
  if (pitches == null) return null;
  for (const [upper, rest] of table) if (pitches <= upper) return rest;
  return table[table.length - 1][1];
}

// 날짜 계산은 UTC로 한다. 지역시간 자정을 toISOString으로 바꾸면 한국에서는 하루 전 날짜가 나온다.
function addDays(date, n) {
  const d = new Date(date + "T00:00:00Z"); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10);
}

function dayList(games) {
  const dates = games.map((g) => g.date).sort();
  const out = [];
  for (let d = dates[0]; d <= dates[dates.length - 1]; d = addDays(d, 1)) out.push(d);
  return out;
}

/** 한 투수의 하루별 칸: 등판(투구 수)·의무 휴식·빈칸. */
function cellsFor(p, days, restTable) {
  const byDate = Object.fromEntries(p.games.map((g) => [g.date, g]));
  const rest = new Set();
  for (const g of p.games) {
    const need = requiredRest(g.pitches, restTable);
    for (let i = 1; need != null && i <= need; i++) rest.add(addDays(g.date, i));
  }
  return days.map((d) => (byDate[d] ? { kind: "game", g: byDate[d] } : rest.has(d) ? { kind: "rest" } : { kind: "empty" }));
}

function heatClass(pitches) {
  if (pitches == null) return "unknown";
  if (pitches > 90) return "h4";
  if (pitches > 60) return "h3";
  if (pitches > 30) return "h2";
  return "h1";
}

function loadLight(p) {
  if (p.pitches_total == null) return { cls: "base", text: "누적 모름" };
  return { cls: p.pitches_total >= 150 ? "alarm" : p.pitches_total >= 100 ? "warn" : "ok", text: `누적 ${p.pitches_total}구` };
}

function TournamentBoard({ data }) {
  const { tournament: t, totals, kbsa } = data;
  const schools = useMemo(() => [...data.schools].sort((a, b) => b.games - a.games || a.code.localeCompare(b.code)), [data]);
  const [params, setParams] = useSearchParams();                    // 주소 ?s=학교&p=투수 로 특정 화면을 가리킬 수 있다
  const s = schools.find((x) => x.code === params.get("s")) || schools[0];
  const pitchers = useMemo(() => [...(s?.pitchers || [])].sort((a, b) => (b.pitches_total ?? -1) - (a.pitches_total ?? -1) || a.code.localeCompare(b.code)), [s]);
  const p = pitchers.find((x) => x.code === params.get("p")) || pitchers[0];
  const code = p?.code;
  const setSchool = (next) => setParams({ s: next }, { replace: true });
  const setCode = (next) => setParams({ s: s.code, p: next }, { replace: true });
  const days = useMemo(() => dayList(data.games), [data]);
  const gamesByDate = useMemo(() => Object.fromEntries(days.map((d) => [d, data.games.filter((g) => g.date === d && g.teams.includes(s?.code))])), [days, data, s]);
  const chart = days.map((d) => { const g = p?.games.find((x) => x.date === d); return { date: d, pitches: g ? g.pitches : null, unknown: g && g.pitches == null ? kbsa.daily_max : null, cum: g ? g.cum_pitches : null }; });
  return (
    <div className="page">
      <h1>고교 투구수 현황판 <span className="badge real">실제 기록 · {t.season} {t.short} 18세 이하부</span></h1>
      <p className="lead">
        {t.name} ({t.dates}, 15개교 {t.games}경기 단판 토너먼트). KBSA 기록실의 경기별 투수 기록(등판 구분·이닝·투구수)을 그대로 옮겼고, 학교는 S01~S15, 투수는 S03-P02 같은 가명 코드만 씁니다.
        신호등 두 개는 서로 다른 뜻입니다. <b>규정</b>은 KBSA 투구수 규정(하루 {kbsa.daily_max}구, 투구 수별 의무 휴식일, 3일 연속 등판 금지)을 지켰는지,
        <b> 누적</b>은 대회 7일 동안 던진 투구 수의 합입니다(100구 이상 주의, 150구 이상 경보로 표시. ACWR은 4주 자료가 있어야 해서 단기 대회에서는 계산하지 않습니다).
      </p>
      <div className="kpi">
        <div><div className="v">{t.games}<span className="sub"> 경기</span></div><div className="l">상세 기록 {t.games - t.no_detail_games.length}경기 · {t.no_detail_games.length}경기는 선발만 공개(투구 수 모름)</div></div>
        <div><div className="v">{totals.pitchers}<span className="sub"> 명</span></div><div className="l">등판 투수 · 등판 {totals.outings}회 · 3경기 이상 등판 {totals.pitchers_3plus_games}명</div></div>
        <div><div className="v">{totals.violations}<span className="sub"> 건</span></div><div className="l">규정 위반 · 판정 불가 {totals.unknown_outings}등판</div></div>
        <div><div className="v">{totals.back_to_back}<span className="sub"> 건</span></div><div className="l">연투(이튿날 다시 등판) · 의무 휴식일 뒤 첫날 등판 {totals.min_rest_exact}건</div></div>
        <div><div className="v">{totals.games_91plus}<span className="sub"> 등판</span></div><div className="l">91구 이상(휴식 4일 구간) · 100구 이상 {totals.games_100plus}등판 · 최다 {kbsa.daily_max}구</div></div>
        <div><div className="v">{totals.max_total}<span className="sub"> 구</span></div><div className="l">한 투수의 대회 누적 최다 투구 수</div></div>
      </div>
      <div className="toolbar">
        <label><span>학교</span>
          <select value={s?.code || ""} onChange={(e) => setSchool(e.target.value)}>
            {schools.map((x) => <option key={x.code} value={x.code}>{x.code} · {x.games}경기 · 투수 {x.pitchers.length}명</option>)}
          </select>
        </label>
        <span className="caption" style={{ margin: 0 }}>경기 수가 많은 학교(결승 진출 4경기)부터 정렬. 투수는 누적 투구 수가 많은 순.</span>
      </div>
      <div className="grid2 hs-grid">
        <div className="card">
          <h2>{s?.code} 투수 <span style={{ color: "var(--muted)", fontWeight: 500 }}>· 규정 / 누적</span></h2>
          <div className="list">
            {pitchers.map((x) => {
              const load = loadLight(x);
              return (
                <button key={x.code} className={x.code === code ? "on" : ""} onClick={() => setCode(x.code)}>
                  <span className="code">{x.code}</span>
                  <span className={`light ${STATUS_CLASS[x.rule_status]}`}>규정 {x.rule_status}</span>
                  <span className={`light ${load.cls}`}>{load.text}</span>
                  <span className="tags">
                    {x.back_to_back > 0 && <span className="pill"><span className="dot" style={{ background: "var(--warn)" }} />연투 {x.back_to_back}</span>}
                    {x.min_rest_exact > 0 && <span className="pill"><span className="dot" style={{ background: "var(--warn)" }} />최소 휴식 뒤 등판 {x.min_rest_exact}</span>}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
        <div className="card">
          <h2>{s?.code} 대회 등판 달력 <span style={{ color: "var(--muted)", fontWeight: 500 }}>· 칸의 숫자는 그날 투구 수</span></h2>
          <div className="tbl-wrap">
            <table className="heat">
              <thead>
                <tr><th>투수</th>{days.map((d) => <th key={d}>{d.slice(5).replace("-", "/")}<small>{gamesByDate[d]?.length ? gamesByDate[d].map((g) => g.round).join("·") : ""}</small></th>)}</tr>
              </thead>
              <tbody>
                {pitchers.map((x) => (
                  <tr key={x.code} className={x.code === code ? "hl" : ""} onClick={() => setCode(x.code)}>
                    <th>{x.code}</th>
                    {cellsFor(x, days, kbsa.rest_table).map((c, i) => (
                      <td key={i} className={c.kind === "game" ? `game ${heatClass(c.g.pitches)}` : c.kind}>
                        {c.kind === "game" ? (c.g.pitches == null ? "?" : c.g.pitches) : c.kind === "rest" ? "휴" : ""}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="legend" style={{ marginTop: 8 }}>
            <span><i className="band" style={{ background: "var(--velo-bg)" }} />1~30구</span>
            <span><i className="band" style={{ background: "#9dc1ec" }} />31~60구</span>
            <span><i className="band" style={{ background: "#4f8fdc" }} />61~90구</span>
            <span><i className="band" style={{ background: "#1d4f8f" }} />91~105구</span>
            <span><i className="band rest" />의무 휴식일(직전 투구 수 기준)</span>
            <span><i className="band" style={{ background: "var(--base-bg)", border: "1px dashed var(--base)" }} />? 투구 수 미공개 등판</span>
          </div>
        </div>
      </div>
      {p && (
        <div className="card">
          <div className="card-head">
            <h2>{p.code} <span style={{ color: "var(--muted)", fontWeight: 500 }}>· 등판 {p.outings}회{p.pitches_total != null && ` · 누적 ${p.pitches_total}구`}{p.max_pitches != null && ` · 한 경기 최다 ${p.max_pitches}구`}</span></h2>
            <span className={`light ${STATUS_CLASS[p.rule_status]}`}>규정 {p.rule_status}</span>
          </div>
          <div className="grid2 hs-detail">
            <div className="tbl-wrap">
              <table className="tbl">
                <thead><tr><th>날짜</th><th>라운드</th><th>상대</th><th>등판</th><th className="num">이닝</th><th className="num">투구 수</th><th>직전 등판 뒤</th><th className="num">누적</th></tr></thead>
                <tbody>
                  {p.games.map((g) => (
                    <tr key={g.game_no}>
                      <td>{g.date.slice(5).replace("-", "/")}</td><td>{g.round}</td><td>{g.opponent}</td>
                      <td>{g.role}{g.result !== "-" && <span style={{ color: "var(--muted)" }}> · {g.result}</span>}</td>
                      <td className="num">{Math.floor(g.outs / 3)}{g.outs % 3 ? `.${g.outs % 3}` : ""}</td>
                      <td className="num">{g.pitches == null ? <span className="light base">미공개</span> : g.pitches}</td>
                      <td>{restText(g)}</td>
                      <td className="num">{g.cum_pitches == null ? "—" : g.cum_pitches}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div>
              <ResponsiveContainer width="100%" height={220}>
                <ComposedChart data={chart} margin={{ top: 12, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid vertical={false} stroke={GRID} />
                  <XAxis dataKey="date" tickFormatter={(d) => d.slice(5).replace("-", "/")} tick={TICK} axisLine={{ stroke: GRID }} tickLine={false} />
                  <YAxis domain={[0, 120]} tick={TICK} width={34} axisLine={false} tickLine={false} />
                  <Tooltip {...TIP_STYLE} formatter={(v, n) => [n === "투구 수 미공개" ? "미공개" : fmt.num(v, 0), n]} />
                  <Legend wrapperStyle={LEGEND_STYLE} verticalAlign="top" iconType="plainline" />
                  <Bar dataKey="pitches" name="투구 수" fill="var(--velo)" radius={[3, 3, 0, 0]} isAnimationActive={false} />
                  <Bar dataKey="unknown" name="투구 수 미공개" fill="var(--base-bg)" stroke="var(--base)" strokeDasharray="3 3" radius={[3, 3, 0, 0]} isAnimationActive={false} />
                  <Line type="monotone" dataKey="cum" name="누적" stroke="var(--warn)" strokeWidth={2} dot={{ r: 3 }} connectNulls isAnimationActive={false} />
                  <ReferenceLine y={kbsa.daily_max} stroke="var(--alarm)" strokeDasharray="4 4" label={limitLabel(`하루 ${kbsa.daily_max}구`)} />
                </ComposedChart>
              </ResponsiveContainer>
              <p className="caption">누적 선은 대회 기간 투구 수의 합. 투구 수가 공개되지 않은 경기(점선 막대) 뒤로는 누적을 표시하지 않습니다.</p>
            </div>
          </div>
          {p.violations.length > 0 && (
            <div className="tbl-wrap" style={{ marginTop: 8 }}>
              <table className="tbl">
                <thead><tr><th>날짜</th><th>규정</th><th>내용</th></tr></thead>
                <tbody>{p.violations.map((v) => <tr key={v.date + v.rule}><td>{v.date}</td><td><span className={`light ${v.rule === "unknown" ? "base" : "alarm"}`}>{RULE_NAME[v.rule] || v.rule}</span></td><td style={{ whiteSpace: "normal" }}>{v.detail}</td></tr>)}</tbody>
              </table>
            </div>
          )}
        </div>
      )}
      <p className="note">
        출처: {t.source}. 상세 기록이 공개되지 않은 경기({t.no_detail_games.map((n) => `${n}경기`).join(", ")})는 선발 투수 두 명만 '투구 수 미공개'로 들어가 있고, 그날 등판한 다른 투수는 기록에 없습니다.
        한계: 공식 경기 투구 수만 반영되고 대회 전 주말리그·연습 투구는 빠집니다. 고교에는 공식 부상 기록이 없어 이 화면은 '규정이 보지 못하는 부하를 보여 주는 현황판'이지 탐지 성능을 검증한 것이 아닙니다.
        규정 수치(하루 {kbsa.daily_max}구, 휴식일 표 {kbsa.rest_table.map(([u, r]) => `${u}구 이하 ${r}일`).join(" · ")})는 설정 파일 값입니다.
      </p>
    </div>
  );
}

function restText(g) {
  if (g.gap_days == null) return <span style={{ color: "var(--muted)" }}>첫 등판</span>;
  const gap = `${g.gap_days}일 휴식`;
  if (g.required_rest == null) return <>{gap} <span style={{ color: "var(--muted)" }}>· 직전 투구 수 미공개</span></>;
  const need = g.required_rest === 0 ? "의무 휴식 없음" : `의무 ${g.required_rest}일`;
  if (g.rest_ok === false) return <>{gap} <span className="light alarm">{need} 미달</span></>;
  if (g.gap_days === 0) return <>{gap} <span className="light warn">연투</span> <span style={{ color: "var(--muted)" }}>· {need}</span></>;
  if (g.min_rest_exact) return <>{gap} <span className="light warn">{need} 뒤 첫날</span></>;
  return <>{gap} <span style={{ color: "var(--muted)" }}>· {need}</span></>;
}

/* ---------- 시즌 모드: 입력 양식(data/highschool/input.xlsx)으로 들어온 학교별 시즌 기록 ---------- */

function SeasonBoard({ data }) {
  const [school, setSchool] = useState(null);
  const [code, setCode] = useState(null);
  const [foreign, setForeign] = useState("none");
  useEffect(() => { if (data && !school) setSchool(data.schools[0]?.code); }, [data, school]);
  const s = data?.schools.find((x) => x.code === school);
  useEffect(() => { if (s && !s.pitchers.find((p) => p.code === code)) setCode(s.pitchers[0]?.code); }, [s, code]);
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
