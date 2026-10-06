import { useEffect, useMemo, useState } from "react";
import { useJson } from "../lib/data.js";
import { analyze, parseInput } from "../lib/engine.js";
import { AlertCard, Pitcher } from "./Replay.jsx";

const PART = { elbow: "팔꿈치", shoulder: "어깨", hamstring: "햄스트링" };
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

export default function Kbo() {
  const { data } = useJson("kbo_case.json");
  const { data: params } = useJson("engine_params.json");
  const saved = useMemo(load, []);
  const [name, setName] = useState(saved?.name ?? "");
  const [role, setRole] = useState(saved?.role ?? "SP");
  const [unit, setUnit] = useState(saved?.unit ?? "km/h");
  const [text, setText] = useState(saved?.text ?? "");
  const [season, setSeason] = useState(saved?.season ?? new Date().getFullYear());
  const [result, setResult] = useState(null);
  const [problems, setProblems] = useState([]);
  const [picked, setPicked] = useState(null);
  useEffect(() => { try { localStorage.setItem(STORE, JSON.stringify({ name, role, unit, text, season })); } catch { /* 저장 못 해도 동작엔 지장 없음 */ } }, [name, role, unit, text, season]);

  const run = () => {
    if (!params) return;
    const { rows, problems: bad } = parseInput(text, Number(season));
    setProblems(bad);
    if (rows.length < 3) { setResult(null); setProblems([...bad, "등판이 3개 이상 있어야 합니다."]); return; }
    const out = analyze(rows, role, params.roles, params.rules, unit);
    const label = name.trim() || "직접 입력한 투수";
    setResult({
      data: { id: "manual", manual: true, name: label, season: Number(season), role, group: "other", il_date: null,
              baseline_end: out.outings[out.nStart - 1]?.date ?? null, outings: out.outings, limits: {} },
      alerts: out.alerts.map((a) => ({ ...a, id: "manual", who: label, unit, velo_delta: a.velo, rule: "EWMA" })),
      monitored: out.monitored, nStart: out.nStart,
    });
    setPicked(null);
  };

  if (!data) return <div className="placeholder">KBO 화면 자료를 읽는 중…</div>;
  return (
    <div className="page">
      <h1>KBO · 직접 입력 분석</h1>
      <p className="lead">
        한국에는 투구 추적 데이터가 공개돼 있지 않아 MLB처럼 선수를 검색할 수는 없습니다. 대신 경기별 <b>직구 평균 구속</b>과 <b>직구 투구 수</b>를 적어 넣으면,
        1화면과 같은 엔진(움직이는 기준선 + 한 방향 EWMA)이 이 브라우저 안에서 돌아가 구속 하락 지수와 경보를 그려 줍니다. 입력한 자료는 이 기기에만 남고 어디로도 보내지 않습니다.
      </p>
      <div className="card">
        <div className="card-head">
          <h2>투수 데이터 넣기</h2>
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
        <textarea className="paste" rows={9} value={text} onChange={(e) => setText(e.target.value)} spellCheck={false}
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
      </div>
      {result && (
        <>
          <p className="caption">등판 {result.data.outings.length}개 중 시작 구간 {result.nStart}개, 감시 {result.monitored}개 · 경보 {result.alerts.length}건. 시작 구간은 {role === "SP" ? "선발 첫 8등판" : "불펜 첫 15등판과 직구 120구 중 늦은 시점"}입니다.</p>
          <Pitcher data={result.data} shown={result.data.outings.length} alerts={result.alerts} setPicked={setPicked} features={["velo"]} signals={["velo"]} unit={unit} />
        </>
      )}
      {picked && <AlertCard alert={picked} onClose={() => setPicked(null)} />}
      <div className="card">
        <h2>2026 KBO 외국인 투수 사례 <span style={{ color: "var(--muted)", fontWeight: 500 }}>· 날짜는 공개 기록</span></h2>
        <p className="caption">팔꿈치·어깨 문제로 1군에서 말소된 뒤 구단 결정까지 걸린 기간. 이 선수들의 경기별 직구 평균 구속을 위에 넣으면 같은 그래프를 볼 수 있습니다.</p>
        <div className="kpi">
          {data.pitchers.map((p) => (
            <div key={p.name}>
              <div className="v" style={{ fontSize: 18 }}>{p.name} <span style={{ color: "var(--muted)", fontWeight: 500, fontSize: 13 }}>{p.team} · {PART[p.part] || p.part}</span></div>
              <div className="l">말소 {p.removed} → 결정 {p.decision} ({p.decision_type}) · <b>{Math.round((new Date(p.decision) - new Date(p.removed)) / 86400000)}일</b><br />대체 {p.replacement} · {p.outcome}</div>
            </div>
          ))}
        </div>
        <h3>대응 사례 <span style={{ color: "var(--muted)", fontWeight: 500 }}>· 감시 대상 아님</span></h3>
        {data.response_only.map((x) => (
          <p key={x.name} className="note" style={{ margin: "4px 0" }}>
            <b>{x.name}</b> ({x.team}) · {PART[x.part] || x.part} · 말소 {x.removed} → 결정 {x.decision} ({x.decision_type}) · 대체 {x.replacement} · {x.outcome}. {x.note}
          </p>
        ))}
      </div>
      <p className="note">한계: KBO는 구속만 쓰는 사후 사례 연구입니다. 대체 후보 추천은 만들지 않고 로드맵에 둡니다.</p>
    </div>
  );
}
