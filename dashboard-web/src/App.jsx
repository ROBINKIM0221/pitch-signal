import { Link, NavLink, Route, Routes, useLocation } from "react-router-dom";
import { useJson } from "./lib/data.js";
import Replay from "./pages/Replay.jsx";
import Performance from "./pages/Performance.jsx";
import HighSchool from "./pages/HighSchool.jsx";
import Bullpen from "./pages/Bullpen.jsx";
import Kbo from "./pages/Kbo.jsx";
import Watch from "./pages/Watch.jsx";
import About from "./pages/About.jsx";

// 메뉴 두 단 (2026-10-16 사용자): 윗단 = 큰 분류(고교 야구 / MLB·KBO), 아랫단 = 그 분류의 화면. 성능 비교는 메뉴에 없고 리플레이 아래 검증 요약에서 링크.
const GROUPS = [
  // 고교 아랫단은 자료(연도·대회)별 — 주소 ?d= 로 고른다 (현황판 안의 탭을 올림)
  { key: "hs", label: "고교 야구", items: [
    { to: "/", d: "korea_2025", label: "2025 전국 고교 시즌", file: "highschool.json" },
    { to: "/", d: "tournament_2025", label: "2025 전국체전", file: "highschool.json" },
  ] },
  { key: "pro", label: "MLB · KBO", items: [
    { to: "/replay", label: "리플레이 · 경보 카드", file: "pitchers.json" },
    { to: "/bullpen", label: "팀 불펜 현황판", file: "teams.json" },
    { to: "/kbo", label: "KBO 영입 전 점검", file: "kbo_case.json" },
    { to: "/watch", label: "시즌 감시 현황", file: "watchlist.json" },
    { to: "/performance", label: "검증 결과표", file: "performance.json", hidden: true },
  ] },
  { key: "about", label: "소개", items: [{ to: "/about", label: "소개", file: null }] },
];
const ROUTES = GROUPS.flatMap((g) => g.items.map((m) => ({ ...m, group: g.key })));
ROUTES.push({ to: "/highschool", label: "고교 투구수 현황판", file: "highschool.json", group: "hs" });

export default function App() {
  const { data: meta } = useJson("meta.json");
  const location = useLocation();
  const current = ROUTES.find((m) => m.to === location.pathname) || ROUTES[0];
  const group = GROUPS.find((g) => g.key === current.group);
  const hsKey = new URLSearchParams(location.search).get("d") || "korea_2025";
  const synthetic = meta?.synthetic?.includes(current.file);
  return (
    <div className="shell">
      <header className="topbar">
        <div className="topbar-in">
          <Link to="/" className="brand" aria-label="피치시그널 처음으로">
            <span className="mark" aria-hidden="true" />
            <span className="name">PitchSignal</span>
          </Link>
          <nav className="nav" aria-label="분류">
            {GROUPS.filter((g) => g.key !== "about").map((g) => (
              <Link key={g.key} to={g.items[0].to} className={g.key === group.key ? "active" : ""}>{g.label}</Link>
            ))}
          </nav>
          <Link to="/about" className={`about ${group.key === "about" ? "active" : ""}`}>소개</Link>
        </div>
      </header>
      <div className="subbar">
        <div className="subbar-in">
          {group.key !== "about" && (
            <nav className="subnav" aria-label="화면">
              {group.items.filter((m) => !m.hidden || m.to === current.to).map((m) => m.d ? (
                <Link key={m.d} to={{ pathname: m.to, search: `?d=${m.d}` }} className={m.d === hsKey ? "active" : ""}>{m.label}</Link>
              ) : (
                <NavLink key={m.to} to={m.to} end className={({ isActive }) => (isActive || m.to === current.to ? "active" : "")}>{m.label}</NavLink>
              ))}
            </nav>
          )}
          <span className="subbar-right">
            {synthetic && <span className="badge synthetic">가상 데이터</span>}
            {group.key === "hs" && !synthetic && <span className="badge real">KBSA 기록실 2025 실제 기록</span>}
            {group.key === "pro" && <span className="badge real">MLB Statcast · 트리플A 공개 기록</span>}
          </span>
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
