import { Link, NavLink, Route, Routes, useLocation } from "react-router-dom";
import { useJson } from "./lib/data.js";
import Replay from "./pages/Replay.jsx";
import Performance from "./pages/Performance.jsx";
import HighSchool from "./pages/HighSchool.jsx";
import Bullpen from "./pages/Bullpen.jsx";
import Kbo from "./pages/Kbo.jsx";
import Watch from "./pages/Watch.jsx";
import About from "./pages/About.jsx";

const MENU = [
  { to: "/", no: "1", label: "리플레이 · 경보 카드", file: "pitchers.json" },
  { to: "/performance", no: "2", label: "성능 비교", file: "performance.json" },
  { to: "/highschool", no: "3", label: "고교 현황판", file: "highschool.json" },
  { to: "/bullpen", no: "4", label: "팀 불펜 현황판", file: "teams.json" },
  { to: "/kbo", no: "5", label: "KBO · 영입 전 점검", file: "kbo_case.json" },
  { to: "/watch", no: "6", label: "2026 시즌 현황", file: "watchlist.json" },
  { to: "/about", no: "ⓘ", label: "소개 · 방법", file: null },
];

export default function App() {
  const { data: meta } = useJson("meta.json");
  const location = useLocation();
  const current = MENU.find((m) => m.to === location.pathname) || MENU[0];
  const synthetic = meta?.synthetic?.includes(current.file);
  return (
    <div className="shell">
      <header className="topbar">
        <Link to="/" className="brand" aria-label="피치시그널 처음으로">
          <span className="mark" aria-hidden="true" />
          <span className="name">PitchSignal</span>
          <small>피치시그널 · 평소와 달라진 등판을 알리는 점검 신호</small>
        </Link>
        {synthetic && <span className="badge synthetic">가상 데이터</span>}
        {current.to === "/kbo" && <span className="badge real">MLB·트리플A 공개 기록 · 트리플A는 참고용</span>}
        {current.to === "/highschool" && !synthetic && <span className="badge real">KBSA 기록실 · 2025 전국 고교 시즌·전국체전 실제 기록</span>}
        {current.to === "/bullpen" && <span className="badge real">MLB 30개 팀 · {meta?.dev_seasons?.[0] ?? 2021}~{meta?.sealed_seasons?.[0] ?? 2026} 실제 기록</span>}
        {meta && !synthetic && current.file && !["/kbo", "/highschool", "/bullpen"].includes(current.to) && (
          <span className="badge real">{current.to === "/" ? `${meta.dev_seasons?.[0] ?? 2021}~${meta.sealed_seasons?.[0] ?? meta.seasons?.at(-1)} 실제 결과` : current.to === "/watch" ? "2026 봉인 시즌 · 10/7 평가" : `검증셋 ${meta.seasons?.join("~")} 실제 결과`}</span>
        )}
        <div className="meta">
          {meta && <span>데이터 기준일 <b>{meta.as_of}</b></span>}
          {meta && <span>버전 <b>{meta.version}</b></span>}
        </div>
      </header>
      <div className="body">
        <nav className="nav" aria-label="화면">
          <div className="section">화면</div>
          {MENU.map((m) => (
            <NavLink key={m.to} to={m.to} end className={({ isActive }) => (isActive ? "active" : "")}>
              <span className="no">{m.no}</span>{m.label}
            </NavLink>
          ))}
          <p className="hint">신호는 통계적 관리도가 낸 점검 시작 신호입니다. 판단은 사람이 합니다.</p>
        </nav>
        <main className="main">
          <Routes>
            <Route path="/" element={<Replay />} />
            <Route path="/performance" element={<Performance />} />
            <Route path="/highschool" element={<HighSchool />} />
            <Route path="/bullpen" element={<Bullpen />} />
            <Route path="/kbo" element={<Kbo />} />
            <Route path="/watch" element={<Watch />} />
            <Route path="/about" element={<About />} />
          </Routes>
          <footer className="foot">
            데이터 기준일 {meta?.as_of ?? "—"} · 출처: MLB Statcast(Baseball Savant), MLB Stats API, KBSA 기록실(2025 전국 고교 시즌 973경기·전국체전, 선수는 등번호로만 표시). '가상 데이터' 배지가 있는 화면만 실제 기록이 아닙니다.
            {" "}이 화면의 신호는 통계적 관리도가 낸 점검 시작 신호이며 부상을 예측하거나 진단하지 않습니다. 판단은 사람이 합니다.
          </footer>
        </main>
      </div>
    </div>
  );
}
