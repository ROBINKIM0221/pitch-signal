import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import { useJson } from "./lib/data.js";
import Replay from "./pages/Replay.jsx";
import Performance from "./pages/Performance.jsx";
import HighSchool from "./pages/HighSchool.jsx";
import Bullpen from "./pages/Bullpen.jsx";
import Kbo from "./pages/Kbo.jsx";
import About from "./pages/About.jsx";

const MENU = [
  { to: "/", label: "① 리플레이 · ② 경보 카드", file: "replay_index.json" },
  { to: "/performance", label: "③ 성능 비교", file: "performance.json" },
  { to: "/highschool", label: "④ 고교 현황판", file: "highschool.json" },
  { to: "/bullpen", label: "⑤ 불펜 부하", file: "bullpen.json" },
  { to: "/kbo", label: "⑥ KBO 사례", file: "kbo_case.json" },
  { to: "/about", label: "소개 · 방법", file: null },
];

export default function App() {
  const { data: meta } = useJson("meta.json");
  const location = useLocation();
  const current = MENU.find((m) => m.to === location.pathname) || MENU[0];
  const synthetic = meta?.synthetic?.includes(current.file);
  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">PitchSignal<small>피치시그널 · 평소와 달라진 등판을 알리는 점검 신호</small></div>
        {synthetic && <span className="badge synthetic">가상 데이터</span>}
        {meta && !synthetic && current.file && <span className="badge real">검증셋 {meta.seasons?.join("~")} 실제 결과</span>}
        <div className="meta">
          {meta && <span>데이터 기준일 {meta.as_of}</span>}
          {meta && <span>버전 {meta.version}</span>}
        </div>
      </header>
      <div className="body">
        <nav className="nav">
          <div className="section">화면</div>
          {MENU.map((m) => (
            <NavLink key={m.to} to={m.to} end className={({ isActive }) => (isActive ? "active" : "")}>{m.label}</NavLink>
          ))}
        </nav>
        <main className="main">
          <Routes>
            <Route path="/" element={<Replay />} />
            <Route path="/performance" element={<Performance />} />
            <Route path="/highschool" element={<HighSchool />} />
            <Route path="/bullpen" element={<Bullpen />} />
            <Route path="/kbo" element={<Kbo />} />
            <Route path="/about" element={<About />} />
          </Routes>
          <footer className="foot">
            데이터 기준일 {meta?.as_of ?? "—"} · 출처: MLB Statcast(Baseball Savant), MLB Stats API. 고교·KBO 화면은 '가상 데이터' 배지가 있으면 실제 기록이 아닙니다.
            {" "}이 화면의 신호는 통계적 관리도가 낸 점검 시작 신호이며 부상을 예측하거나 진단하지 않습니다. 판단은 사람이 합니다.
          </footer>
        </main>
      </div>
    </div>
  );
}
