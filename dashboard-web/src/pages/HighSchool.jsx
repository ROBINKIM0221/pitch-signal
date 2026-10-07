import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { Bar, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis, Legend } from "recharts";
import { fmt, useJson } from "../lib/data.js";
import { ChartTip, GRID, LABEL, LEGEND_STYLE, TICK, TIP_STYLE, limitLabel } from "../lib/chart.jsx";
import { addDays, dailySeries, dateRange } from "../lib/load.js";

const RULE_NAME = { daily_max: "하루 105구 초과", rest: "의무 휴식일 미준수", three_days: "3일 연속 등판", unknown: "투구 수 기록 없음(판정 불가)" };
const LOAD_CLASS = { "보통": "ok", "주의": "warn", "경보": "alarm", "계산 불가": "base" };
const STATUS_CLASS = { "준수": "ok", "위반": "alarm", "판정 불가": "base" };

export default function HighSchool() {
  const { data: index } = useJson("highschool.json");
  const [params, setParams] = useSearchParams();
  const key = index?.datasets?.find((d) => d.key === params.get("d"))?.key || index?.datasets?.[0]?.key;
  const { data } = useJson(key ? `highschool/${key}.json` : null);
  if (!index) return <div className="placeholder">고교 현황판 자료를 읽는 중…</div>;
  if (index.synthetic || !index.datasets?.length) return <SeasonLegacy data={index} />;
  const pick = (next) => setParams({ d: next }, { replace: true });
  const selector = (
    <div className="seg" role="tablist" aria-label="자료" style={{ marginBottom: 14 }}>
      {index.datasets.map((d) => <button key={d.key} role="tab" className={`btn ${d.key === key ? "on" : ""}`} aria-selected={d.key === key} onClick={() => pick(d.key)}>{d.short} · {d.mode === "season" ? "시즌 전체" : "7일 대회"}</button>)}
    </div>
  );
  if (!data) return <div className="page"><h1>고교 투구수 현황판</h1>{selector}<div className="placeholder">자료를 읽는 중…</div></div>;
  const common = { data, index, selector, params, setParams };
  return data.mode === "tournament" ? <TournamentBoard {...common} /> : <SeasonBoard {...common} />;
}

/* ---------- 공통 조각 ---------- */

function useSelection(data, params, setParams) {
  const schools = data.schools;
  const s = schools.find((x) => x.code === params.get("s")) || schools[0];
  const pitchers = s?.pitchers || [];
  const p = pitchers.find((x) => x.code === params.get("p")) || pitchers[0];
  const keep = { d: params.get("d") };
  const setSchool = (next) => setParams({ ...keep, s: next }, { replace: true });
  const setCode = (next) => setParams({ ...keep, s: s.code, p: next }, { replace: true });
  return { schools, s, pitchers, p, setSchool, setCode };
}

