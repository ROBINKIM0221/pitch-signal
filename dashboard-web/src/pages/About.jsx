import { Link } from "react-router-dom";
import { useJson } from "../lib/data.js";

// 소개 (2026-10-16 외부 검토: 무엇을 볼 수 있나 → 어떻게 믿을 수 있나 → 한계 세 덩어리로)
const SCREENS = [
  { to: "/", name: "고교 현황판", text: "2025 전국 고교 973경기·전국체전의 투구 수로 규정 준수와 누적 부하, 투수 운용 계획, 기록지에서 읽은 볼 비율" },
  { to: "/replay", name: "리플레이 · 경보 카드", text: "MLB 투수 시즌을 등판 단위로 되감아 경보가 언제, 왜 울렸는지와 검증 결과 요약" },
  { to: "/bullpen", name: "팀 불펜 현황판", text: "MLB 팀과 날짜를 고르면 불펜 투수마다 연투·최근 투구량 신호등과 품질 경보" },
  { to: "/kbo", name: "KBO 영입 전 점검", text: "2026 KBO 외국인 투수의 MLB·트리플A 지난 시즌에서 달라진 흐름과 IL 이력" },
  { to: "/watch", name: "시즌 감시 현황", text: "고른 날짜까지 4주 안에 경보가 울린 MLB 투수와 그 뒤 팔 부상 IL" },
];

export default function About() {
  const { data: meta } = useJson("meta.json");
  return (
    <div className="page">
      <h1>소개</h1>
      <p className="lead">피치시그널은 투수마다 '평소의 투구'를 배우고, 평소와 달라진 등판을 알려 점검을 시작할 때를 알려 주는 모니터링 시스템입니다. 부상을 예측하거나 진단하지 않으며, 판단은 사람이 합니다.</p>

      <div className="card">
        <h2>무엇을 볼 수 있나</h2>
        <div className="menu-grid">
          {SCREENS.map((s) => (
            <Link key={s.to} to={s.to}>
              <b>{s.name}</b>
              <span>{s.text}</span>
            </Link>
          ))}
        </div>
      </div>

      <div className="card">
        <h2>어떻게 믿을 수 있나</h2>
        <ul className="plain">
          <li><b>결과를 보기 전에 평가 방법을 고정했습니다.</b> 가설·지표·판정 기준을 2026년 10월 6일 공개 저장소에 고정(eval-plan-v1)한 뒤, 2024~2025 시즌에서 한 번만 계산했고 2026 시즌은 봉인했다가 10월 7일 한 번 평가했습니다.</li>
          <li><b>경보가 얼마나 자주 잘못 울리는지 먼저 정했습니다.</b> 부상 없는 투수 100등판에 한 번꼴로 울리도록 맞췄고, 공 수가 적은 짧은 등판에서도 같은 비율이 지켜지게 했습니다.</li>
          <li><b>모든 화면이 실제 공개 기록입니다.</b> MLB Statcast·MLB Stats API, 대한야구소프트볼협회(KBSA) 기록실. 가상 데이터는 없습니다.</li>
        </ul>
      </div>

      <div className="card">
        <h2>한계</h2>
        <ul className="plain">
          <li>구속이 떨어지지 않는 부상은 잡지 못합니다. 2026 봉인 시즌에서는 주 가설이 재현되지 않았습니다.</li>
          <li>고교에는 공식 부상 기록이 없어 탐지 성능을 검증할 수 없습니다. 고교 현황판은 규정이 보지 못하는 부하를 보여 주는 용도입니다.</li>
          <li>불펜에서 몸만 풀고 등판하지 않은 투구, 연습 투구는 기록에 없습니다.</li>
          <li>고교 볼 비율은 손으로 쓴 기록지를 읽은 추정값이라 약간의 오차가 있습니다.</li>
        </ul>
      </div>

      <p className="note">
        데이터: MLB 2021~2026 정규시즌(Baseball Savant), 트리플A 2023~2025, KBSA 기록실 2025 고교 시즌 973경기·전국체전 14경기와 경기 기록지. 연구·비상업 목적이며 원데이터와 기록지 사진은 공개하지 않습니다.
        학교와 선수는 협회 기록실에 공개된 이름으로 표시합니다.
        {meta && <> 데이터 기준일 {meta.as_of} · 결과 버전 {meta.version}.</>} 코드와 평가 계획: <a href="https://github.com/ROBINKIM0221/pitch-signal" target="_blank" rel="noreferrer">github.com/ROBINKIM0221/pitch-signal</a>
      </p>
    </div>
  );
}
