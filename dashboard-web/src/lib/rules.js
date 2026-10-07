// KBSA 투구수 규정을 화면에서 앞으로 계산한다 (투수 운용 계획판). 정의는 src/core/kbsa_rules.py와 같다:
//   투구 수별 의무 휴식일 r(표의 상한을 넘으면 마지막 값) — d일에 던졌다면 d + r + 1일부터 등판 가능,
//   3일 연속 등판 금지 — 어제와 그제 모두 던졌으면 오늘은 불가.
import { addDays } from "./load.js";

export function requiredRest(pitches, table) {
  for (const [upper, rest] of table) if (pitches <= upper) return rest;
  return table[table.length - 1][1];
}

/** 마지막 등판 기준 다음 등판 가능일. outings: [{date, pitches}] (pitches null = 모름 → date null). 등판이 없으면 null. */
export function nextEligible(outings, table) {
  if (!outings.length) return null;
  const last = [...outings].sort((a, b) => a.date.localeCompare(b.date)).at(-1);
  if (last.pitches == null) return { date: null, rest: null, last };
  const rest = requiredRest(last.pitches, table);
  return { date: addDays(last.date, rest + 1), rest, last };
}

/** 기준일(date)에 등판할 수 있는가. 기준일 이전(당일 포함)의 등판만 본다. */
export function availability(outings, date, table) {
  const past = outings.filter((o) => o.date <= date);
  const next = nextEligible(past, table);
  const reasons = [];
  if (next && next.date == null) return { status: "판정 불가", until: null, reasons: [`${next.last.date} 등판의 투구 수를 몰라 의무 휴식일을 계산할 수 없음`], next };
  let until = null;
  if (next && next.date > date) { until = next.date; reasons.push(`${next.last.date} ${next.last.pitches}구 → 의무 휴식 ${next.rest}일, ${next.date}부터 가능`); }
  const pitched = new Set(past.map((o) => o.date));
  if (pitched.has(addDays(date, -1)) && pitched.has(addDays(date, -2))) {
    const ban = addDays(date, 1);
    reasons.push("어제·그제 연속 등판 → 3일 연속 등판 금지");
    until = until && until > ban ? until : ban;
  }
  return { status: until ? "불가" : "가용", until, reasons, next };
}
