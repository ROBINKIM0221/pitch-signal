import { Link } from "react-router-dom";
import { ROLE, fmt, useJson } from "../lib/data.js";

const SIGNAL_NAME = { velo: "구속 하락", change: "폼 변화" };

export default function Watch() {
  const { data } = useJson("watchlist.json");
  const { data: perf } = useJson("performance.json");
  if (!data) return <div className="placeholder">2026 시즌 현황을 읽는 중…</div>;
  const t = data.season_totals;
  const sealed = perf?.sealed;
  const velo = sealed?.results.find((r) => r.method === "구속 하락 신호" && r.group === "all");
  const h3 = sealed?.tests.find((x) => x.test.startsWith("H3"));
  const h1 = sealed?.tests.find((x) => x.test.startsWith("H1"));
  const withIl = data.rows.filter((r) => r.il_after).length;
  return (
    <div className="page">
      <h1>2026 시즌 감시 현황</h1>
      <p className="lead">
        2026 시즌은 평가 계획을 고정할 때 봉인해 두었다가 <b>10월 7일 한 번</b> 평가했습니다(코드·설정은 고정 때 그대로). 이 화면은 그 결과를 실제 운영 화면처럼 보여 줍니다:
        데이터 기준일({data.as_of}) 기준 최근 {data.weeks}주({fmt.date(data.since)}~) 안에 경보가 울린 투수 목록입니다. 신호는 점검을 시작하라는 뜻이고, 판단은 사람이 합니다.
      </p>
      <div className="kpi">
        <div><div className="v">{t.pitcher_seasons.toLocaleString()}</div><div className="l">2026 감시 투수-시즌 (감시 등판 {t.outings.toLocaleString()}개)</div></div>
        <div><div className="v">{t.velo} <span style={{ color: "var(--muted)", fontWeight: 500 }}>/ {t.change}</span></div><div className="l">시즌 경보 수 · 구속 하락 / 폼 변화</div></div>
        <div><div className="v">{data.rows.length}</div><div className="l">최근 {data.weeks}주 경보가 울린 투수 · 그중 뒤에 팔 부상 IL {withIl}명</div></div>
        {velo && <div><div className="v">{fmt.num(velo.false_alarms_per100, 2)}<span style={{ color: "var(--muted)", fontWeight: 500, fontSize: 14 }}> /100</span></div><div className="l">2026 대조군 실측 오경보(구속 하락 신호) → H3 {h3?.supported ? "지지" : "지지 안 됨"} (설계 1.0, 허용 2.0)</div></div>}
      </div>
      {sealed && (
        <p className="notice">
          봉인 평가 요약: 사례 {velo?.cases}건·대조군 {velo?.controls}명. 구속 하락 신호 창 지수 일치도 {fmt.num(h1?.value, 3)} (95% 구간 {fmt.num(h1?.ci_lo, 3)}~{fmt.num(h1?.ci_hi, 3)}) → <b>H1 {h1?.supported ? "지지" : "지지 안 됨"}</b>,
          탐지 {fmt.pct(velo?.detection)} vs 대조군 창 안 경보 {fmt.pct(velo?.control_window)}, 선행 중앙값 {fmt.num(velo?.median_lead, 1)}등판 → <b>H2 {sealed.tests.find((x) => x.test.startsWith("H2"))?.supported ? "지지" : "지지 안 됨"}</b>,
          실측 오경보 두 신호 모두 설계값의 2배 이내 → <b>H3 지지</b>. 결과는 좋든 나쁘든 그대로 보고합니다(자세한 표는 성능 비교 화면의 '봉인 2026' 탭).
        </p>
      )}
      <div className="card">
        <div className="card-head">
          <h2>최근 {data.weeks}주 경보 투수 <span style={{ color: "var(--muted)", fontWeight: 500 }}>· 최근 경보 날짜순</span></h2>
          <span className="caption" style={{ margin: 0 }}>이름을 누르면 리플레이로 갑니다</span>
        </div>
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr><th>투수</th><th>역할</th><th>최근 경보</th><th>신호</th><th className="num">마지막 등판 지수 (구속 / 폼)</th><th>그 뒤 팔 부상 IL</th><th className="num">시즌 경보 (구속/폼)</th><th className="num">감시 등판</th></tr></thead>
            <tbody>
              {data.rows.map((r) => (
                <tr key={r.id} className={r.il_after ? "hl" : ""}>
                  <td><Link to={`/?p=${r.id}`}>{r.name}</Link></td>
                  <td>{ROLE[r.role]}</td>
                  <td>{r.alarm_dates.map((d) => fmt.date(d)).join(", ")}</td>
                  <td>{r.signals.map((s) => <span key={s} className={`light ${s === "velo" ? "velo" : "change"}`} style={{ marginRight: 4 }}>{SIGNAL_NAME[s]}</span>)}</td>
                  <td className="num">{fmt.num(r.velo_index)} / {fmt.num(r.change_index)}</td>
                  <td>{r.il_after ? <span className="light alarm">IL {fmt.date(r.il_after)}</span> : <span style={{ color: "var(--muted)" }}>없음(기준일까지)</span>}</td>
                  <td className="num">{r.alarms_velo} / {r.alarms_change}</td>
                  <td className="num">{r.n_mon}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="note">시즌 막바지(9월)라 경보 뒤 IL 등재는 데이터 기준일({data.as_of}) 안에서만 확인됩니다. 정규시즌 뒤 부상 소식은 반영되지 않습니다.</p>
      </div>
    </div>
  );
}
