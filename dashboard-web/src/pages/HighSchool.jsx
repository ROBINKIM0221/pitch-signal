import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Bar, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis, Legend } from "recharts";
import { fmt, useJson } from "../lib/data.js";
import { ChartTip, GRID, LABEL, LEGEND_STYLE, TICK, TIP_STYLE, limitLabel } from "../lib/chart.jsx";
import { addDays, dailySeries, dateRange } from "../lib/load.js";
import { availability, nextEligible, requiredRest } from "../lib/rules.js";

const RULE_NAME = { daily_max: "하루 105구 초과", rest: "의무 휴식일 미준수", three_days: "3일 연속 등판", unknown: "투구 수 기록 없음(판정 불가)" };
const LOAD_CLASS = { "보통": "ok", "주의": "warn", "높음": "alarm", "계산 불가": "base" };
const STATUS_CLASS = { "준수": "ok", "위반": "alarm", "판정 불가": "base" };

const DEFAULT_REGION = "경기";                                   // 공모전 지역

export default function HighSchool() {
  const { data: index } = useJson("highschool.json");
  const [params, setParams] = useSearchParams();
  const dataset = index?.datasets?.find((d) => d.key === params.get("d")) || index?.datasets?.[0];
  // 시즌(전국) 데이터셋은 권역별 파일: 주소 ?r=권역 키, 없으면 경기 권역
  const region = dataset?.regions ? (dataset.regions.find((r) => r.key === params.get("r")) || dataset.regions.find((r) => r.name === DEFAULT_REGION) || dataset.regions[0]) : null;
  const file = dataset ? (region ? region.file : dataset.file) : null;
  const { data } = useJson(file);
  if (!index) return <div className="placeholder">고교 현황판 자료를 읽는 중…</div>;
  if (index.synthetic || !index.datasets?.length) return <SeasonLegacy data={index} />;
  const pick = (next) => setParams({ d: next }, { replace: true });
  const selector = (
    <div className="seg" role="tablist" aria-label="자료" style={{ marginBottom: 14 }}>
      {index.datasets.map((d) => <button key={d.key} role="tab" className={`btn ${d.key === dataset.key ? "on" : ""}`} aria-selected={d.key === dataset.key} onClick={() => pick(d.key)}>{d.short} · {d.mode === "season" ? "전국 시즌" : "7일 대회"}</button>)}
    </div>
  );
  if (!data) return <div className="page"><h1>고교 투구수 현황판</h1>{selector}<div className="placeholder">자료를 읽는 중…</div></div>;
  const common = { data, index, dataset, region, selector, params, setParams };
  return data.mode === "tournament" ? <TournamentBoard {...common} /> : <SeasonBoard {...common} />;
}

/* ---------- 공통 조각 ---------- */

function useSelection(data, params, setParams, region) {
  const schools = data.schools;
  const s = schools.find((x) => x.code === params.get("s")) || schools[0];
  const pitchers = s?.pitchers || [];
  const p = pitchers.find((x) => x.code === params.get("p")) || pitchers[0];
  const keep = { d: params.get("d"), ...(region ? { r: region.key } : {}) };
  const setSchool = (next) => setParams({ ...keep, s: next }, { replace: true });
  const setCode = (next) => setParams({ ...keep, s: s.code, p: next }, { replace: true });
  return { schools, s, pitchers, p, setSchool, setCode, keep };
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
      <div>7일 합 {fmt.num(d.sum_7d, 0)}구</div>
    </>
  );
}

const CAT = { K: ["삼진", "k"], BB: ["4구", "bb"], HBP: ["사구", "bb"], H: ["안타", "h"], HR: ["홈런", "hr"], OUT: ["아웃", "out"], E: ["실책 출루", "e"], SAC: ["희생", "out"], FC: ["야선", "e"], TB: ["승부치기 주자", "tb"] };

/** 등판 흐름 요약: 타석·삼진·4사구·안타·4사구가 2개 이상 몰린 이닝·폭투류. flow 항목 = [이닝, 결과, 범주, (사건들)] */
function flowSummary(flow) {
  const walks = {};
  let k = 0, bb = 0, h = 0, wild = 0;
  for (const [inn, , cat, ev] of flow) {
    if (cat === "K") k++;
    if (cat === "BB" || cat === "HBP") { bb++; walks[inn] = (walks[inn] || 0) + 1; }
    if (cat === "H" || cat === "HR") h++;
    wild += (ev || []).filter((e) => ["폭투", "보크", "포일"].includes(e)).length;
  }
  return { pa: flow.length, k, bb, h, wild, walkInnings: Object.entries(walks).filter(([, n]) => n >= 2).map(([i]) => Number(i)) };
}

