import { useEffect, useState } from "react";

// 데이터는 public/data/ 의 JSON에서 읽는다. 첫 화면은 목록과 투수 한 명 파일만 읽고, 나머지는 화면을 열 때 읽는다.
const BASE = import.meta.env.BASE_URL;
const cache = new Map();

export async function loadJson(name) {
  if (!cache.has(name)) {
    const request = fetch(`${BASE}data/${name}`).then((r) => {
      if (!r.ok) throw new Error(`${name}: ${r.status}`);
      return r.json();
    });
    request.catch(() => cache.delete(name));            // 실패한 요청은 기억하지 않아 다시 시도할 수 있게
    cache.set(name, request);
  }
  return cache.get(name);
}

export function useJson(name) {
  const [state, setState] = useState({ data: null, error: null });
  useEffect(() => {
    let alive = true;
    setState({ data: null, error: null });
    if (!name) return undefined;
    loadJson(name).then((data) => alive && setState({ data, error: null }))
      .catch((error) => alive && setState({ data: null, error }));
    return () => { alive = false; };
  }, [name]);
  return state;
}

export const fmt = {
  pct: (v, d = 1) => (v == null || Number.isNaN(v) ? "—" : `${Number(v).toFixed(d)}%`),
  num: (v, d = 2) => (v == null || Number.isNaN(v) ? "—" : Number(v).toFixed(d)),
  date: (s) => (s ? s.slice(5).replace("-", "/") : ""),
};

export const ROLE = { SP: "선발", RP: "불펜" };
export const PART = { elbow: "팔꿈치", shoulder: "어깨" };
export const FEATURE = { velo: "구속 (mph)", rel_z: "수직 릴리스 (ft)", arm_angle: "팔 각도 (도)" };
