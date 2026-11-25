// 주간 갱신 자료의 '마지막 갱신' 줄 (highschool.json 목록 항목의 updated: {run, through})
import { test } from "node:test";
import assert from "node:assert/strict";
import { updatedLabel } from "../src/lib/updated.js";

test("the label gives the run date and the last game day", () => {
  assert.equal(updatedLabel({ run: "2027-03-08", through: "2027-03-07" }), "마지막 갱신: 2027-03-08 (경기 기록 3월 7일까지)");
  assert.equal(updatedLabel({ run: "2027-10-25", through: "2027-10-22" }), "마지막 갱신: 2027-10-25 (경기 기록 10월 22일까지)");
});

test("datasets without the field show nothing", () => {
  assert.equal(updatedLabel(undefined), null);
  assert.equal(updatedLabel(null), null);
});
