// 브라우저용 간이 엔진 시험. 실행: node --test dashboard-web/tests/
import { test } from "node:test";
import assert from "node:assert/strict";
import { parseInput, startUpLength, run, analyze, KMH_PER_MPH } from "../src/lib/engine.js";

const RULES = { starter_outings: 8, reliever_outings: 15, reliever_min_fastballs: 120 };
// MLB 개발셋에서 추정한 값과 같은 자릿수의 예시 (선발): σ_w 0.97 mph, Q 0.085, Σ_e 0.277, λ 0.2, k 1.656
const SP = { sigma_w: 0.97, q: 0.084764, se: 0.276989, lam: 0.2, k: 1.656 };
const PARAMS = { SP, RP: { sigma_w: 0.80, q: 0.158537, se: 0.458566, lam: 0.2, k: 1.703 } };

function season(n, velo, nFb = 50) {
  return Array.from({ length: n }, (_, i) => ({ date: `2026-04-${String(1 + i).padStart(2, "0")}`, velo: typeof velo === "function" ? velo(i) : velo, n_fb: nFb }));
}

test("parseInput reads comma, tab and spaced rows, skips the header and sorts by date", () => {
  const { rows, problems } = parseInput("날짜,직구 평균구속(km/h),직구 수\n2026-04-09\t148.7\t60\n2026.04.03, 149.2, 55, 98\n4/15 150.1 58", 2026);
  assert.deepEqual(rows.map((r) => r.date), ["2026-04-03", "2026-04-09", "2026-04-15"]);
  assert.equal(rows[0].n_all, 98);
  assert.equal(rows[1].n_all, null);
  assert.deepEqual(problems, []);
});

test("parseInput reports bad lines instead of throwing", () => {
  const { rows, problems } = parseInput("2026-13-40,149,50\n2026-04-01,0,50\n2026-04-02,149,50");
  assert.equal(rows.length, 1);
  assert.equal(problems.length, 2);
});

test("start-up length follows the role rules (SP 8 outings, RP 15 outings and 120 fastballs)", () => {
  assert.equal(startUpLength(season(30, 149), "SP", RULES), 8);
  assert.equal(startUpLength(season(30, 149, 5), "RP", RULES), 24);       // 15등판에 75구뿐 → 24등판(120구)까지
  assert.equal(startUpLength(season(30, 149, 10), "RP", RULES), 15);
  assert.equal(startUpLength(season(5, 149), "SP", RULES), 5);              // 시즌이 짧으면 있는 만큼
});

test("a steady pitcher gets no alarm and indexes near zero", () => {
  const res = run(season(30, 94 + 0.0), 8, SP);
  const mon = res.filter((r) => r.phase === "monitor");
  assert.equal(mon.length, 22);
  assert.ok(mon.every((r) => !r.alarm));
  assert.ok(mon.every((r) => Math.abs(r.index) < 0.05));
  assert.ok(Math.abs(mon[0].expected - 94) < 1e-9);
});

test("a sustained velocity drop raises an alarm within a few outings", () => {
  const res = run(season(30, (i) => (i < 15 ? 94 : 92.2)), 8, SP);     // 15번째 등판부터 1.8 mph(≈2σ_w) 하락 지속
  const first = res.findIndex((r) => r.alarm);
  assert.ok(first >= 15 && first <= 19, `first alarm at ${first}`);
  assert.ok(res[first].index > 1);
});

test("a rise in velocity never alarms (one-sided rule)", () => {
  const res = run(season(30, (i) => (i < 15 ? 94 : 96)), 8, SP);
  assert.ok(res.every((r) => !r.alarm));
  assert.ok(res.at(-1).index < 0);
});

test("fewer pitches widen the expected band", () => {
  const few = run(season(12, 94, 5), 8, SP), many = run(season(12, 94, 60), 8, SP);
  assert.ok(few[9].sd > many[9].sd);
});

test("analyze converts km/h input to mph internally and reports back in km/h", () => {
  const rows = season(20, (i) => (i < 12 ? 150 : 147.5)).map((r) => ({ ...r, n_fb: 40 }));
  const out = analyze(rows, "SP", PARAMS, RULES, "km/h");
  assert.equal(out.nStart, 8);
  assert.equal(out.outings[8].phase, "monitor");
  assert.ok(Math.abs(out.outings[8].exp.velo - 150) < 0.5);                 // 예상 구속은 km/h 단위
  assert.ok(out.alerts.length >= 1 && out.alerts[0].card.includes("km/h"));
  const mph = analyze(rows.map((r) => ({ ...r, velo: r.velo / KMH_PER_MPH })), "SP", PARAMS, RULES, "mph");
  assert.ok(Math.abs(mph.outings[8].velo_index - out.outings[8].velo_index) < 1e-6);     // 단위가 달라도 지수는 같다
});
