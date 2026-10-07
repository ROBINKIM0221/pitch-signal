// KBSA 투구수 규정의 '다음 등판 가능일' 계산 시험 (정의는 src/core/kbsa_rules.py와 같다: d일에 r일 휴식이 필요하면 d + r + 1일부터, 3일 연속 등판 금지)
import { test } from "node:test";
import assert from "node:assert/strict";
import { requiredRest, nextEligible, availability } from "../src/lib/rules.js";

const TABLE = [[45, 0], [60, 1], [75, 2], [90, 3], [105, 4]];

test("required rest follows the KBSA table and caps at the last row", () => {
  assert.deepEqual([0, 45, 46, 60, 61, 75, 76, 90, 91, 105, 120].map((p) => requiredRest(p, TABLE)), [0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 4]);
});

test("next eligible date comes from the last outing's pitch count", () => {
  const outings = [{ date: "2025-05-03", pitches: 30 }, { date: "2025-05-07", pitches: 77 }];
  assert.deepEqual(nextEligible(outings, TABLE), { date: "2025-05-11", rest: 3, last: { date: "2025-05-07", pitches: 77 } });
  assert.equal(nextEligible([], TABLE), null);
  assert.deepEqual(nextEligible([{ date: "2025-05-07", pitches: null }], TABLE), { date: null, rest: null, last: { date: "2025-05-07", pitches: null } });
});

test("availability on a date: mandatory rest, then the three-consecutive-days ban, then unknown pitch counts", () => {
  const outings = [{ date: "2025-05-03", pitches: 30 }, { date: "2025-05-07", pitches: 77 }];
  assert.equal(availability(outings, "2025-05-10", TABLE).status, "불가");
  assert.equal(availability(outings, "2025-05-10", TABLE).until, "2025-05-11");
  assert.equal(availability(outings, "2025-05-11", TABLE).status, "가용");
  const b2b = [{ date: "2025-05-08", pitches: 20 }, { date: "2025-05-09", pitches: 15 }];
  assert.equal(availability(b2b, "2025-05-10", TABLE).status, "불가");          // 이틀 연속 던졌으니 사흘째는 금지
  assert.match(availability(b2b, "2025-05-10", TABLE).reasons.join(" "), /3일 연속/);
  assert.equal(availability(b2b, "2025-05-11", TABLE).status, "가용");
  assert.equal(availability([{ date: "2025-05-09", pitches: null }], "2025-05-10", TABLE).status, "판정 불가");
  assert.equal(availability([], "2025-05-10", TABLE).status, "가용");
  // 기준일에 이미 던진 경우: 그날의 등판도 포함해 다음 날부터 계산
  assert.equal(availability([{ date: "2025-05-10", pitches: 50 }], "2025-05-10", TABLE).status, "불가");
  assert.equal(availability([{ date: "2025-05-10", pitches: 50 }], "2025-05-10", TABLE).until, "2025-05-12");
});

test("a hypothetical outing today pushes the next eligible date", () => {
  const outings = [{ date: "2025-05-03", pitches: 30 }];
  assert.equal(nextEligible([...outings, { date: "2025-05-10", pitches: 95 }], TABLE).date, "2025-05-15");
});
