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

// 학교 투수 표 칸별 툴팁 (2026-10-16: 모든 칸에서 그 칸 설명이 뜨게)
const RULE_TIP = { "준수": "하루 105구, 투구 수별 의무 휴식일, 3일 연속 등판 금지를 모두 지켰습니다", "위반": "KBSA 투구수 규정을 어긴 등판이 있습니다 (아래 카드에 날짜)", "판정 불가": "투구 수가 공개되지 않은 등판이 있어 규정 준수를 판정할 수 없습니다" };
function loadTip(x, lights) {
  if (x.load_reasons.length) return `누적 부하 ${x.load_status} 이유: ${x.load_reasons.join(" · ")}`;
  if (x.load_status === "계산 불가") return "투구 수가 공개되지 않은 등판이 있어 누적 부하를 계산할 수 없습니다";
  return `보통: 7일 합 최대 ${x.max_7d != null ? fmt.num(x.max_7d, 0) : "—"}구(주의 ${lights.sum7.caution}구 미만), 3일 안 두 경기 합 최대 ${x.max_pair3 != null ? fmt.num(x.max_pair3, 0) : "—"}구(주의 ${lights.pair3.caution}구 미만)`;
}

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
      {index.datasets.map((d) => <button key={d.key} role="tab" className={`btn ${d.key === dataset.key ? "on" : ""}`} aria-selected={d.key === dataset.key} onClick={() => pick(d.key)}>{d.mode === "season" ? `${d.short} 전국 고교` : `${d.short} (7일 대회)`}</button>)}
    </div>
  );
  if (!data) return <div className="page"><h1>고교 투구수 현황판</h1><div className="placeholder">자료를 읽는 중…</div></div>;
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

