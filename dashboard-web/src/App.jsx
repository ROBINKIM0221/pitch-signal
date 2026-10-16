import { Link, NavLink, Route, Routes, useLocation } from "react-router-dom";
import { useJson } from "./lib/data.js";
import Replay from "./pages/Replay.jsx";
import Performance from "./pages/Performance.jsx";
import HighSchool from "./pages/HighSchool.jsx";
import Bullpen from "./pages/Bullpen.jsx";
import Kbo from "./pages/Kbo.jsx";
import Watch from "./pages/Watch.jsx";
import About from "./pages/About.jsx";

// 화면 순서 (2026-10-16 외부 검토 반영): 한국 적용(고교)을 맨 앞에. 성능 비교는 메뉴에서 빼고 리플레이 아래 검증 요약으로 옮긴다(주소는 남김).
const MENU = [
  { to: "/", label: "고교 현황판", file: "highschool.json" },
  { to: "/replay", label: "리플레이 · 경보 카드", file: "pitchers.json" },
  { to: "/bullpen", label: "팀 불펜 현황판", file: "teams.json" },
  { to: "/kbo", label: "KBO 영입 전 점검", file: "kbo_case.json" },
  { to: "/watch", label: "시즌 감시 현황", file: "watchlist.json" },
  { to: "/about", label: "소개", file: null },
];
const ROUTES = [...MENU, { to: "/performance", label: "성능 비교", file: "performance.json" }];

export default function App() {
  const { data: meta } = useJson("meta.json");
  const location = useLocation();
  const current = ROUTES.find((m) => m.to === location.pathname) || MENU[0];
  const synthetic = meta?.synthetic?.includes(current.file);
  return (
    <div className="shell">
      <header className="topbar">
        <div className="topbar-in">
          <Link to="/" className="brand" aria-label="피치시그널 처음으로">
            <span className="mark" aria-hidden="true" />
            <span className="name">PitchSignal</span>
          </Link>
          <nav className="nav" aria-label="화면">
            {MENU.map((m) => (
              <NavLink key={m.to} to={m.to} end className={({ isActive }) => (isActive ? "active" : "")}>{m.label}</NavLink>
            ))}
          </nav>
          <div className="meta">{meta && <>데이터 기준일 <b>{meta.as_of}</b></>}</div>
        </div>
      </header>
      <div className="subbar">
        <div className="subbar-in">
          <span>투수의 평소와 달라진 등판을 알리는 점검 신호</span>
          {synthetic && <span className="badge synthetic">가상 데이터</span>}
          {current.to === "/kbo" && <span className="badge real">MLB·트리플A 공개 기록</span>}
          {current.to === "/" && !synthetic && <span className="badge real">KBSA 기록실 2025 실제 기록</span>}
          {current.to === "/bullpen" && <span className="badge real">MLB 30개 팀 {meta?.dev_seasons?.[0] ?? 2021}~{meta?.sealed_seasons?.[0] ?? 2026} 실제 기록</span>}
          {meta && !synthetic && current.file && ["/replay", "/watch", "/performance"].includes(current.to) && (
            <span className="badge real">{current.to === "/replay" ? `MLB ${meta.dev_seasons?.[0] ?? 2021}~${meta.sealed_seasons?.[0] ?? meta.seasons?.at(-1)} 실제 결과` : current.to === "/watch" ? "2026 봉인 시즌" : `검증셋 ${meta.seasons?.join("~")}`}</span>
          )}
        </div>
      </div>
      <div className="body">
        <main className="main">
          <Routes>
            <Route path="/" element={<HighSchool />} />
            <Route path="/replay" element={<Replay />} />
            <Route path="/performance" element={<Performance />} />
            <Route path="/highschool" element={<HighSchool />} />
            <Route path="/bullpen" element={<Bullpen />} />
            <Route path="/kbo" element={<Kbo />} />
            <Route path="/watch" element={<Watch />} />
            <Route path="/about" element={<About />} />
          </Routes>
          <footer className="foot">
            출처: MLB Statcast(Baseball Savant) · MLB Stats API · KBSA 기록실. 데이터 기준일 {meta?.as_of ?? "—"} · 버전 {meta?.version ?? "—"}<br />
            이 사이트의 신호는 점검을 시작할 때를 알리는 것이며, 부상을 예측하거나 진단하지 않습니다. 판단은 사람이 합니다.
          </footer>
        </main>
      </div>
    </div>
  );
}
