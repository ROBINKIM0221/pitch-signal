import { useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ROLE, fmt, useJson } from "../lib/data.js";
import { addDays } from "../lib/load.js";

const SIGNAL_NAME = { velo: "구속 하락", change: "폼 변화" };

/** 고른 기준일의 최근 N주 안에 경보가 울린 투수와, 그 뒤(데이터 기준일까지) 팔 부상 IL. */
function rowsFor(data, date) {
  const from = addDays(date, -(7 * data.weeks - 1));
  const by = new Map();
  for (const a of data.alarms) {
    if (a.date < from || a.date > date) continue;
    by.set(a.id, [...(by.get(a.id) || []), a]);
  }
  return [...by.entries()].map(([id, list]) => {
    const p = data.pitchers[id];
    const last = list[list.length - 1];
    const ilAfter = p.il.find((d) => d > list[0].date) || null;
    const season = data.alarms.filter((a) => a.id === id && a.date <= date);
    return { id, ...p, list, last, ilAfter, velo: season.filter((a) => a.s.includes("velo")).length, change: season.filter((a) => a.s.includes("change")).length };
  }).sort((a, b) => b.last.date.localeCompare(a.last.date) || a.name.localeCompare(b.name));
}

export default function Watch() {
  const { data } = useJson("watchlist.json");
  const [params, setParams] = useSearchParams();
  const date = data ? (params.get("d") >= data.start && params.get("d") <= data.as_of ? params.get("d") : data.as_of) : null;
  const rows = useMemo(() => (data && date ? rowsFor(data, date) : []), [data, date]);
  if (!data) return <div className="placeholder">2026 시즌 현황을 읽는 중…</div>;
  const t = data.season_totals;
  const withIl = rows.filter((r) => r.ilAfter).length;
  const setDate = (d) => d && setParams({ d }, { replace: true });
  return (
    <div className="page">
      <h1>{data.season} 시즌 경보 현황</h1>
      <p className="lead">구단 분석 파트가 등판 다음 날 아침에 보는 화면입니다. 고른 날짜까지 최근 {data.weeks}주 안에 경보가 울린 MLB 투수와, 그 뒤 팔 부상 IL에 올랐는지를 보여 줍니다.</p>
      <div className="toolbar">
        <label><span>기준일</span>
          <button className="btn" onClick={() => setDate(addDays(date, -7) < data.start ? data.start : addDays(date, -7))} aria-label="1주 전">◀ 1주</button>
          <input className="text" type="date" value={date} min={data.start} max={data.as_of} onChange={(e) => setDate(e.target.value)} />
          <button className="btn" onClick={() => setDate(addDays(date, 7) > data.as_of ? data.as_of : addDays(date, 7))} aria-label="1주 뒤">1주 ▶</button>
        </label>
        <span className="caption" style={{ margin: 0 }}>{fmt.date(addDays(date, -(7 * data.weeks - 1)))} ~ {fmt.date(date)} · 데이터 기준일 {data.as_of}</span>
      </div>
      <div className="kpi">
        <div><div className="v">{rows.length}<span className="sub"> 명</span></div><div className="l">최근 {data.weeks}주 경보가 울린 투수</div></div>
        <div><div className="v">{withIl}<span className="sub"> 명</span></div><div className="l">그 뒤 팔 부상 IL에 오른 투수</div></div>
        <div><div className="v">{t.velo}<span className="sub"> / {t.change}</span></div><div className="l">시즌 전체 경보 · 구속 하락 / 폼 변화</div></div>
        <div><div className="v">{t.pitcher_seasons.toLocaleString()}<span className="sub"> 명</span></div><div className="l">시즌에 분석한 투수</div></div>
      </div>
      <div className="card">
        <div className="card-head">
          <h2>경보 투수 <span style={{ color: "var(--muted)", fontWeight: 500, fontSize: 13 }}>최근 경보 날짜순 · 이름을 누르면 리플레이</span></h2>
        </div>
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr><th>투수</th><th>역할</th><th>경보 날짜</th><th>신호</th><th className="num">경보 때 지수 (구속 / 폼)</th><th>그 뒤 팔 부상 IL</th><th className="num">시즌 경보 (구속/폼)</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className={r.ilAfter ? "hl" : ""}>
                  <td><Link to={`/replay?p=${r.id}`}>{r.name}</Link></td>
                  <td>{ROLE[r.role]}</td>
                  <td>{r.list.map((a) => fmt.date(a.date)).join(", ")}</td>
                  <td>{[...new Set(r.list.flatMap((a) => a.s))].map((s) => <span key={s} className={`light ${s === "velo" ? "velo" : "change"}`} style={{ marginRight: 4 }}>{SIGNAL_NAME[s]}</span>)}</td>
                  <td className="num">{fmt.num(r.last.vi)} / {fmt.num(r.last.ci)}</td>
                  <td>{r.ilAfter ? <span className="light alarm">IL {fmt.date(r.ilAfter)}</span> : <span style={{ color: "var(--muted)" }}>없음</span>}</td>
                  <td className="num">{r.velo} / {r.change}</td>
                </tr>
              ))}
              {rows.length === 0 && <tr><td colSpan={7} style={{ color: "var(--muted)", textAlign: "center" }}>이 기간에는 경보가 없습니다</td></tr>}
            </tbody>
          </table>
        </div>
        <p className="note">IL 등재는 데이터 기준일({data.as_of})까지의 공개 기록만 반영합니다. 지수는 1을 넘으면 경보이며, 경보는 점검을 시작하라는 뜻이지 부상 판정이 아닙니다.</p>
      </div>
    </div>
  );
}