function requiredRest(pitches, table) {
  if (pitches == null) return null;
  for (const [upper, rest] of table) if (pitches <= upper) return rest;
  return table[table.length - 1][1];
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

function innings(outs) { return `${Math.floor(outs / 3)}${outs % 3 ? `.${outs % 3}` : ""}`; }

function DayTip({ d }) {
  return (
    <>
      <div><b>{d.date}</b> · {d.pitches ? `투구 ${d.pitches}구` : "등판 없음"}</div>
      <div>7일 합 {fmt.num(d.sum_7d, 0)}구{d.acwr != null ? ` · ACWR ${fmt.num(d.acwr)}` : " · ACWR 계산 불가"}</div>
    </>
  );
}

function GamesTable({ p, withCompetition }) {
  return (
    <div className="tbl-wrap">
      <table className="tbl">
        <thead><tr><th>날짜</th><th>{withCompetition ? "대회" : "라운드"}</th><th>상대</th><th>등판</th><th className="num">이닝</th><th className="num">투구 수</th><th>직전 등판 뒤</th><th className="num">누적</th></tr></thead>
        <tbody>
          {p.games.map((g) => (
            <tr key={g.game_no}>
              <td>{g.date.slice(5).replace("-", "/")}</td><td>{withCompetition ? g.competition : g.round}</td><td>{g.opponent}</td>
              <td>{g.role}{g.result !== "-" && <span style={{ color: "var(--muted)" }}> · {g.result}</span>}</td>
              <td className="num">{innings(g.outs)}</td>
              <td className="num">{g.pitches == null ? <span className="light base">미공개</span> : g.pitches}</td>
              <td>{restText(g)}</td>
              <td className="num">{g.cum_pitches == null ? "—" : g.cum_pitches}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ViolationsTable({ p }) {
  if (!p.violations.length) return null;
  return (
    <div className="tbl-wrap" style={{ marginTop: 8 }}>
      <table className="tbl">
        <thead><tr><th>날짜</th><th>규정</th><th>내용</th></tr></thead>
        <tbody>{p.violations.map((v) => <tr key={v.date + v.rule}><td>{v.date}</td><td><span className={`light ${v.rule === "unknown" ? "base" : "alarm"}`}>{RULE_NAME[v.rule] || v.rule}</span></td><td style={{ whiteSpace: "normal" }}>{v.detail}</td></tr>)}</tbody>
      </table>
    </div>
  );
}

/* ---------- 시즌 모드: 2025 경기도 고교 공식 경기 (KBSA 규정 + ACWR) ---------- */

function SeasonBoard({ data, index, selector, params, setParams }) {
  const { schools, s, pitchers, p, setSchool, setCode } = useSelection(data, params, setParams);
  const { dataset: ds, totals, kbsa } = data;
  const foreign = params.get("f") && data.foreign_rules[params.get("f")] ? params.get("f") : "none";
  const rule = foreign !== "none" ? data.foreign_rules[foreign] : null;
  const days = useMemo(() => (p && s ? dailySeries(p.games.map((g) => ({ date: g.date, pitches: g.pitches })), s.start, s.end, data.acwr) : [])
    .map((d) => ({ ...d, over: rule ? (d.sum_7d != null && d.sum_7d > rule.max_pitches) : false })), [p, s, data, rule]);
  const monthTicks = useMemo(() => days.filter((d) => d.date.endsWith("-01")).map((d) => d.date), [days]);   // 두 패널의 눈금을 매달 1일로 맞춘다
  const summary = data.summary.find((r) => r["학교"] === s?.code);
  const ruleCounts = Object.entries(totals.violations_by_rule).filter(([k]) => k !== "unknown").map(([k, v]) => `${RULE_NAME[k] || k} ${v}`).join(" · ");
  return (
    <div className="page">
      <h1>고교 투구수 현황판 <span className="badge real">실제 기록 · {ds.short}</span></h1>
      {selector}
      <p className="lead">
        {ds.name}: {ds.region} 소재 {totals.schools}개 팀(주말리그 경기권 A·B·C 참가교, U-18 클럽 포함)의 {ds.dates} 공식 경기 {ds.games}경기 — {Object.entries(ds.competitions).map(([k, v]) => `${k} ${v}`).join(", ")}.
        {" "}{index.labels}. 신호등 두 개는 서로 다른 뜻입니다. <b>규정</b>은 KBSA 투구수 규정(하루 {kbsa.daily_max}구, 투구 수별 의무 휴식일, 3일 연속 등판 금지)을 지켰는지,
        <b> 누적 부하</b>는 ACWR(최근 7일 투구 수 ÷ 그 앞 3주 주평균)이 {data.acwr_flag}을 넘은 적이 있는지입니다(3.14절 설계값. 아래 숫자가 보여 주듯 고교 일정에서는 저활동 뒤 등판에서 자주 켜지므로 7일 합·연투와 함께 읽어야 합니다).
      </p>
      <div className="kpi">
        <div><div className="v">{totals.schools}<span className="sub"> 팀</span></div><div className="l">투수 {totals.pitchers}명 · 등판 {totals.outings}회 · {totals.games}경기 (투구 수 미공개 {totals.unknown_outings}등판)</div></div>
        <div><div className="v">{totals.violations}<span className="sub"> 건</span></div><div className="l">규정 위반 · 투수 {totals.violating_pitchers}명{ruleCounts && ` (${ruleCounts})`}</div></div>
        <div><div className="v">{totals.acwr_flag_pitchers}<span className="sub"> / {totals.acwr_ok_pitchers}</span></div><div className="l">ACWR {data.acwr_flag} 초과를 경험한 투수 / 계산 가능 투수{totals.acwr_flag_chronic_median != null && ` · 초과 시점의 직전 3주 주평균 중앙값 ${fmt.num(totals.acwr_flag_chronic_median, 0)}구`}</div></div>
        <div><div className="v">{totals.compliant_with_flag}<span className="sub"> 명</span></div><div className="l">규정은 모두 지켰지만 ACWR 초과 표시가 있던 투수</div></div>
        <div><div className="v">{totals.pitchers_7d_150}<span className="sub"> 명</span></div><div className="l">7일 합 150구 이상을 경험한 투수 · 시즌 500구 이상 {totals.pitchers_season_500}명</div></div>
        <div><div className="v">{totals.back_to_back}<span className="sub"> 건</span></div><div className="l">연투(이튿날 다시 등판) · 의무 휴식일 뒤 첫날 등판 {totals.min_rest_exact}건</div></div>
        <div><div className="v">{totals.games_91plus}<span className="sub"> 등판</span></div><div className="l">91구 이상(휴식 4일 구간) · 100구 이상 {totals.games_100plus}등판</div></div>
      </div>
      <div className="toolbar">
        <label><span>학교</span>
          <select value={s?.code || ""} onChange={(e) => setSchool(e.target.value)}>
            {schools.map((x) => <option key={x.code} value={x.code}>{x.name} · {x.games}경기 · 투수 {x.pitchers.length}명</option>)}
          </select>
        </label>
        <label><span>해외 규정 비교</span>
          <select value={foreign} onChange={(e) => setParams({ d: params.get("d"), s: s.code, p: p?.code, f: e.target.value }, { replace: true })}>
            <option value="none">없음</option>
            {Object.entries(data.foreign_rules).map(([k, v]) => <option key={k} value={k}>{k === "japan" ? "일본" : k} {v.window_days}일 {v.max_pitches}구</option>)}
          </select>
        </label>
        <span className="caption" style={{ margin: 0 }}>경기 수가 많은 팀부터. 투수는 시즌 투구 수가 많은 순.</span>
      </div>
      {summary && (
        <div className="kpi">
          <div><div className="v">{s.pitchers.length}<span className="sub"> 명</span></div><div className="l">{s.name} 투수 · {s.games}경기 · 팀 투구 수 {s.pitches_total ?? "—"}</div></div>
          <div><div className="v">{summary["규정 위반 건수"]}<span className="sub"> 건</span></div><div className="l">규정 위반 · 투수 {summary["위반 투수 수"]}명</div></div>
          <div><div className="v">{summary["ACWR 기준 초과 투수 수"]}<span className="sub"> / {summary["ACWR 계산 가능 투수 수"]}</span></div><div className="l">ACWR {data.acwr_flag} 초과 경험 / 계산 가능 투수</div></div>
          <div><div className="v">{summary["위반 없이 누적 부하 표시"]}<span className="sub"> 명</span></div><div className="l">규정은 지켰지만 누적 부하 표시가 있던 투수</div></div>
        </div>
      )}
      <div className="grid2">
        <div className="card">
          <h2>{s?.name} 투수 <span style={{ color: "var(--muted)", fontWeight: 500 }}>· 규정 / 누적 부하(ACWR)</span></h2>
          <div className="list">
            {pitchers.map((x) => (
              <button key={x.code} className={x.code === p?.code ? "on" : ""} onClick={() => setCode(x.code)}>
                <span className="code">{x.label}</span>
                <span className={`light ${STATUS_CLASS[x.rule_status]}`}>규정 {x.rule_status}</span>
                <span className={`light ${LOAD_CLASS[x.load_status]}`}>ACWR {x.load_status}{x.acwr_peak != null && <span style={{ fontWeight: 500 }}> · 최고 {fmt.num(x.acwr_peak, 1)}</span>}</span>
                <span className="tags"><span className="pill">{x.outings}등판 · {x.pitches_total ?? "—"}구</span>{x.max_7d != null && <span className="pill">7일 최대 {fmt.num(x.max_7d, 0)}구</span>}</span>
              </button>
            ))}
          </div>
        </div>
        <div className="card">
          <h2>{s?.name} 시즌 투구 수 분배 <span style={{ color: "var(--muted)", fontWeight: 500 }}>· 투수별 합계</span></h2>
          <ResponsiveContainer width="100%" height={Math.max(220, 24 * pitchers.length + 40)}>
            <ComposedChart layout="vertical" data={pitchers.map((x) => ({ label: x.label, total: x.pitches_total ?? 0, unknown: x.pitches_total == null, on: x.code === p?.code }))} margin={{ top: 4, right: 48, left: 4, bottom: 0 }}>
              <CartesianGrid horizontal={false} stroke={GRID} />
              <XAxis type="number" tick={TICK} axisLine={false} tickLine={false} />
              <YAxis type="category" dataKey="label" width={44} tick={TICK} axisLine={false} tickLine={false} interval={0} />
              <Tooltip {...TIP_STYLE} formatter={(v, n, item) => [item.payload.unknown ? "일부 미공개" : `${fmt.num(v, 0)}구`, "시즌 투구 수"]} />
              <Bar dataKey="total" name="시즌 투구 수" fill="var(--velo)" radius={[0, 3, 3, 0]} isAnimationActive={false} label={{ position: "right", fontSize: 11, fill: "var(--ink-2)", formatter: (v) => (v ? fmt.num(v, 0) : "") }} />
              <ReferenceLine x={500} stroke="var(--alarm)" strokeDasharray="4 4" label={{ value: "500구", position: "insideTopRight", ...LABEL, fill: "var(--alarm)" }} />
            </ComposedChart>
          </ResponsiveContainer>
          <p className="caption">팀 합계 {s?.pitches_total ?? "—"}구 · {s?.games}경기. 한두 명에게 몰리는지 한눈에 봅니다.</p>
        </div>
      </div>
      {p && (
        <div className="card">
          <div className="card-head">
            <h2>{s.name} {p.label} <span style={{ color: "var(--muted)", fontWeight: 500 }}>· 등판 {p.outings}회{p.pitches_total != null && ` · 시즌 ${p.pitches_total}구`}{p.max_pitches != null && ` · 한 경기 최다 ${p.max_pitches}구`}{p.max_7d != null && ` · 7일 최대 ${fmt.num(p.max_7d, 0)}구`}</span></h2>
            <span><span className={`light ${STATUS_CLASS[p.rule_status]}`} style={{ marginRight: 6 }}>규정 {p.rule_status}</span><span className={`light ${LOAD_CLASS[p.load_status]}`}>ACWR {p.load_status}</span></span>
          </div>
          <div className="chart-title">일별 투구 수와 7일 합 <small>막대 = 그날 투구 수, 검은 선 = 그날까지 7일 합{rule && ` · 해외 규정 비교: 7일 합이 ${rule.max_pitches}구를 넘은 날 ${days.filter((d) => d.over).length}일`}</small></div>
          <ResponsiveContainer width="100%" height={260}>
            <ComposedChart data={days} margin={{ top: 10, right: 12, left: 0, bottom: 0 }} syncId="hs-season">
              <CartesianGrid vertical={false} stroke={GRID} />
              <XAxis dataKey="date" ticks={monthTicks} tickFormatter={fmt.date} tick={TICK} axisLine={{ stroke: GRID }} tickLine={false} />
              <YAxis tick={TICK} width={36} axisLine={false} tickLine={false} />
              <Tooltip content={<ChartTip render={(payload) => <DayTip d={payload[0].payload} />} />} cursor={{ fill: "rgba(20,20,19,0.04)" }} />
              <Bar dataKey="pitches" name="투구 수" fill="var(--velo)" barSize={5} radius={[2, 2, 0, 0]} isAnimationActive={false} />
              <Line type="stepAfter" dataKey="sum_7d" name="7일 합" stroke="var(--ink)" strokeWidth={1.5} dot={false} connectNulls isAnimationActive={false} />
              {rule && <ReferenceLine y={rule.max_pitches} stroke="var(--warn)" strokeDasharray="4 4" label={limitLabel(`7일 ${rule.max_pitches}구`)} />}
              {p.violations.filter((v) => v.rule !== "unknown").map((v) => <ReferenceLine key={v.date + v.rule} x={v.date} stroke="var(--alarm)" label={{ value: "위반", position: "insideTop", ...LABEL, fill: "var(--alarm)" }} />)}
            </ComposedChart>
          </ResponsiveContainer>
          <div className="chart-title">ACWR <small>최근 7일 합 ÷ 그 앞 3주 주평균 · 점선 {data.acwr_flag} · 4 이상은 잘림(값은 마우스를 올리면 보임)</small></div>
          <ResponsiveContainer width="100%" height={150}>
            <ComposedChart data={days} margin={{ top: 10, right: 12, left: 0, bottom: 0 }} syncId="hs-season">
              <CartesianGrid vertical={false} stroke={GRID} />
              <XAxis dataKey="date" ticks={monthTicks} tickFormatter={fmt.date} tick={TICK} axisLine={{ stroke: GRID }} tickLine={false} />
              <YAxis domain={[0, 4]} allowDataOverflow ticks={[0, 1, 2, 3, 4]} tick={TICK} width={36} axisLine={false} tickLine={false} />
              <Tooltip content={<ChartTip render={(payload) => <DayTip d={payload[0].payload} />} />} cursor={{ stroke: "var(--line-2)" }} />
              <Line type="monotone" dataKey="acwr" name="ACWR" stroke="var(--warn)" strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
              <ReferenceLine y={data.acwr_flag} stroke="var(--alarm)" strokeDasharray="4 4" label={limitLabel(`ACWR ${data.acwr_flag}`)} />
            </ComposedChart>
          </ResponsiveContainer>
          <p className="caption">ACWR은 첫 경기부터 4주가 쌓인 뒤부터 계산하며, 3주 동안 거의 던지지 않다가 등판하면 분모가 작아 크게 튑니다 — 그래서 고교처럼 띄엄띄엄 던지는 일정에서는 7일 합·연투·의무 휴식일을 함께 봐야 합니다.</p>
          <GamesTable p={p} withCompetition />
          <ViolationsTable p={p} />
        </div>
      )}
      <p className="note">
        출처: {ds.source}. 지역 밖 상대 팀의 투수는 기록이 일부뿐이라 넣지 않았습니다. 상세 기록이 공개되지 않은 경기({ds.no_detail_games.length}경기)는 선발 투수만 '투구 수 미공개'로 들어갑니다.
        한계: 공식 경기 투구 수만 반영되고 연습·불펜 투구는 빠집니다. 고교에는 공식 부상 기록이 없어 이 화면은 '규정이 보지 못하는 부하를 보여 주는 현황판'이지 탐지 성능을 검증한 것이 아닙니다.
        규정 수치(하루 {kbsa.daily_max}구, 휴식일 표 {kbsa.rest_table.map(([u, r]) => `${u}구 이하 ${r}일`).join(" · ")})와 ACWR 기준 {data.acwr_flag}은 설정 파일 값입니다.
      </p>
    </div>
  );
}

/* ---------- 대회 모드: 2025 전국체전 18세 이하부 ---------- */

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

function cumulativeLight(p) {
  if (p.pitches_total == null) return { cls: "base", text: "누적 모름" };
  return { cls: p.pitches_total >= 150 ? "alarm" : p.pitches_total >= 100 ? "warn" : "ok", text: `누적 ${p.pitches_total}구${p.pitches_total >= 150 ? " · 높음" : p.pitches_total >= 100 ? " · 주의" : ""}` };
}

function TournamentBoard({ data, index, selector, params, setParams }) {
  const { schools, s, pitchers, p, setSchool, setCode } = useSelection(data, params, setParams);
  const { dataset: ds, totals, kbsa } = data;
  const days = useMemo(() => { const dates = data.games.map((g) => g.date).sort(); return dateRange(dates[0], dates[dates.length - 1]); }, [data]);
  const gamesByDate = useMemo(() => Object.fromEntries(days.map((d) => [d, data.games.filter((g) => g.date === d && g.teams.includes(s?.name))])), [days, data, s]);
  const chart = days.map((d) => { const g = p?.games.find((x) => x.date === d); return { date: d, pitches: g ? g.pitches : null, unknown: g && g.pitches == null ? kbsa.daily_max : null, cum: g ? g.cum_pitches : null }; });
  return (
    <div className="page">
      <h1>고교 투구수 현황판 <span className="badge real">실제 기록 · {ds.short} 18세 이하부</span></h1>
      {selector}
      <p className="lead">
        {ds.name} ({ds.dates}, 15개교 {ds.games}경기 단판 토너먼트). KBSA 기록실의 경기별 투수 기록(등판 구분·이닝·투구수)을 그대로 옮겼고, {index.labels}.
        신호등 두 개는 서로 다른 뜻입니다. <b>규정</b>은 KBSA 투구수 규정(하루 {kbsa.daily_max}구, 투구 수별 의무 휴식일, 3일 연속 등판 금지)을 지켰는지,
        <b> 누적</b>은 대회 7일 동안 던진 투구 수의 합입니다(100구 이상 '주의', 150구 이상 '높음' — 규정이 아니라 하루 상한 105구의 약 1배·1.5배라는 서술적 눈금. ACWR은 4주 자료가 있어야 해서 단기 대회에서는 계산하지 않습니다).
      </p>
      <div className="kpi">
        <div><div className="v">{ds.games}<span className="sub"> 경기</span></div><div className="l">상세 기록 {ds.games - ds.no_detail_games.length}경기 · {ds.no_detail_games.length}경기는 선발만 공개(투구 수 모름)</div></div>
        <div><div className="v">{totals.pitchers}<span className="sub"> 명</span></div><div className="l">등판 투수 · 등판 {totals.outings}회 · 3경기 이상 등판 {totals.pitchers_3plus_games}명</div></div>
        <div><div className="v">{totals.violations}<span className="sub"> 건</span></div><div className="l">규정 위반 · 판정 불가 {totals.unknown_outings}등판</div></div>
        <div><div className="v">{totals.back_to_back}<span className="sub"> 건</span></div><div className="l">연투(이튿날 다시 등판) · 의무 휴식일 뒤 첫날 등판 {totals.min_rest_exact}건</div></div>
        <div><div className="v">{totals.games_91plus}<span className="sub"> 등판</span></div><div className="l">91구 이상(휴식 4일 구간) · 100구 이상 {totals.games_100plus}등판 · 최다 {kbsa.daily_max}구</div></div>
        <div><div className="v">{totals.max_total}<span className="sub"> 구</span></div><div className="l">한 투수의 대회 누적 최다 투구 수</div></div>
      </div>
      <div className="toolbar">
        <label><span>학교</span>
          <select value={s?.code || ""} onChange={(e) => setSchool(e.target.value)}>
            {schools.map((x) => <option key={x.code} value={x.code}>{x.name} · {x.games}경기 · 투수 {x.pitchers.length}명</option>)}
          </select>
        </label>
        <span className="caption" style={{ margin: 0 }}>경기 수가 많은 학교(결승 진출 4경기)부터 정렬. 투수는 누적 투구 수가 많은 순.</span>
      </div>
      <div className="grid2 hs-grid">
        <div className="card">
          <h2>{s?.name} 투수 <span style={{ color: "var(--muted)", fontWeight: 500 }}>· 규정 / 누적</span></h2>
          <div className="list">
            {pitchers.map((x) => {
              const load = cumulativeLight(x);
              return (
                <button key={x.code} className={x.code === p?.code ? "on" : ""} onClick={() => setCode(x.code)}>
                  <span className="code">{x.label}</span>
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
          <h2>{s?.name} 대회 등판 달력 <span style={{ color: "var(--muted)", fontWeight: 500 }}>· 칸의 숫자는 그날 투구 수</span></h2>
          <div className="tbl-wrap">
            <table className="heat">
              <thead>
                <tr><th>투수</th>{days.map((d) => <th key={d}>{d.slice(5).replace("-", "/")}<small>{gamesByDate[d]?.length ? gamesByDate[d].map((g) => g.round).join("·") : ""}</small></th>)}</tr>
              </thead>
              <tbody>
                {pitchers.map((x) => (
                  <tr key={x.code} className={x.code === p?.code ? "hl" : ""} onClick={() => setCode(x.code)}>
                    <th>{x.label}</th>
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
            <h2>{s.name} {p.label} <span style={{ color: "var(--muted)", fontWeight: 500 }}>· 등판 {p.outings}회{p.pitches_total != null && ` · 누적 ${p.pitches_total}구`}{p.max_pitches != null && ` · 한 경기 최다 ${p.max_pitches}구`}</span></h2>
            <span className={`light ${STATUS_CLASS[p.rule_status]}`}>규정 {p.rule_status}</span>
          </div>
          <div className="grid2 hs-detail">
            <GamesTable p={p} />
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
          <ViolationsTable p={p} />
        </div>
      )}
      <p className="note">
        출처: {ds.source}. 상세 기록이 공개되지 않은 경기({ds.no_detail_games.map((n) => `${n}경기`).join(", ")})는 선발 투수 두 명만 '투구 수 미공개'로 들어가 있고, 그날 등판한 다른 투수는 기록에 없습니다.
        한계: 공식 경기 투구 수만 반영되고 대회 전 주말리그·연습 투구는 빠집니다. 고교에는 공식 부상 기록이 없어 이 화면은 '규정이 보지 못하는 부하를 보여 주는 현황판'이지 탐지 성능을 검증한 것이 아닙니다.
        규정 수치(하루 {kbsa.daily_max}구, 휴식일 표 {kbsa.rest_table.map(([u, r]) => `${u}구 이하 ${r}일`).join(" · ")})는 설정 파일 값입니다.
      </p>
    </div>
  );
}

/* ---------- 예비: 입력 양식(data/highschool/input.xlsx) 또는 가상 자료가 들어온 옛 형식 ---------- */

function SeasonLegacy({ data }) {
  const s = data.schools?.[0];
  const p = s?.pitchers?.[0];
  if (!s || !p) return <div className="placeholder">고교 자료가 없습니다.</div>;
  return (
    <div className="page">
      <h1>고교 투구수 현황판 {data.synthetic && <span className="badge synthetic">가상 데이터</span>}</h1>
      <p className="lead">{data.season} 시즌 고교 {data.schools.length}곳. 학교는 S01~, 투수는 S01-P03 같은 가명 코드만 씁니다.</p>
      <div className="card">
        <h2>{s.code} {p.code}</h2>
        <ResponsiveContainer width="100%" height={270}>
          <ComposedChart data={p.days} margin={{ top: 12, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke={GRID} />
            <XAxis dataKey="date" tickFormatter={fmt.date} tick={TICK} axisLine={{ stroke: GRID }} tickLine={false} minTickGap={24} />
            <YAxis yAxisId="p" tick={TICK} width={34} axisLine={false} tickLine={false} />
            <YAxis yAxisId="a" orientation="right" domain={[0, 4]} allowDataOverflow tick={TICK} width={34} axisLine={false} tickLine={false} />
            <Tooltip {...TIP_STYLE} />
            <Bar yAxisId="p" dataKey="pitches" name="투구 수" fill="var(--velo)" isAnimationActive={false} />
            <Line yAxisId="a" type="monotone" dataKey="acwr" name="ACWR" stroke="var(--warn)" strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
            <ReferenceLine yAxisId="a" y={data.acwr_flag} stroke="var(--alarm)" strokeDasharray="4 4" />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
