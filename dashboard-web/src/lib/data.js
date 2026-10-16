import { useEffect, useState } from "react";

// 데이터는 public/data/ 의 JSON에서 읽는다. 첫 화면은 목록과 투수 한 명 파일만 읽고, 나머지는 화면을 열 때 읽는다.
const BASE = import.meta.env.BASE_URL;
const cache = new Map();

export async function loadJson(name) {
  if (!cache.has(name)) {
    // 빌드마다 바뀌는 번호를 붙여, 화면 코드는 새 것인데 JSON만 옛 캐시가 남는 일을 막는다 (GitHub Pages 캐시 10분)
    const request = fetch(`${BASE}data/${name}?v=${typeof __BUILD__ === "undefined" ? "dev" : __BUILD__}`).then((r) => {
      if (!r.ok) throw new Error(`${name}: ${r.status}`);
      return r.json();
    });
    request.catch(() => cache.delete(name));            // 실패한 요청은 기억하지 않아 다시 시도할 수 있게
    cache.set(name, request);
  }
  return cache.get(name);
}

export function useJson(name) {
  const [state, setState] = useState({ name: null, data: null, error: null });
  useEffect(() => {
    let alive = true;
    if (!name) return undefined;
    loadJson(name).then((data) => alive && setState({ name, data, error: null }))
      .catch((error) => alive && setState({ name, data: null, error }));
    return () => { alive = false; };
  }, [name]);
  // 파일 이름이 바뀐 직후 한 번은 이전 파일의 자료가 state에 남아 있다 — 지금 이름의 자료만 돌려준다
  // (2026-10-16: 고교 시즌 화면에서 '전국체전' 탭을 누르면 대회 설정 + 시즌 자료로 그려 화면 전체가 멈추던 것)
  return state.name === name ? { data: state.data, error: state.error } : { data: null, error: null };
}

export const fmt = {
  pct: (v, d = 1) => (v == null || Number.isNaN(v) ? "—" : `${Number(v).toFixed(d)}%`),
  num: (v, d = 2) => (v == null || Number.isNaN(v) ? "—" : Number(v).toFixed(d)),
  date: (s) => (s ? s.slice(5).replace("-", "/") : ""),
};

export const ROLE = { SP: "선발", RP: "불펜" };
export const PART = { elbow: "팔꿈치", shoulder: "어깨" };
export const FEATURE = { velo: "평균 구속 (km/h)", rel_z: "공 놓는 높이 (cm)", arm_angle: "팔 각도 (도)" };
// MLB 자료는 mph — 화면에는 km/h로 보이고 mph는 괄호로 (2026-10-16 외부 검토: "야구빠 아니면 바로 계산 안 됨")
export const KMH = 1.609344;
export const kmhText = (mph, d = 1) => (mph == null || Number.isNaN(mph) ? "—" : `${(mph * KMH).toFixed(d)} km/h (${Number(mph).toFixed(d)} mph)`);
/** 지수(1 넘으면 경보)를 말로 */
export const indexWord = (v) => (v == null ? "" : v >= 1 ? "경보" : v >= 0.7 ? "경보 기준에 가까움" : v >= 0.3 ? "평소와 조금 다름" : "평소 그대로");
export const FEATURE_HELP = {
  velo: "그 등판에서 던진 주력 패스트볼의 평균 구속. 최고 구속이 아닙니다 (최고 구속은 부상 전 변화가 없어 쓰지 않습니다).",
  rel_z: "공을 놓는 높이의 등판 평균 (구장 보정 뒤).",
  arm_angle: "릴리스 때 팔 각도의 등판 평균. 0도가 수평, 90도가 수직.",
};
export const PITCH_NAME = { FF: "포심", SI: "싱커", FC: "커터" };