/** 이닝별 타석 띠: 결과 글자를 범주 색의 작은 칩으로. 사건(폭투·도루 등)은 툴팁에. */
function FlowStrip({ flow }) {
  const innings = [...new Set(flow.map((f) => f[0]))];
  return (
    <div className="flow">
      {innings.map((inn) => (
        <span key={inn} className="flow-inn">
          <b>{inn}회</b>
          {flow.filter((f) => f[0] === inn).map(([, res, cat, ev], i) => <i key={i} className={`pa ${CAT[cat]?.[1] || "out"}`} title={`${CAT[cat]?.[0] || cat}${ev?.length ? ` · ${ev.join(", ")}` : ""}`}>{res}</i>)}
        </span>
      ))}
    </div>
  );
}

function BallTip({ d }) {
  return (
    <>
      <div><b>{fmt.date(d.date)}</b> · {d.opponent}</div>
      <div>볼 비율(추정) <b>{fmt.num(d.ball, 0)}%</b> · 읽은 표시 {d.marks}개 / 공식 {d.pitches ?? "?"}구</div>
      {d.flag && <div style={{ color: "var(--warn)" }}>평소보다 볼이 많았던 등판</div>}
    </>
  );
}

/** 등판별 볼 비율(추정): 점 하나 = 검산을 통과한 등판, 점선 = 시즌 볼 비율, 주황 점 = '평소보다 볼 많음'. 원인은 해석하지 않는다. */
function BallChart({ p }) {
  const pts = p.games.filter((g) => g.ball_pct != null).map((g) => ({
    date: g.date, x: g.date.slice(5).replace("-", "/"), ball: 100 * g.ball_pct, marks: g.ball_marks, flag: !!g.ball_flag, opponent: g.opponent, pitches: g.pitches,
  }));
  if (pts.length < 2) return null;
  const Dot = ({ cx, cy, payload }) => (cx == null ? null : (
    <circle cx={cx} cy={cy} r={payload.flag ? 6 : 4.5} fill={payload.flag ? "var(--warn)" : "var(--ink-2)"} stroke="var(--card)" strokeWidth={2} />
  ));
  return (
    <>
      <div className="chart-title">등판별 볼 비율(추정) <small>점 = 기록지에서 읽은 그 등판의 볼 비율, 점선 = 시즌 {p.ball_season != null ? `${fmt.num(100 * p.ball_season, 1)}%` : "—"}, 주황 점 = 평소보다 볼이 많았던 등판</small></div>
      <ResponsiveContainer width="100%" height={200}>
        <ComposedChart data={pts} margin={{ top: 10, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke={GRID} />
          <XAxis dataKey="x" tick={TICK} interval="preserveStartEnd" />
          <YAxis domain={[0, 80]} ticks={[0, 20, 40, 60, 80]} tick={TICK} unit="%" width={44} />
          <Tooltip content={<ChartTip render={(payload) => <BallTip d={payload[0].payload} />} />} cursor={{ stroke: "var(--line-2)" }} />
          {p.ball_season != null && <ReferenceLine y={100 * p.ball_season} stroke="var(--muted)" strokeDasharray="4 4" />}
          <Line dataKey="ball" stroke="var(--line-2)" strokeWidth={1.5} dot={<Dot />} activeDot={{ r: 7 }} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </>
  );
}

/** 기록지 판독 볼 비율(추정) 칸: 안 읽음 — / 읽었지만 검산 미달 / 비율과 '평소보다 볼 많음'. */
function BallCell({ g }) {
  if (g.ball_marks == null) return <span style={{ color: "var(--muted)" }}>—</span>;
  if (g.ball_pct == null) {
    return <span className="light base" title={`기록지에서 읽은 표시 ${g.ball_marks}개가 공식 투구 수 ${g.pitches ?? "?"}구와 15% 넘게 달라 볼 비율을 보여 주지 않습니다`}>검산 미달</span>;
  }
  return (
    <>
      {fmt.num(100 * g.ball_pct, 0)}%
      {g.ball_flag && <span className="light warn" style={{ marginLeft: 6 }} title="그 투수의 다른 등판보다 볼 비율이 뚜렷이 높았던 등판입니다(읽은 투구 수를 감안한 기준, 40구 이상만). 원인은 해석하지 않습니다.">평소보다 볼 많음</span>}
    </>
  );
}

function GamesTable({ p, withCompetition }) {
  const [open, setOpen] = useState(null);
  const hasResults = p.games.some((g) => g.batters != null);
  const hasBall = p.games.some((g) => g.ball_marks != null);
  return (
    <div className="tbl-wrap">
      <table className="tbl">
        <thead><tr><th>날짜</th><th>{withCompetition ? "대회" : "라운드"}</th><th>상대</th><th>등판</th><th className="num">이닝</th><th className="num">투구 수</th>{hasResults && <><th className="num">타자</th><th className="num">삼진</th><th className="num">4사구</th><th className="num">피안타</th><th className="num">투구/타자</th></>}{hasBall && <th className="num" title="협회 기록지 사진에서 공마다 볼·볼 아님을 읽은 추정값">볼 비율(추정)</th>}<th>직전 등판 뒤</th><th className="num">누적</th>{hasResults && <th>흐름</th>}</tr></thead>
        <tbody>
          {p.games.map((g) => {
            const sum = g.flow ? flowSummary(g.flow) : null;
            return [
              <tr key={g.game_no} className={open === g.game_no ? "hl" : ""}>
                <td>{g.date.slice(5).replace("-", "/")}</td><td>{withCompetition ? g.competition : g.round}</td><td>{g.opponent}</td>
                <td>{g.role}{g.result !== "-" && <span style={{ color: "var(--muted)" }}> · {g.result}</span>}</td>
                <td className="num">{innings(g.outs)}</td>
                <td className="num">{g.pitches == null ? <span className="light base">미공개</span> : g.pitches}</td>
                {hasResults && <>
                  <td className="num">{g.batters ?? "—"}</td><td className="num">{g.k ?? "—"}</td>
                  <td className="num">{g.bb_hbp ?? "—"}{sum?.walkInnings.length > 0 && <span className="light warn" style={{ marginLeft: 6 }} title={`4구·사구 2개 이상 몰린 이닝: ${sum.walkInnings.map((i) => `${i}회`).join(", ")}`}>{sum.walkInnings.map((i) => `${i}회`).join("·")} 몰림</span>}</td>
                  <td className="num">{g.hits ?? "—"}{g.hr > 0 && <span style={{ color: "var(--muted)" }}> (홈런 {g.hr})</span>}</td>
                  <td className="num">{g.pitches != null && g.batters ? fmt.num(g.pitches / g.batters, 1) : "—"}</td>
                </>}
                {hasBall && <td className="num"><BallCell g={g} /></td>}
                <td>{restText(g)}</td>
                <td className="num">{g.cum_pitches == null ? "—" : g.cum_pitches}</td>
                {hasResults && <td>{g.flow ? <button className="pill" onClick={() => setOpen(open === g.game_no ? null : g.game_no)}>{open === g.game_no ? "닫기" : "타석별 보기"}</button> : <span style={{ color: "var(--muted)" }}>—</span>}</td>}
              </tr>,
              open === g.game_no && g.flow && (
                <tr key={`${g.game_no}-flow`} className="flow-row">
                  <td colSpan={16} style={{ whiteSpace: "normal" }}>
                    <FlowStrip flow={g.flow} />
                    <div className="caption" style={{ marginTop: 6 }}>타석 {sum.pa} · 삼진 {sum.k} · 4구+사구 {sum.bb} · 안타 {sum.h}{sum.wild > 0 && ` · 폭투·보크·포일 ${sum.wild}`}{sum.walkInnings.length > 0 && ` · 4사구가 몰린 이닝 ${sum.walkInnings.map((i) => `${i}회`).join(", ")}`} — 상대 타격표의 타석을 투수 타자 수대로 배정해 복원한 순서입니다(합이 맞는 경기만).</div>
                  </td>
                </tr>
              ),
            ];
          })}
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

/* ---------- 시즌 모드: 2025 전국 고교 공식 경기 (KBSA 규정 + 절대량 부하 신호등) ---------- */

function SeasonBoard({ data, index, dataset, region, selector, params, setParams }) {
  const { schools, s, pitchers, p, setSchool, setCode, keep } = useSelection(data, params, setParams, region);
  const { dataset: ds, totals, kbsa } = data;
  const nation = dataset.totals;                                   // 전국 합계 (목록 파일)
  const setRegion = (next) => setParams({ d: dataset.key, r: next }, { replace: true });
  const jumpToSchool = (name) => {                                 // 검색: 학교 이름 → 권역·학교
    const hit = dataset.schools.find((x) => x.name === name);
    if (hit) setParams({ d: dataset.key, r: hit.region, s: hit.code }, { replace: true });
  };
  const foreign = params.get("f") && data.foreign_rules[params.get("f")] ? params.get("f") : "none";
  const rule = foreign !== "none" ? data.foreign_rules[foreign] : null;
  const days = useMemo(() => (p && s ? dailySeries(p.games.map((g) => ({ date: g.date, pitches: g.pitches })), s.start, s.end, { acute_days: 7, chronic_days: 21 }) : [])
    .map((d) => ({ ...d, over: rule ? (d.sum_7d != null && d.sum_7d > rule.max_pitches) : false })), [p, s, data, rule]);
  const monthTicks = useMemo(() => days.filter((d) => d.date.endsWith("-01")).map((d) => d.date), [days]);   // 두 패널의 눈금을 매달 1일로 맞춘다
  const ruleCounts = Object.entries(totals.violations_by_rule).filter(([k]) => k !== "unknown").map(([k, v]) => `${RULE_NAME[k] || k} ${v}`).join(" · ");
  return (
    <div className="page">
      <h1>고교 투구수 현황판 <span className="badge real">실제 기록 · {dataset.short} · {ds.region} 권역</span></h1>
      {selector}
      <p className="lead">
        {dataset.name}: 2025 고교(18세 이하부) 37개 리그 {dataset.games}경기 전부 — 전국 {nation.schools}개 팀(주말리그 참가교, U-18 클럽 포함) · 투수 {nation.pitchers}명 · 등판 {nation.outings}회 · 규정 위반 {nation.violations}건 · 시즌 500구 이상 {nation.pitchers_season_500}명.
        {" "}권역은 주말리그 참가 리그로 나눴고, 지금 보는 권역은 <b>{ds.region}</b>({totals.schools}개 팀, {ds.dates} {ds.games}경기)입니다. {index.labels}.
        신호등 두 개는 서로 다른 뜻입니다. <b>규정</b>은 KBSA 투구수 규정(하루 {kbsa.daily_max}구, 투구 수별 의무 휴식일, 3일 연속 등판 금지)을 지켰는지,
        <b> 누적 부하</b>는 규정에 없는 절대량 두 가지 — 7일 투구 수 합(주의 {data.load_lights.sum7.caution}구·높음 {data.load_lights.sum7.high}구)과 3일 안 두 등판의 합(주의 {data.load_lights.pair3.caution}구·높음 {data.load_lights.pair3.high}구) — 을 넘은 적이 있는지입니다.
        기준값은 어떤 규정도 아니고 전국 2025 자료의 분위수(7일 합 상위 5%·2%)에 맞춘 서술적 눈금입니다. ACWR(최근 7일 ÷ 그 앞 3주 주평균)은 주말에만 던지는 고교 일정에서 분모가 작아 튀어 쓰지 않습니다.
      </p>
      <div className="toolbar">
        <label><span>권역</span>
          <select value={region?.key || ""} onChange={(e) => setRegion(e.target.value)}>
            {dataset.regions.map((r) => <option key={r.key} value={r.key}>{r.name} · {r.schools}팀 · 투수 {r.pitchers}명{r.violations ? ` · 위반 ${r.violations}` : ""}</option>)}
          </select>
        </label>
        <label><span>학교 검색</span>
          <input list="hs-schools" placeholder="학교 이름 (전국)" onChange={(e) => jumpToSchool(e.target.value)} style={{ height: 34, padding: "0 10px", border: "1px solid var(--line-2)", borderRadius: 9, background: "var(--card)", minWidth: 200 }} />
          <datalist id="hs-schools">{dataset.schools.map((x) => <option key={x.code} value={x.name}>{`${dataset.regions.find((r) => r.key === x.region)?.name ?? ""} · ${x.games}경기`}</option>)}</datalist>
        </label>
      </div>
      <div className="kpi">
        <div><div className="v">{totals.schools}<span className="sub"> 팀</span></div><div className="l">투수 {totals.pitchers}명 · 등판 {totals.outings}회 · {totals.games}경기 (투구 수 미공개 {totals.unknown_outings}등판)</div></div>
        <div><div className="v">{totals.violations}<span className="sub"> 건</span></div><div className="l">규정 위반 · 투수 {totals.violating_pitchers}명{ruleCounts && ` (${ruleCounts})`}</div></div>
        <div><div className="v"><span style={{ color: "var(--alarm)" }}>{totals.pitchers_load_high}</span> · <span style={{ color: "var(--warn)" }}>{totals.pitchers_load_caution}</span><span className="sub"> 명</span></div><div className="l">누적 부하 높음 · 주의 (7일 합 {data.load_lights.sum7.high}/{data.load_lights.sum7.caution}구, 3일 안 두 등판 합 {data.load_lights.pair3.high}/{data.load_lights.pair3.caution}구)</div></div>
        <div><div className="v">{totals.compliant_with_load}<span className="sub"> 명</span></div><div className="l">규정은 모두 지켰지만 누적 부하 표시(높음·주의)가 있던 투수</div></div>
        <div><div className="v">{totals.pitchers_7d_150}<span className="sub"> 명</span></div><div className="l">7일 합 {data.load_lights.sum7.high}구 이상을 경험한 투수 · 시즌 500구 이상 {totals.pitchers_season_500}명</div></div>
        <div><div className="v">{totals.pairs3_70}<span className="sub"> 쌍</span></div><div className="l">3일 안 두 등판 합 {data.load_lights.pair3.caution}구 이상 · {data.load_lights.pair3.high}구 이상 {totals.pairs3_100}쌍 (규정상 허용되는 연투·하루 쉰 등판)</div></div>
        <div><div className="v">{totals.back_to_back}<span className="sub"> 건</span></div><div className="l">연투(이튿날 다시 등판) · 의무 휴식일 뒤 첫날 등판 {totals.min_rest_exact}건</div></div>
        <div><div className="v">{totals.games_91plus}<span className="sub"> 등판</span></div><div className="l">91구 이상(휴식 4일 구간) · 100구 이상 {totals.games_100plus}등판</div></div>
        {totals.ball_read != null && <div><div className="v">{totals.ball_outings}<span className="sub"> 등판</span></div><div className="l">기록지 판독 볼 비율(추정)을 보여 주는 등판 (기록지를 읽은 등판 {totals.ball_read}) · 평소보다 볼이 많았던 등판 {totals.ball_flags}</div></div>}
      </div>
      <div className="toolbar">
        <label><span>학교</span>
          <select value={s?.code || ""} onChange={(e) => setSchool(e.target.value)}>
            {schools.map((x) => <option key={x.code} value={x.code}>{x.name} · {x.games}경기 · 투수 {x.pitchers.length}명</option>)}
          </select>
        </label>
        <label><span>해외 규정 비교</span>
          <select value={foreign} onChange={(e) => setParams({ ...keep, s: s.code, p: p?.code, f: e.target.value }, { replace: true })}>
            <option value="none">없음</option>
            {Object.entries(data.foreign_rules).map(([k, v]) => <option key={k} value={k}>{k === "japan" ? "일본" : k} {v.window_days}일 {v.max_pitches}구</option>)}
          </select>
        </label>
        <span className="caption" style={{ margin: 0 }}>경기 수가 많은 팀부터. 투수는 시즌 투구 수가 많은 순.</span>
      </div>
      {s && (
        <div className="kpi">
          <div><div className="v">{s.pitchers.length}<span className="sub"> 명</span></div><div className="l">{s.name} 투수 · {s.games}경기 · 팀 투구 수 {s.pitches_total ?? "—"}</div></div>
          <div><div className="v">{s.violations}<span className="sub"> 건</span></div><div className="l">규정 위반 · 투수 {s.violating_pitchers}명</div></div>
          <div><div className="v"><span style={{ color: "var(--alarm)" }}>{s.load_high}</span> · <span style={{ color: "var(--warn)" }}>{s.load_caution}</span><span className="sub"> 명</span></div><div className="l">누적 부하 높음 · 주의</div></div>
          <div><div className="v">{s.compliant_with_load}<span className="sub"> 명</span></div><div className="l">규정은 지켰지만 누적 부하 표시가 있던 투수</div></div>
        </div>
      )}
      <div className="grid2">
        <div className="card">
          <h2>{s?.name} 투수 <span style={{ color: "var(--muted)", fontWeight: 500 }}>· 규정 / 누적 부하</span></h2>
          <div className="list">
            {pitchers.map((x) => (
              <button key={x.code} className={x.code === p?.code ? "on" : ""} onClick={() => setCode(x.code)} title={x.load_reasons.join(" · ") || undefined}>
                <span className="code">{x.label}</span>
                <span className={`light ${STATUS_CLASS[x.rule_status]}`}>규정 {x.rule_status}</span>
                <span className={`light ${LOAD_CLASS[x.load_status]}`}>부하 {x.load_status}</span>
                <span className="tags"><span className="pill">{x.outings}등판 · {x.pitches_total ?? "—"}구</span>{x.max_7d != null && <span className="pill">7일 최대 {fmt.num(x.max_7d, 0)}구</span>}{x.max_pair3 != null && <span className="pill">3일 쌍 최대 {fmt.num(x.max_pair3, 0)}구</span>}{x.ball_season != null && <span className="pill" title="기록지 판독 볼 비율(추정), 검산 통과 등판 합">볼 {fmt.num(100 * x.ball_season, 0)}%</span>}{x.ball_flags > 0 && <span className="pill" title="평소보다 볼이 많았던 등판 수 (40구 이상)"><span className="dot" style={{ background: "var(--warn)" }} />볼 많음 {x.ball_flags}</span>}</span>
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
      {s && <Planner school={s} games={data.games} kbsa={kbsa} lights={data.load_lights} onPick={setCode} picked={p?.code} />}
      {p && (
        <div className="card">
          <div className="card-head">
            <h2>{s.name} {p.label} <span style={{ color: "var(--muted)", fontWeight: 500 }}>· 등판 {p.outings}회{p.pitches_total != null && ` · 시즌 ${p.pitches_total}구`}{p.max_pitches != null && ` · 한 경기 최다 ${p.max_pitches}구`}{p.max_7d != null && ` · 7일 최대 ${fmt.num(p.max_7d, 0)}구`}</span></h2>
            <span><span className={`light ${STATUS_CLASS[p.rule_status]}`} style={{ marginRight: 6 }}>규정 {p.rule_status}</span><span className={`light ${LOAD_CLASS[p.load_status]}`} title={p.load_reasons.join(" · ") || undefined}>부하 {p.load_status}</span></span>
          </div>
          {p.load_reasons.length > 0 && <p className="caption" style={{ marginTop: 0 }}>부하 표시 이유: {p.load_reasons.join(" · ")}</p>}
          {p.batters != null && p.batters > 0 && (
            <p className="caption" style={{ marginTop: 0 }}>
              <b>시즌 등판 결과</b> (맥락 정보 — 신호가 아닙니다): 타자 {fmt.num(p.batters, 0)}명 · 삼진율 {fmt.num(100 * (p.k ?? 0) / p.batters, 1)}% · 4사구율 {fmt.num(100 * (p.bb_hbp ?? 0) / p.batters, 1)}% · 피안타 {p.hits ?? "—"}(홈런 {p.hr ?? 0}){p.p_per_pa != null && ` · 투구/타자 ${fmt.num(p.p_per_pa, 2)}`} · 타석별 흐름이 복원된 등판 {p.flow_games}/{p.outings}
            </p>
          )}
          {p.games.some((g) => g.ball_marks != null) && (
            <p className="caption" style={{ marginTop: 0 }}>
              <b>제구 (기록지 판독, 추정)</b>: 볼 비율 {p.ball_season != null ? `${fmt.num(100 * p.ball_season, 1)}%` : "—"} · 볼 비율을 보여 주는 등판 {p.ball_outings}/{p.outings}{p.ball_flags > 0 && ` · 평소보다 볼이 많았던 등판 ${p.ball_flags}`}
              {" "}— 협회 기록지 사진에서 공마다 볼·볼 아님을 읽은 값입니다. 읽은 표시 수가 공식 투구 수와 15% 넘게 다른 등판은 빼고, '평소보다 볼 많음'은 40구 이상 등판만 그 투수의 다른 등판과 비교합니다. 원인(피로·부상 등)은 해석하지 않습니다.
            </p>
          )}
          <BallChart p={p} />
          <div className="chart-title">일별 투구 수와 7일 합 <small>막대 = 그날 투구 수, 검은 선 = 그날까지 7일 합, 점선 = 주의 {data.load_lights.sum7.caution}구·높음 {data.load_lights.sum7.high}구{rule && ` · 해외 규정 비교: 7일 합이 ${rule.max_pitches}구를 넘은 날 ${days.filter((d) => d.over).length}일`}</small></div>
          <ResponsiveContainer width="100%" height={300}>
            <ComposedChart data={days} margin={{ top: 10, right: 12, left: 0, bottom: 0 }} syncId="hs-season">
              <CartesianGrid vertical={false} stroke={GRID} />
              <XAxis dataKey="date" ticks={monthTicks} tickFormatter={fmt.date} tick={TICK} axisLine={{ stroke: GRID }} tickLine={false} />
              <YAxis tick={TICK} width={36} axisLine={false} tickLine={false} />
              <Tooltip content={<ChartTip render={(payload) => <DayTip d={payload[0].payload} />} />} cursor={{ fill: "rgba(20,20,19,0.04)" }} />
              <Bar dataKey="pitches" name="투구 수" fill="var(--velo)" barSize={5} radius={[2, 2, 0, 0]} isAnimationActive={false} />
              <Line type="stepAfter" dataKey="sum_7d" name="7일 합" stroke="var(--ink)" strokeWidth={1.5} dot={false} connectNulls isAnimationActive={false} />
              <ReferenceLine y={data.load_lights.sum7.caution} stroke="var(--warn)" strokeDasharray="4 4" label={limitLabel(`주의 ${data.load_lights.sum7.caution}구`)} />
              <ReferenceLine y={data.load_lights.sum7.high} stroke="var(--alarm)" strokeDasharray="4 4" label={limitLabel(`높음 ${data.load_lights.sum7.high}구`)} />
              {rule && <ReferenceLine y={rule.max_pitches} stroke="var(--muted)" strokeDasharray="2 4" label={limitLabel(`7일 ${rule.max_pitches}구`)} />}
              {p.violations.filter((v) => v.rule !== "unknown").map((v) => <ReferenceLine key={v.date + v.rule} x={v.date} stroke="var(--alarm)" label={{ value: "위반", position: "insideTop", ...LABEL, fill: "var(--alarm)" }} />)}
            </ComposedChart>
          </ResponsiveContainer>
          <p className="caption">7일 합은 그날까지의 공식 경기 투구 수 합(연습·불펜 투구 제외). 3일 안 두 등판의 합은 등판표의 '직전 등판 뒤'와 투구 수로 확인할 수 있습니다.</p>
          <GamesTable p={p} withCompetition />
          <ViolationsTable p={p} />
        </div>
      )}
      <p className="note">
        출처: {ds.source}. 전국 모든 공식 경기를 넣었으므로 각 투수의 기록은 시즌 전체입니다. 상세 기록이 공개되지 않은 경기({ds.no_detail_games.length}경기)는 선발 투수만 '투구 수 미공개'로 들어갑니다.
        한계: 공식 경기 투구 수만 반영되고 연습·불펜 투구는 빠집니다. 고교에는 공식 부상 기록이 없어 이 화면은 '규정이 보지 못하는 부하를 보여 주는 현황판'이지 탐지 성능을 검증한 것이 아닙니다.
        규정 수치(하루 {kbsa.daily_max}구, 휴식일 표 {kbsa.rest_table.map(([u, r]) => `${u}구 이하 ${r}일`).join(" · ")})와 부하 기준값은 설정 파일 값입니다.
      </p>
    </div>
  );
}

/* ---------- 투수 운용 계획판: 기준일에 누가 등판할 수 있는가 (KBSA 규정을 앞으로 계산) ---------- */

function sumWindow(games, from, to) {
  let total = 0;
  for (const g of games) if (g.date >= from && g.date <= to) { if (g.pitches == null) return null; total += g.pitches; }
  return total;
}

function Planner({ school, games, kbsa, lights, onPick, picked }) {
  const mine = useMemo(() => games.filter((g) => g.teams.includes(school.name)), [games, school]);
  const firstDays = useMemo(() => {                                   // 이 학교가 치른 대회의 첫날 (바로가기)
    const out = new Map();
    for (const g of mine) if (!out.has(g.competition) || g.date < out.get(g.competition)) out.set(g.competition, g.date);
    return [...out.entries()].sort((a, b) => a[1].localeCompare(b[1]));
  }, [mine]);
  const [date, setDate] = useState(school.end);
  const [assume, setAssume] = useState(0);
  const rows = school.pitchers.map((x) => {
    const outings = x.games.map((g) => ({ date: g.date, pitches: g.pitches }));
    const today = x.games.find((g) => g.date === date) || null;
    const before = outings.filter((o) => o.date < date);              // 기준일 아침 기준: 그날 이전 등판만으로 판단
    const a = availability(before, date, kbsa.rest_table);
    const next = nextEligible(before, kbsa.rest_table);
    const sum7 = sumWindow(outings, addDays(date, -6), addDays(date, -1));
    const hypo = assume > 0 && a.status === "가용" ? nextEligible([...before, { date, pitches: assume }], kbsa.rest_table) : null;
    return { x, a, next, sum7, today, hypo };
  }).sort((r1, r2) => {
    const order = { "가용": 0, "불가": 1, "판정 불가": 2 };
    return order[r1.a.status] - order[r2.a.status] || (r1.sum7 ?? 0) - (r2.sum7 ?? 0) || r1.x.label.localeCompare(r2.x.label);
  });
  const counts = { "가용": 0, "불가": 0, "판정 불가": 0 };
  rows.forEach((r) => { counts[r.a.status] += 1; });
  const gameToday = mine.find((g) => g.date === date);
  const cls = { "가용": "ok", "불가": "alarm", "판정 불가": "base" };
  return (
    <div className="card">
      <div className="card-head">
        <h2>{school.name} 투수 운용 계획판 <span style={{ color: "var(--muted)", fontWeight: 500 }}>· 기준일 아침에 누가 등판할 수 있는가</span></h2>
        <span className="caption" style={{ margin: 0 }}>가용 <b style={{ color: "var(--ok)" }}>{counts["가용"]}</b> · 불가 <b style={{ color: "var(--alarm)" }}>{counts["불가"]}</b> · 판정 불가 {counts["판정 불가"]}{gameToday && ` · 이날 경기: ${gameToday.competition}`}</span>
      </div>
      <div className="toolbar" style={{ marginBottom: 10 }}>
        <label><span>기준일</span><input type="date" value={date} min={school.start} max={addDays(school.end, 14)} onChange={(e) => e.target.value && setDate(e.target.value)} style={{ height: 34, padding: "0 10px", border: "1px solid var(--line-2)", borderRadius: 9, background: "var(--card)" }} /></label>
        <label><span>바로가기</span>
          <select value="" onChange={(e) => e.target.value && setDate(e.target.value)}>
            <option value="">대회 첫날…</option>
            {firstDays.map(([c, d]) => <option key={c} value={d}>{c} {fmt.date(d)}</option>)}
            <option value={school.end}>시즌 마지막 경기 {fmt.date(school.end)}</option>
          </select>
        </label>
        <label><span>오늘 투구 가정</span><input type="number" min={0} max={130} step={5} value={assume} onChange={(e) => setAssume(Math.max(0, Number(e.target.value) || 0))} style={{ width: 80, height: 34, padding: "0 10px", border: "1px solid var(--line-2)", borderRadius: 9, background: "var(--card)" }} /><span style={{ color: "var(--muted)" }}>구 → 가용 투수의 다음 가능일</span></label>
      </div>
      <div className="tbl-wrap">
        <table className="tbl">
          <thead><tr><th>투수</th><th>기준일 상태</th><th>마지막 등판</th><th>의무 휴식</th><th>다음 등판 가능일</th><th className="num">직전 7일 합</th><th>이날 실제</th>{assume > 0 && <th>오늘 {assume}구 던지면</th>}</tr></thead>
          <tbody>
            {rows.map(({ x, a, next, sum7, today, hypo }) => (
              <tr key={x.code} className={x.code === picked ? "hl" : ""} onClick={() => onPick(x.code)} style={{ cursor: "pointer" }}>
                <td><b>{x.label}</b></td>
                <td><span className={`light ${cls[a.status]}`} title={a.reasons.join(" / ") || undefined}>{a.status}{a.status === "불가" && a.until && ` · ${fmt.date(a.until)}부터`}</span></td>
                <td>{next ? <>{fmt.date(next.last.date)} <span style={{ color: "var(--muted)" }}>· {next.last.pitches == null ? "투구 수 미공개" : `${next.last.pitches}구`}</span></> : <span style={{ color: "var(--muted)" }}>기준일 전 등판 없음</span>}</td>
                <td>{next ? (next.rest == null ? "—" : next.rest === 0 ? "없음" : `${next.rest}일`) : "—"}</td>
                <td>{next ? (next.date ? fmt.date(next.date) : "판정 불가") : "—"}</td>
                <td className="num">{sum7 == null ? "—" : sum7}{sum7 != null && sum7 >= lights.sum7.caution && <span className={`light ${sum7 >= lights.sum7.high ? "alarm" : "warn"}`} style={{ marginLeft: 6 }}>{sum7 >= lights.sum7.high ? "높음" : "주의"}</span>}</td>
                <td>{today ? <span className={`light ${a.status === "불가" ? "alarm" : "velo"}`}>{today.pitches == null ? "등판 (투구 수 미공개)" : `${today.pitches}구 등판`}{a.status === "불가" && " · 규정 위반?"}</span> : <span style={{ color: "var(--muted)" }}>—</span>}</td>
                {assume > 0 && <td>{hypo ? `${fmt.date(hypo.date)}부터 (휴식 ${hypo.rest}일)` : ""}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="caption">상태는 기준일 아침 기준 — 그날 이전 등판만으로 KBSA 규정(투구 수별 의무 휴식일, 3일 연속 등판 금지)을 적용합니다. '이날 실제'는 기록에 있는 그날 등판입니다. 2025 기록으로 되돌아보는 화면이지만, 운영 중에는 어제까지의 투구 수만 넣으면 오늘의 가용 투수와 '오늘 몇 구를 던지면 언제 다시 나올 수 있는가'가 그대로 나옵니다.</p>
    </div>
  );
}

/* ---------- 대회 모드: 2025 전국체전 18세 이하부 ---------- */

function cellsFor(p, days, restTable) {
  const byDate = Object.fromEntries(p.games.map((g) => [g.date, g]));
  const rest = new Set();
  for (const g of p.games) {
    const need = g.pitches == null ? null : requiredRest(g.pitches, restTable);
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

function cumulativeLight(p, lights) {
  if (p.pitches_total == null) return { cls: "base", text: "누적 모름" };
  const { caution, high } = lights.sum7;
  return { cls: p.pitches_total >= high ? "alarm" : p.pitches_total >= caution ? "warn" : "ok", text: `누적 ${p.pitches_total}구${p.pitches_total >= high ? " · 높음" : p.pitches_total >= caution ? " · 주의" : ""}` };
}

function TournamentBoard({ data, index, selector, params, setParams }) {
  const { schools, s, pitchers, p, setSchool, setCode } = useSelection(data, params, setParams, null);
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
        <b> 누적</b>은 대회 7일 동안 던진 투구 수의 합입니다({data.load_lights.sum7.caution}구 이상 '주의', {data.load_lights.sum7.high}구 이상 '높음' — 시즌 화면의 7일 합과 같은 기준으로, 규정이 아니라 전국 2025 자료 분위수에 맞춘 서술적 눈금).
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
              const load = cumulativeLight(x, data.load_lights);
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
