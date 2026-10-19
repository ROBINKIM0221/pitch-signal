import { useState } from "react";
import { Link } from "react-router-dom";
import { CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis } from "recharts";
import { PITCH_NAME, ROLE, fmt, useJson, KMH, kmhText, indexWord } from "../lib/data.js";
import { ChartTip, GRID, LABEL, TICK } from "../lib/chart.jsx";

const PART = { elbow: "팔꿈치", shoulder: "어깨", hamstring: "햄스트링", other: "다른 부위", unknown: "부위 미상" };
const ARM = new Set(["elbow", "shoulder"]);
const STATUS = { new: "신규", replacement: "시즌 중 대체", short_term: "단기 대체", resigned: "재계약" };
const LEAGUE_COLOR = { MLB: "var(--ink)", AAA: "#8e6bbf" };
const TEAM_ORDER = ["KIA", "삼성", "LG", "두산", "kt", "SSG", "롯데", "한화", "NC", "키움"];

function AlarmDot({ cx, cy, payload }) {
  if (!payload?.alarm || cx == null || cy == null) return null;
  return <circle cx={cx} cy={cy} r={4.5} fill="var(--alarm)" stroke="#fff" strokeWidth={1.2} />;
}

// 여러 시즌의 등판 구속을 한 줄로: 시즌 사이는 끊고, 리그별 색, 경보 점, IL 세로선
function CareerChart({ pitcher }) {
  const rows = pitcher.timeline.map((t, i) => ({ ...t, i: i + 1, [`velo_${t.league}_${t.season}`]: t.velo * KMH, alarm_y: t.alarm ? t.velo * KMH : null }));   // km/h로 그림   // 경보 점은 별도 data 없이 열로 (툴팁이 모든 등판에 뜨게)
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
        <Tooltip content={<ChartTip render={(payload, label) => { const r = rows[Math.round(label) - 1]; return r ? <><div><b>{r.date}</b> · {r.league} {r.season} · {r.phase === "baseline" ? "평소를 배우는 중" : "분석"}</div><div>평균 구속 {kmhText(r.velo)}{r.velo_index != null && <> · 구속 하락 지수 {fmt.num(r.velo_index)} → {indexWord(r.velo_index)}</>}{r.alarm && <span className="alarm"> · 경보</span>}</div></> : null; }} />} cursor={{ stroke: "var(--line-2)" }} />
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
        <span className={`light ${p.status === "resigned" ? "base" : p.status === "new" ? "ok" : "warn"}`}>{p.kbo_season} {STATUS[p.status] || p.status}</span>
      </div>
      {!has && <p className="caption" style={{ margin: 0 }}>{p.kbo_season}년 이전 공개 추적 기록(2021년 이후 MLB·2023년 이후 트리플A)이 없습니다(더블A 이하·독립리그·NPB·KBO 기록은 공개 추적 자료가 없음).</p>}
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
              <thead><tr><th>시즌</th><th>역할 · 주력</th><th className="num">등판 / 분석</th><th className="num">시즌 초 구속 (km/h)</th><th className="num">마지막 5등판</th><th className="num">변화</th><th className="num">경보 (구속/폼)</th><th>IL 등재</th><th></th></tr></thead>
              <tbody>
                {p.seasons.map((s) => (
                  <tr key={`${s.league}${s.season}`}>
                    <td><span className="pill" style={{ margin: 0 }}><span className="dot" style={{ background: LEAGUE_COLOR[s.league] }} />{s.league} {s.season}</span></td>
                    <td>{ROLE[s.role]} · {PITCH_NAME[s.fb] || s.fb || "—"}</td>
                    <td className="num">{s.outings} / {s.monitored}{s.monitored === 0 && <span style={{ color: "var(--muted)" }}> (시작 구간 못 채움)</span>}</td>
                    <td className="num" title={s.velo_start != null ? `${fmt.num(s.velo_start, 1)} mph` : undefined}>{s.velo_start == null ? "—" : fmt.num(s.velo_start * KMH, 1)}</td>
                    <td className="num" title={s.velo_last5 != null ? `${fmt.num(s.velo_last5, 1)} mph` : undefined}>{s.velo_last5 == null ? "—" : fmt.num(s.velo_last5 * KMH, 1)}</td>
                    <td className="num" style={{ color: s.velo_change != null && s.velo_change <= -1 ? "var(--alarm)" : "inherit" }}>{s.velo_change == null ? "—" : `${s.velo_change > 0 ? "+" : ""}${fmt.num(s.velo_change * KMH, 1)}`}</td>
                    <td className="num">{s.alarms_velo} / {s.alarms_change}</td>
                    <td>{s.il ? <span className={`light ${ARM.has(s.il.part) ? "alarm" : "base"}`} title={s.il.reason || undefined}>{fmt.date(s.il.date)} {PART[s.il.part] || s.il.part}{s.il.count > 1 && ` · ${s.il.count}회`}</span> : <span style={{ color: "var(--muted)" }}>없음</span>}</td>
                    <td>{s.replay && <Link to={`/replay?p=${s.replay}`}>리플레이 →</Link>}</td>
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
  const { data: scout } = useJson("scout.json");
  const [kboSeason, setKboSeason] = useState(null);
  const [team, setTeam] = useState("all");
  const [onlyData, setOnlyData] = useState(true);

  if (!scout) return <div className="placeholder">KBO 화면 자료를 읽는 중…</div>;
  const seasons = scout.kbo_seasons || [2026];
  const ks = kboSeason ?? seasons[0];
  const inSeason = scout.pitchers.filter((p) => (p.kbo_season ?? 2026) === ks);
  const teams = TEAM_ORDER.filter((t) => scout.pitchers.some((p) => p.team === t));
  const shown = inSeason.filter((p) => (team === "all" || p.team === team) && (!onlyData || p.seasons.length > 0))
    .sort((a, b) => TEAM_ORDER.indexOf(a.team) - TEAM_ORDER.indexOf(b.team));
  const withData = inSeason.filter((p) => p.seasons.length > 0).length;
  return (
    <div className="page">
      <h1>KBO 외국인 투수 영입 전 점검</h1>
      <p className="lead">{ks}년 KBO 외국인 투수 {inSeason.length}명 중 MLB·트리플A 공개 추적 기록이 있는 {withData}명의 미국 시절에 같은 엔진을 돌려, 영입 전에 '평소와 달라진 흐름'이 있었는지 봅니다.</p>
      <details className="more">
        <summary>자료와 한계 보기</summary>
        <p>MLB 2021~2026, 트리플A 2023~2025(Baseball Savant). 트리플A는 구장 보정 없이 MLB 한계값을 그대로 쓴 참고용입니다.
          IL 등재는 MLB(팔꿈치·어깨만 확인)와 트리플A(거래 기록, 대부분 부위 미상) 공개 기록에서 가져왔고, KBO 시즌의 부상은 들어 있지 않습니다.
          각 투수는 그 KBO 시즌까지의 미국 기록만 보여 줍니다. 명단은 시즌별 구단 발표·언론 기사(시즌 중 대체·단기 대체 포함)로 정리했습니다.</p>
      </details>
      <div className="toolbar">
        <div className="seg" role="group" aria-label="KBO 시즌">
          {seasons.map((y) => <button key={y} className={`btn ${ks === y ? "on" : ""}`} onClick={() => setKboSeason(y)}>{y}</button>)}
        </div>
        <label><span>구단</span>
          <select value={team} onChange={(e) => setTeam(e.target.value)}><option value="all">전체</option>{teams.map((t) => <option key={t}>{t}</option>)}</select>
        </label>
        <button className={`btn ${onlyData ? "on" : ""}`} onClick={() => setOnlyData(!onlyData)}>{onlyData ? "기록 있는 투수만" : "전체 보기"}</button>
        <span className="caption" style={{ margin: 0 }}>{shown.length}명 · '리플레이 →'를 누르면 그 시즌 그래프 · <span className="hover-hint">구속 그래프에 커서를 올리면 등판별 구속과 지수</span></span>
      </div>
      {shown.map((p, i) => (
        <div key={`${p.kbo_season}_${p.name}`}>
          {team === "all" && (i === 0 || shown[i - 1].team !== p.team) && <h3 className="team-head">{p.team}</h3>}
          <ScoutCard p={p} />
        </div>
      ))}
      <p className="note">한계: 영입 전 점검은 공개 기록이 있는 선수에게만 가능하고, 트리플A 결과는 참고용입니다. KBO 시즌 자체의 추적 기록은 공개돼 있지 않습니다.</p>
    </div>
  );
}
