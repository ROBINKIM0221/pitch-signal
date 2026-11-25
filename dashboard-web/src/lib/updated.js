// 주간 갱신 자료(highschool.json 목록 항목의 updated: {run, through})의 '마지막 갱신' 줄. 그 값이 없는 자료는 줄이 없다.
export function updatedLabel(updated) {
  if (!updated) return null;
  const [, month, day] = updated.through.split("-").map(Number);
  return `마지막 갱신: ${updated.run} (경기 기록 ${month}월 ${day}일까지)`;
}