/** 직전 등판 뒤: 첫 줄 = 쉰 날 + 표시(연투·미달·휴식 뒤 첫날), 둘째 줄 = 의무 휴식일 (표가 한 화면에 들어가게 두 줄로). */
function restText(g) {
  if (g.gap_days == null) return <span style={{ color: "var(--muted)" }}>첫 등판</span>;
  const gap = `${g.gap_days}일 휴식`;
  const sub = (text) => <small className="sub">{text}</small>;
  if (g.required_rest == null) return <>{gap}{sub("직전 투구 수 미공개")}</>;
  const need = g.required_rest === 0 ? "의무 휴식 없음" : `의무 ${g.required_rest}일`;
  if (g.rest_ok === false) return <>{gap} <span className="light alarm" title={`${need} 미달`}>미달</span>{sub(need)}</>;
  if (g.gap_days === 0) return <>{gap} <span className="light warn">연투</span>{sub(need)}</>;
  if (g.min_rest_exact) return <>{gap} <span className="light warn" title={`${need}이 끝난 첫날 등판`}>휴식 뒤 첫날</span>{sub(need)}</>;
  return <>{gap}{sub(need)}</>;
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

/** 이닝별 띠: 이닝 투구 수와 스트라이크·볼(기록지 투구수 줄 + 표시 판독, 추정), 그 뒤에 타석 결과 칩(범주 색, 사건은 툴팁).
 *  innings 항목 = [이닝, 투구 수, 스트라이크, 볼, 교체 이닝?] — 스트라이크·볼을 못 믿는 이닝은 null. */
function FlowStrip({ flow, innings }) {
  const pas = flow || [];
  const count = new Map((innings || []).map((r) => [r[0], r]));
  const list = [...new Set([...pas.map((f) => f[0]), ...count.keys()])].sort((a, b) => a - b);
  return (
    <div className="flow">
      {list.map((inn) => {
        const r = count.get(inn);
        return (
          <span key={inn} className="flow-inn">
            <b>{inn}회</b>
            {r && (
              <span className="inn-count" title={r[2] == null ? "이 이닝은 기록지에서 읽은 공 수가 투구 수와 많이 달라 스트라이크·볼을 비웠습니다" : "스트라이크·볼은 기록지 표시를 읽은 추정값입니다 (스트라이크 = 볼이 아닌 모든 공, 띠에 안 그린 마지막 공은 타석 결과로 채움)"}>
                {r[1]}구{r[2] != null && <small> (스트라이크 {r[2]}개 · 볼 {r[3]}개)</small>}{r[4] && <small> · 교체 이닝</small>}
              </span>
            )}
            {pas.filter((f) => f[0] === inn).map(([, res, cat, ev], i) => <i key={i} className={`pa ${CAT[cat]?.[1] || "out"}`} title={`${CAT[cat]?.[0] || cat}${ev?.length ? ` · ${ev.join(", ")}` : ""}`}>{res}</i>)}
          </span>
        );
      })}
    </div>
  );
}

function BallTip({ d }) {
  return (
    <>
      <div><b>{fmt.date(d.date)}</b> · {d.opponent}</div>
      <div>볼 비율(추정) <b>{fmt.num(d.ball, 0)}%</b> · {ballOf(d.ball / 100, d.pitches)}</div>
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
      <div className="chart-title">등판별 볼 비율 <small>점선 = 시즌 평균 · 주황 점 = 평소보다 볼이 많았던 등판</small><span className="hover-hint">점에 커서를 올리면 그 경기 상대·볼 비율·볼 수</span></div>
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

const BALL_HOW = "협회 기록지 사진에서 공마다 볼인지 아닌지를 읽은 값입니다. 기록원이 그리지 않은 마지막 공(4구의 넷째 볼, 삼진의 셋째 스트라이크, 인플레이 타구)은 타석 결과로 채웁니다. 볼 비율 = 볼 ÷ 공식 투구 수(읽지 못한 공은 볼이 아닌 것으로 셈). 기록지에서 읽은 공 수가 공식 투구 수와 15% 넘게 다른 등판은 뺍니다. '평소보다 볼 많음'은 40구 이상 등판을 그 투수의 다른 등판과 비교한 것이며, 원인은 해석하지 않습니다.";

// 볼 수는 '공식 투구 수 중 몇 개'로만 보여 준다 (2026-10-20 외부 검토·사용자 결정: 기록지에서 센 공 수는 화면에 내지 않음)
const ballOf = (pct, pitches) => (pitches ? `공식 ${pitches}구 중 볼 ${Math.round(pct * pitches)}개 (기록지에서 읽음)` : "기록지에서 읽음");

/** 다시 읽은 등판 표시 — 2026-10-09 사용자 "꼭 표시할 필요는 없다"로 숨김(데이터의 ball_reread는 남김). 되살리려면 SHOW_REREAD = true. */
const SHOW_REREAD = false;
function RereadMark({ g }) {
  if (!SHOW_REREAD || !(g.ball_reread > 0)) return null;
  return <span className="light base" style={{ marginLeft: 6 }} title={`자동 판독이 어려운 기록지라 다시 읽은 등판입니다 — 그린 표시의 ${fmt.num(100 * g.ball_reread, 0)}%를 AI가 다시 읽었습니다(일부는 사람이 확인).`}>다시 읽음</span>;
}

/** 기록지 판독 볼 비율(추정) 칸: 안 읽음 — / 읽었지만 검산 미달 / 비율과 '평소보다 볼 많음'. */
function BallCell({ g }) {
  if (g.ball_marks == null) return <span style={{ color: "var(--muted)" }}>—</span>;
  if (g.ball_pct == null) {
    return <><span className="light base" title="기록지에서 읽은 공 수가 공식 투구 수와 15% 넘게 달라 볼 비율을 보여 주지 않습니다">검산 미달</span><RereadMark g={g} /></>;
  }
  return (
    <>
      <span title={ballOf(g.ball_pct, g.pitches)}>{fmt.num(100 * g.ball_pct, 0)}%</span>
      {g.ball_flag && <span className="light warn" style={{ marginLeft: 6 }} title="평소보다 볼이 많았던 등판: 그 투수의 다른 등판보다 볼 비율이 뚜렷이 높았던 등판입니다(투구 수를 감안한 기준, 40구 이상만). 원인은 해석하지 않습니다.">볼 많음</span>}
      <RereadMark g={g} />
    </>
  );
}

function GamesTable({ p, withCompetition }) {
  const [open, setOpen] = useState(null);
  const hasResults = p.games.some((g) => g.batters != null);
  const hasBall = p.games.some((g) => g.ball_marks != null);
  const hasDetail = hasResults || p.games.some((g) => g.innings);
  return (
    <div className="tbl-wrap">
      <table className="tbl games">
        <thead><tr><th>날짜</th><th>{withCompetition ? "대회" : "라운드"}</th><th>상대</th><th>등판</th><th className="num">이닝</th><th className="num">투구 수</th>{hasResults && <><th className="num">타자</th><th className="num">삼진</th><th className="num">4사구</th><th className="num">피안타</th><th className="num">타자당 투구</th></>}{hasBall && <th className="num" title={BALL_HOW}>볼 비율</th>}<th>직전 등판 뒤</th><th className="num">누적</th>{hasDetail && <th>흐름</th>}</tr></thead>
        <tbody>
          {p.games.map((g) => {
            const sum = g.flow ? flowSummary(g.flow) : null;
            return [
              <tr key={g.game_no} className={open === g.game_no ? "hl" : ""}>
                <td>{g.date.slice(5).replace("-", "/")}</td><td className="wrap">{withCompetition ? g.competition : g.round}</td><td>{g.opponent}</td>
                <td>{g.role}{g.result !== "-" && <span style={{ color: "var(--muted)" }}> · {g.result}</span>}</td>
                <td className="num">{innings(g.outs)}</td>
                <td className="num">{g.pitches == null ? <span className="light base">미공개</span> : g.pitches}</td>
                {hasResults && <>
                  <td className="num">{g.batters ?? "—"}</td><td className="num">{g.k ?? "—"}</td>
                  <td className="num wrap">{g.bb_hbp ?? "—"}{sum?.walkInnings.length > 0 && <span className="light warn" style={{ marginLeft: 6 }} title={`4구·사구 2개 이상 몰린 이닝: ${sum.walkInnings.map((i) => `${i}회`).join(", ")}`}>{sum.walkInnings.map((i) => `${i}회`).join("·")} 몰림</span>}</td>
                  <td className="num">{g.hits ?? "—"}{g.hr > 0 && <span style={{ color: "var(--muted)" }}> (홈런 {g.hr})</span>}</td>
                  <td className="num">{g.pitches != null && g.batters ? fmt.num(g.pitches / g.batters, 1) : "—"}</td>
                </>}
                {hasBall && <td className="num wrap"><BallCell g={g} /></td>}
                <td className="wrap">{restText(g)}</td>
                <td className="num">{g.cum_pitches == null ? "—" : g.cum_pitches}</td>
                {hasDetail && <td>{g.flow || g.innings ? <button className="pill" onClick={() => setOpen(open === g.game_no ? null : g.game_no)}>{open === g.game_no ? "닫기" : g.innings ? "이닝별 보기" : "타석별 보기"}</button> : <span style={{ color: "var(--muted)" }}>—</span>}</td>}
              </tr>,
              open === g.game_no && (g.flow || g.innings) && (
                <tr key={`${g.game_no}-flow`} className="flow-row">
                  <td colSpan={16} style={{ whiteSpace: "normal" }}>
                    <FlowStrip flow={g.flow} innings={g.innings} />
                    {sum && <div className="caption" style={{ marginTop: 6 }}>타석 {sum.pa} · 삼진 {sum.k} · 4구+사구 {sum.bb} · 안타 {sum.h}{sum.wild > 0 && ` · 폭투·보크·포일 ${sum.wild}`}{sum.walkInnings.length > 0 && ` · 4사구가 몰린 이닝 ${sum.walkInnings.map((i) => `${i}회`).join(", ")}`} — 상대 타격표의 타석을 투수 타자 수대로 배정해 복원한 순서입니다(합이 맞는 경기만).</div>}
                    {g.innings && <div className="caption" style={{ marginTop: 4 }}>이닝별 투구 수는 협회 기록지 맨 아래 '투구수' 줄을 읽은 값입니다(이닝 합이 공식 투구 수와 맞는 등판만). 스트라이크·볼은 그 이닝 기록지 표시의 볼 비율로 나눈 추정값이고(스트라이크 = 볼이 아닌 모든 공), 표시 수가 투구 수와 많이 다른 이닝은 비웠습니다. 교체 이닝은 공식 투구 수에서 나머지 이닝을 뺀 몫입니다.</div>}
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
  const foreign = params.get("f") && data.foreign_rules[params.get("f")] ? params.get("f") : "none";
  const rule = foreign !== "none" ? data.foreign_rules[foreign] : null;
  const days = useMemo(() => (p && s ? dailySeries(p.games.map((g) => ({ date: g.date, pitches: g.pitches })), s.start, s.end, { acute_days: 7, chronic_days: 21 }) : [])
    .map((d) => ({ ...d, over: rule ? (d.sum_7d != null && d.sum_7d > rule.max_pitches) : false })), [p, s, data, rule]);
  const gameDays = useMemo(() => days.filter((d) => d.pitches).map((d) => ({ ...d, x: d.date.slice(5).replace("-", "/") })), [days]);   // 등판한 날만 (빈 날이 많아 막대가 가늘어지던 것)
  const ruleCounts = Object.entries(totals.violations_by_rule).filter(([k]) => k !== "unknown").map(([k, v]) => `${RULE_NAME[k] || k} ${v}`).join(" · ");
  return (
    <div className="page">
      <h1>{dataset.season} 전국 고교 투구수 현황판</h1>
      <p className="lead">{dataset.season}년 전국 고교 공식 경기 {dataset.games}경기의 투구 수로, 투수마다 KBSA 투구수 규정을 지켰는지와 규정이 보지 못하는 누적 부하를 봅니다.</p>
      <details className="more">
        <summary>신호등 기준 보기</summary>
        <p><b>규정</b>: 하루 {kbsa.daily_max}구, 투구 수별 의무 휴식일, 3일 연속 등판 금지를 지켰는지.<br />
          <b>누적 부하</b>: 7일 투구 수 합이 {data.load_lights.sum7.caution}구 이상이면 주의, {data.load_lights.sum7.high}구 이상이면 높음. 3일 안 두 경기 합이 {data.load_lights.pair3.caution}구 이상이면 주의, {data.load_lights.pair3.high}구 이상이면 높음.
          규정이 아니라 2025년 전국 자료에서 상위 5%·2%에 해당하는 값으로 정한 눈금입니다.</p>
      </details>
      <div className="toolbar">
        <label><span>권역</span>
          <select value={region?.key || ""} onChange={(e) => setRegion(e.target.value)}>
            {dataset.regions.map((r) => <option key={r.key} value={r.key}>{r.name} ({r.schools}팀)</option>)}
          </select>
        </label>
        <PlayerSearch entry={dataset} params={params} setParams={setParams} />
        <span className="caption" style={{ margin: 0 }}>{ds.region} 권역 · {totals.schools}개 팀 · 투수 {totals.pitchers}명 · {totals.games}경기</span>
      </div>
      <div className="kpi">
        <div><div className="v">{totals.violations}<span className="sub"> 건</span></div><div className="l">규정 위반{ruleCounts && ` (${ruleCounts})`}</div></div>
        <div><div className="v">{totals.compliant_with_load}<span className="sub"> 명</span></div><div className="l">규정은 지켰지만 누적 부하 주의·높음</div></div>
        <div><div className="v">{totals.pitchers_season_500}<span className="sub"> 명</span></div><div className="l">시즌 500구 이상 던진 투수</div></div>
        <div><div className="v">{totals.pairs3_70}<span className="sub"> 쌍</span></div><div className="l">3일 안 두 경기 합 {data.load_lights.pair3.caution}구 이상</div></div>
      </div>
      <div className="toolbar">
        <label><span>학교</span>
          <select value={s?.code || ""} onChange={(e) => setSchool(e.target.value)}>
            {schools.map((x) => <option key={x.code} value={x.code}>{x.name}</option>)}
          </select>
        </label>
        <label><span>해외 규정 비교</span>
          <select value={foreign} onChange={(e) => setParams({ ...keep, s: s.code, p: p?.code, f: e.target.value }, { replace: true })}>
            <option value="none">없음</option>
            {Object.entries(data.foreign_rules).map(([k, v]) => <option key={k} value={k}>{k === "japan" ? "일본" : k} {v.window_days}일 {v.max_pitches}구</option>)}
          </select>
        </label>
        {s && <span className="caption" style={{ margin: 0 }}>{s.name} · {s.games}경기 · 투수 {s.pitchers.length}명 · 규정 위반 {s.violations}건 · 부하 높음 <b style={{ color: "var(--alarm)" }}>{s.load_high}</b> · 주의 <b style={{ color: "var(--warn)" }}>{s.load_caution}</b></span>}
      </div>
      <div className="grid2">
        <div className="card">
          <h2>{s?.name} 투수 <span className="hover-hint">줄을 누르면 아래에 그 투수 · 칸에 커서를 올리면 설명</span></h2>
          <div className="tbl-wrap">
            <table className="tbl pick">
              <thead><tr><th>투수</th><th>규정</th><th>누적 부하</th><th className="num">등판</th><th className="num">시즌 투구</th><th className="num" title="한 주(그날 포함 7일) 동안 던진 투구 수 합의 시즌 최댓값">7일 최대</th><th className="num">볼 비율</th></tr></thead>
              <tbody>
                {pitchers.map((x) => (
                  <tr key={x.code} className={x.code === p?.code ? "hl" : ""} onClick={() => setCode(x.code)}>
                    <td title="누르면 아래에 이 투수의 시즌 카드가 열립니다"><b>{x.label}</b></td>
                    <td title={RULE_TIP[x.rule_status]}><span className={`light ${STATUS_CLASS[x.rule_status]}`}>{x.rule_status}</span></td>
                    <td title={loadTip(x, data.load_lights)}><span className={`light ${LOAD_CLASS[x.load_status]}`}>{x.load_status}</span></td>
                    <td className="num" title={`시즌 등판 ${x.outings}회`}>{x.outings}</td>
                    <td className="num" title={x.pitches_total == null ? "투구 수가 공개되지 않은 등판이 있어 합계를 낼 수 없습니다" : `시즌 공식 경기 투구 수 합계 ${x.pitches_total}구 (연습·불펜 투구 제외)`}>{x.pitches_total ?? "—"}</td>
                    <td className="num" title={x.max_7d != null ? `한 주(그날 포함 7일) 동안 던진 투구 수 합의 시즌 최댓값 · 주의 ${data.load_lights.sum7.caution}구, 높음 ${data.load_lights.sum7.high}구` : undefined}>{x.max_7d != null ? fmt.num(x.max_7d, 0) : "—"}</td>
                    <td className="num" title={x.ball_season != null ? `기록지에서 읽은 볼 비율(추정) · ${x.ball_outings ?? "?"}등판 합${x.ball_flags > 0 ? ` · 평소보다 볼이 많았던 등판 ${x.ball_flags}` : ""}` : "기록지에서 볼 비율을 읽지 못했습니다"}>{x.ball_season != null ? `${fmt.num(100 * x.ball_season, 0)}%` : "—"}{x.ball_flags > 0 && <span className="light warn" style={{ marginLeft: 4 }}>{x.ball_flags}</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <div className="card">
          <h2>투수별 시즌 투구 수</h2>
          <ResponsiveContainer width="100%" height={Math.max(220, 33 * pitchers.length + 40)}>
            <ComposedChart layout="vertical" data={pitchers.map((x) => ({ label: x.label, total: x.pitches_total ?? 0, unknown: x.pitches_total == null, on: x.code === p?.code }))} margin={{ top: 4, right: 48, left: 4, bottom: 0 }}>
              <CartesianGrid horizontal={false} stroke={GRID} />
              <XAxis type="number" tick={TICK} axisLine={false} tickLine={false} />
              <YAxis type="category" dataKey="label" width={86} tick={TICK} axisLine={false} tickLine={false} interval={0} />
              <Tooltip {...TIP_STYLE} formatter={(v, n, item) => [item.payload.unknown ? "일부 미공개" : `${fmt.num(v, 0)}구`, "시즌 투구 수"]} />
              <Bar dataKey="total" name="시즌 투구 수" fill="var(--navy-2)" radius={[0, 3, 3, 0]} isAnimationActive={false} label={{ position: "right", fontSize: 11, fill: "var(--ink-2)", formatter: (v) => (v ? fmt.num(v, 0) : "") }} />
              <ReferenceLine x={500} stroke="var(--alarm)" strokeDasharray="4 4" />
            </ComposedChart>
          </ResponsiveContainer>
          <p className="caption">점선은 시즌 500구. <span className="hover-hint">막대에 커서를 올리면 투구 수</span></p>
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
          {p.stats && <HsStats st={p.stats} />}
          {!p.stats && p.batters != null && p.batters > 0 && (
            <p className="caption" style={{ marginTop: 0 }}>
              <b>시즌 기록</b> 타자 {fmt.num(p.batters, 0)}명 · 삼진율 {fmt.num(100 * (p.k ?? 0) / p.batters, 1)}% · 4사구율 {fmt.num(100 * (p.bb_hbp ?? 0) / p.batters, 1)}% · 피안타 {p.hits ?? "—"}(홈런 {p.hr ?? 0}){p.p_per_pa != null && ` · 타자당 투구 ${fmt.num(p.p_per_pa, 1)}개`}
            </p>
          )}
          {p.games.some((g) => g.ball_marks != null) && (
            <p className="caption" style={{ marginTop: 0 }}>※ 볼·스트라이크 비율은 손으로 쓴 협회 기록지를 모델이 읽고 판정한 값이라 약간의 오차가 있을 수 있습니다.</p>
          )}
          {p.games.some((g) => g.ball_marks != null) && (
            <p className="caption" style={{ marginTop: 0 }}>
              <b>볼 비율(추정)</b> {p.ball_season != null ? `${fmt.num(100 * p.ball_season, 1)}%` : "—"} · {p.outings}등판 중 {p.ball_outings}등판{p.ball_flags > 0 && ` · 평소보다 볼이 많았던 등판 ${p.ball_flags}`}
              <span className="info" title={BALL_HOW}>i</span>
            </p>
          )}
          <BallChart p={p} />
          <div className="chart-title">등판별 투구 수 <span className="hover-hint">막대·점에 커서를 올리면 날짜별 투구 수와 7일 합</span><small style={{ display: "block", marginTop: 2 }}>막대 = 그날 투구 수 · 선 = 그날까지 7일 합 · 점선 = 7일 합 주의 {data.load_lights.sum7.caution}구, 높음 {data.load_lights.sum7.high}구{rule && ` · ${rule.max_pitches}구(해외 규정)를 넘은 날 ${days.filter((d) => d.over).length}일`}</small></div>
          <ResponsiveContainer width="100%" height={240}>
            <ComposedChart data={gameDays} margin={{ top: 10, right: 12, left: 0, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke={GRID} />
              <XAxis dataKey="x" tick={TICK} axisLine={{ stroke: GRID }} tickLine={false} interval="preserveStartEnd" minTickGap={8} />
              <YAxis tick={TICK} width={36} axisLine={false} tickLine={false} />
              <Tooltip content={<ChartTip render={(payload) => <DayTip d={payload[0].payload} />} />} cursor={{ fill: "rgba(19,40,75,0.05)" }} />
              <Bar dataKey="pitches" name="투구 수" fill="var(--navy-2)" maxBarSize={22} radius={[2, 2, 0, 0]} isAnimationActive={false} />
              <Line dataKey="sum_7d" name="7일 합" stroke="var(--warn)" strokeWidth={2} dot={{ r: 2.5 }} isAnimationActive={false} />
              <ReferenceLine y={data.load_lights.sum7.caution} stroke="var(--warn)" strokeDasharray="4 4" label={limitLabel(`주의 ${data.load_lights.sum7.caution}`)} />
              <ReferenceLine y={data.load_lights.sum7.high} stroke="var(--alarm)" strokeDasharray="4 4" label={limitLabel(`높음 ${data.load_lights.sum7.high}`)} />
              {rule && <ReferenceLine y={rule.max_pitches} stroke="var(--muted)" strokeDasharray="2 4" label={limitLabel(`7일 ${rule.max_pitches}구`)} />}
            </ComposedChart>
          </ResponsiveContainer>
          <p className="caption" style={{ margin: "14px 0 6px" }}><span className="hover-hint">'볼 비율' 칸의 '검산 미달'과, '이닝별 보기'를 연 뒤 이닝 투구 수에 커서를 올리면 설명이 보입니다</span></p>
          <GamesTable p={p} withCompetition />
          <ViolationsTable p={p} />
        </div>
      )}
      <p className="note">
        출처: {ds.source}. 공식 경기 투구 수만 반영되며 연습·불펜 투구는 빠집니다. 상세 기록이 공개되지 않은 {ds.no_detail_games.length}경기는 선발 투수만 '투구 수 미공개'로 들어갑니다.
        고교에는 공식 부상 기록이 없어, 이 화면은 부상 탐지가 아니라 규정이 보지 못하는 부하를 보여 주는 현황판입니다.
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
        <h2>{school.name} 투수 운용 계획판</h2>
        <span className="caption" style={{ margin: 0 }}>가용 <b style={{ color: "var(--ok)" }}>{counts["가용"]}</b> · 불가 <b style={{ color: "var(--alarm)" }}>{counts["불가"]}</b> · 판정 불가 {counts["판정 불가"]}{gameToday && ` · 이날 경기: ${gameToday.competition}`}</span>
      </div>
      <div className="toolbar" style={{ marginBottom: 10 }}>
        <label><span>날짜</span><input className="text" type="date" value={date} min={school.start} max={addDays(school.end, 14)} onChange={(e) => e.target.value && setDate(e.target.value)} /></label>
        <label><span>바로가기</span>
          <select value="" onChange={(e) => e.target.value && setDate(e.target.value)}>
            <option value="">대회 첫날…</option>
            {firstDays.map(([c, d]) => <option key={c} value={d}>{c} {fmt.date(d)}</option>)}
            <option value={school.end}>시즌 마지막 경기 {fmt.date(school.end)}</option>
          </select>
        </label>
        <label><span>오늘</span><input className="text" type="number" min={0} max={130} step={5} value={assume} onChange={(e) => setAssume(Math.max(0, Number(e.target.value) || 0))} style={{ width: 80 }} /><span>구 던지면 다음 등판 가능일은?</span></label>
      </div>
      <div className="tbl-wrap">
        <table className="tbl">
          <thead><tr><th>투수</th><th>이날 등판</th><th>마지막 등판</th><th>의무 휴식</th><th>다음 등판 가능일</th><th className="num">직전 7일 합</th><th>이날 실제</th>{assume > 0 && <th>오늘 {assume}구 던지면</th>}</tr></thead>
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
      <p className="caption">고른 날짜 전날까지의 등판에 KBSA 규정(투구 수별 의무 휴식일, 3일 연속 등판 금지)을 적용한 결과입니다. 시즌 중에는 어제까지의 투구 수만 넣으면 오늘 나갈 수 있는 투수가 바로 나옵니다. <span className="hover-hint">'이날 등판' 칸에 커서를 올리면 판단 이유</span></p>
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

// 투수 시즌 성적 (2026-10-21 사용자: 스카우트가 보는 지표 — 맥락 정보, 규정·부하 신호와 섞지 않음). 10이닝 미만은 흐리게
const HS_STATS = [
  ["ip", "이닝", (v) => fmt.num(v, 1), "타석 결과가 있는 등판의 이닝"],
  ["era", "ERA", (v) => fmt.num(v, 2), "9이닝당 자책점 (고교는 7이닝 경기가 많아 프로와 바로 비교하지 않음)"],
  ["whip", "WHIP", (v) => fmt.num(v, 2), "이닝당 출루 허용 (피안타 + 볼넷)"],
  ["avg", "피안타율", (v) => v.toFixed(3).replace(/^0/, ""), "상대 타율 (타수 = 타석 − 4구 − 사구 − 희생)"],
  ["ops", "피OPS", (v) => v.toFixed(3).replace(/^0/, ""), "상대 출루율 + 장타율 (2루타·3루타는 타석 결과 표기로 셈)"],
  ["k_pct", "삼진%", (v) => fmt.num(100 * v, 1), "상대 타자 중 삼진 비율"],
  ["bb_pct", "4사구%", (v) => fmt.num(100 * v, 1), "상대 타자 중 볼넷·사구 비율"],
  ["k_bb", "K−BB%", (v) => fmt.num(100 * v, 1), "삼진% − 4사구%. 이닝이 적어도 비교적 안정적인 제구·구위 지표"],
  ["go_ao", "땅볼/뜬공", (v) => fmt.num(v, 2), "땅볼 아웃 ÷ 뜬공 아웃 (직선타는 뜬공 쪽, 번트 아웃 제외)"],
  ["p_ip", "이닝당 투구", (v) => fmt.num(v, 1), "이닝당 투구 수 — 같은 이닝을 막아도 많으면 부하가 큼"],
  ["p_bf", "타자당 투구", (v) => fmt.num(v, 1), "타자 한 명에게 던진 공"],
];

function HsStats({ st }) {
  const small = st.ip < 10;
  const vals = { ...st, ops: st.obp != null && st.slg != null ? st.obp + st.slg : null, k_bb: st.k_pct != null && st.bb_pct != null ? st.k_pct - st.bb_pct : null };
  return (
    <div style={{ margin: "0 0 10px" }}>
      <div className="chart-title" style={{ marginBottom: 4 }}>시즌 성적 <small>협회 경기 기록·타석 결과 · 맥락 정보{small && " · 10이닝 미만이라 표본 적음"}</small><span className="hover-hint">칸에 커서를 올리면 뜻</span></div>
      <div className="tbl-wrap">
        <table className="tbl" style={small ? { opacity: 0.55 } : undefined}>
          <thead><tr>{HS_STATS.map(([k, name, , tip]) => <th key={k} className="num" title={tip}>{name}</th>)}</tr></thead>
          <tbody><tr>{HS_STATS.map(([k, , f, tip]) => <td key={k} className="num" title={tip}>{vals[k] == null ? "—" : f(vals[k])}</td>)}</tr></tbody>
        </table>
      </div>
    </div>
  );
}

// 검색 칸 예시 (2026-10-20 사용자: 2025는 대구고 김민준, 2026은 하현승). 없는 자료는 목록 첫 선수
const PLAYER_EXAMPLE = { korea_2025: "김민준 · 대구고", korea_2026: "하현승 · 부산고", tournament_2025: "하현승 · 부산고" };

/** 선수 이름 검색 (2026-10-20 사용자: 학교 검색 대신, MLB 리플레이처럼 이름으로 바로) — 전국에서 찾아 그 권역·학교·투수로 이동 */
function PlayerSearch({ entry, params, setParams }) {
  const players = entry?.players || [];
  const label = (x) => `${x.n} · ${x.t}`;
  const pick = (v) => {
    const hit = players.find((x) => label(x) === v);
    if (hit) setParams({ d: entry.key, ...(hit.r ? { r: hit.r } : {}), s: hit.s, p: hit.p }, { replace: true });
  };
  if (!players.length) return null;
  const example = PLAYER_EXAMPLE[entry.key] || `${players[0].n.split(" #")[0]} · ${players[0].t}`;
  return (
    <label><span>선수 검색</span>
      <input key={params.get("p") || ""} className="text" type="search" list={`hs-players-${entry.key}`} placeholder={`이름 (예: ${example})`} onChange={(e) => pick(e.target.value)} style={{ minWidth: 220 }} />
      <datalist id={`hs-players-${entry.key}`}>{players.map((x) => <option key={`${x.s}-${x.p}`} value={label(x)} />)}</datalist>
    </label>
  );
}

function TournamentBoard({ data, index, selector, params, setParams }) {
  const entry = index?.datasets?.find((x) => x.key === data.dataset?.key);
  const { schools, s, pitchers, p, setSchool, setCode } = useSelection(data, params, setParams, null);
  const { dataset: ds, totals, kbsa } = data;
  const days = useMemo(() => { const dates = data.games.map((g) => g.date).sort(); return dateRange(dates[0], dates[dates.length - 1]); }, [data]);
  const gamesByDate = useMemo(() => Object.fromEntries(days.map((d) => [d, data.games.filter((g) => g.date === d && g.teams.includes(s?.name))])), [days, data, s]);
  const chart = days.map((d) => { const g = p?.games.find((x) => x.date === d); return { date: d, pitches: g ? g.pitches : null, unknown: g && g.pitches == null ? kbsa.daily_max : null, cum: g ? g.cum_pitches : null }; });
  return (
    <div className="page">
      <h1>{ds.short} 투구수 현황판</h1>
      <p className="lead">{ds.name}({ds.dates}, {schools.length}개교 {ds.games}경기)에서 투수마다 규정 준수와 대회 7일 동안의 누적 투구 수를 봅니다. 누적 {data.load_lights.sum7.caution}구 이상은 주의, {data.load_lights.sum7.high}구 이상은 높음입니다.</p>
      <div className="kpi">
        <div><div className="v">{totals.violations}<span className="sub"> 건</span></div><div className="l">규정 위반</div></div>
        <div><div className="v">{totals.back_to_back}<span className="sub"> 건</span></div><div className="l">연투(이튿날 다시 등판)</div></div>
        <div><div className="v">{totals.games_91plus}<span className="sub"> 등판</span></div><div className="l">91구 이상 등판</div></div>
        <div><div className="v">{totals.max_total}<span className="sub"> 구</span></div><div className="l">한 투수의 대회 누적 최다</div></div>
      </div>
      <div className="toolbar">
        <label><span>학교</span>
          <select value={s?.code || ""} onChange={(e) => setSchool(e.target.value)}>
            {schools.map((x) => <option key={x.code} value={x.code}>{x.name} · {x.games}경기 · 투수 {x.pitchers.length}명</option>)}
          </select>
        </label>
        <PlayerSearch entry={entry} params={params} setParams={setParams} />
        <span className="caption" style={{ margin: 0 }}>{ds.games}경기 · 투수 {totals.pitchers}명 · 등판 {totals.outings}회</span>
      </div>
      <div className="grid2 hs-grid">
        <div className="card">
          <h2>{s?.name} 투수</h2>
          <div className="tbl-wrap">
            <table className="tbl pick">
              <thead><tr><th>투수</th><th>규정</th><th>대회 누적</th><th className="num">등판</th><th className="num">연투</th><th className="num">휴식 끝난 첫날 등판</th></tr></thead>
              <tbody>
                {pitchers.map((x) => {
                  const load = cumulativeLight(x, data.load_lights);
                  return (
                    <tr key={x.code} className={x.code === p?.code ? "hl" : ""} onClick={() => setCode(x.code)}>
                      <td><b>{x.label}</b></td>
                      <td><span className={`light ${STATUS_CLASS[x.rule_status]}`}>{x.rule_status}</span></td>
                      <td><span className={`light ${load.cls}`}>{load.text.replace("누적 ", "")}</span></td>
                      <td className="num">{x.outings}</td>
                      <td className="num">{x.back_to_back || "—"}</td>
                      <td className="num">{x.min_rest_exact || "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
        <div className="card">
          <h2>대회 등판 달력 <span style={{ color: "var(--muted)", fontWeight: 500, fontSize: 13 }}>칸 숫자 = 그날 투구 수</span></h2>
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
              <p className="caption">누적 선은 대회 기간 투구 수의 합. 투구 수가 공개되지 않은 경기(점선 막대) 뒤로는 누적을 표시하지 않습니다. <span className="hover-hint">막대·점에 커서를 올리면 그날 값</span></p>
            </div>
          </div>
          <ViolationsTable p={p} />
        </div>
      )}
      <p className="note">
        출처: {ds.source}. 상세 기록이 공개되지 않은 {ds.no_detail_games.length}경기는 선발 투수 두 명만 '투구 수 미공개'로 들어갑니다. 대회 전 주말리그·연습 투구는 빠집니다.
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
