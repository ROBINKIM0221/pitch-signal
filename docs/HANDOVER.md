# 작업 인수인계 (2026-11-26 기준)

다음에 이 저장소를 이어서 작업할 때 먼저 읽는 문서다. 설계 근거와 변경 기록은 `docs/SPEC.md`에 있다.

## 지금 상태

- `main` = 공개 사이트(https://robinkim0221.github.io/pitch-signal/). `dashboard-web/**`이 바뀐 push만 배포된다.
- 고교 화면: 2025·2026 시즌과 전국체전은 확정된 결과다(더 바꾸지 않는다). 2027 시즌·전국체전은 설정만 들어가 있고, 자료가 생기면 메뉴에 나타난다.
- 확인 명령과 지금 결과
  - `.venv\Scripts\python.exe -m pytest -q` → 355 passed, 1 skipped
  - `dashboard-web`에서 `node --test` → 25 통과, `npm run build` → 성공

## 2027 시즌 주간 갱신 (2026-11-25~26에 추가)

한 번 도는 순서: 새 경기 받기 → `17_kbsa_records`(투구수 현황판) → `18_scoresheets list·read·rows·score·innings --dataset korea_2027`(기록지 판독) → `19_reread plan·render`(다시 읽을 타석 묶음) → 다시 읽기 → `18_scoresheets score·innings --dataset korea_2027` → `13_export_dashboard` → `16_scout` → 커밋.

저장소 안에 있는 것

| 파일 | 내용 |
|---|---|
| `config_kbsa.yaml` | `korea_2027`·`tournament_2027` 데이터셋(`live: true`). 권역·대회·전국체전 경기를 경기 목록의 리그 이름에서 정한다 |
| `src/common/hs_records.py` | `resolve_dataset`(경기 목록이 없거나 대회가 덜 끝났으면 건너뜀), `source_of`, `updated_info` |
| `src/17_kbsa_records.py` | 주간 갱신 데이터셋은 문제가 있는 경기만 빼고 `data/processed/hs_<key>_quarantine.csv`에 적는다 |
| `src/18_scoresheets.py` | `--dataset KEY`: 그 데이터셋 경기만 계산하고 다른 시즌 줄은 그대로 둔다 |
| `src/19_reread.py`, `src/common/reread.py` | 다시 읽을 타석 고르기, 60타석 묶음, 타석 칸 그림 |
| `dashboard-web/src/lib/updated.js` | 화면의 '마지막 갱신' 줄 |

저장소 밖에 있는 것 (실명 원자료와 수집 스크립트는 저장소에 두지 않는다)

- 주간 실행기, 협회 기록실 수집, 다시 읽기 호출(이미지를 읽는 AI 에이전트), 2025·2026 불변 검사, 테스트 91개: 작업 노트북의 `C:\work\private\pitchsignal\weekly\`
- 그 폴더에서 먼저 볼 것: `README_운영.md`(운영 안내), `진행기록.md`(만들면서 내린 판단과 미뤄 둔 것), 설계·계획 문서, `rehearsal_report.md`
- 예약 실행(Windows 작업 스케줄러): `PitchSignal-weekly` 월요일 04:00(전 과정), `PitchSignal-reread` 목요일 04:00(밀린 다시 읽기만). 2027-03-01부터 2027-11-30까지
- 확인할 일이 생기면 작업 노트북 바탕화면에 `PitchSignal_주간갱신_확인필요.txt`가 생긴다

재 둔 숫자

- 다시 읽기 품질(영상과 짝지은 1,236타석): 모델 판독만 76.4%, 다시 읽기 적용 91.7% (기준 88%)
- 예행연습(2026년 4월 19경기를 새 시즌처럼 넣음): 20분, 기록지 38장 판독이 실제 결과와 동일, 볼 비율 평균 차 0.36%p, 범위 밖 줄 변화 없음

## 2027년 3월에 할 일

1. 저장소를 `main`에 둔다(다른 브랜치면 화면 자료를 만들지 않고 알림만 남긴다).
2. 판독 에이전트 로그인을 점검한다: `python run_weekly.py --self-test` (저장소 밖 폴더에서).
3. 첫 실행(2027-03-01 뒤 노트북을 처음 켰을 때) 결과는 커밋만 되고 웹에는 올라가지 않는다. 화면을 확인한 뒤 `python run_weekly.py --enable-push`로 자동 올리기를 켠다.

## 하지 말 것

- `18_scoresheets`의 `read·rows·score·innings`를 `--dataset` 없이 돌리지 않는다. 2025·2026의 다시 읽기 원본은 2026-10-31에 정리해 남아 있지 않으므로, 전체를 다시 계산하면 두 시즌 결과가 더 나쁜 값으로 덮인다. 바뀌었는지는 저장소 밖 `invariants.py check`로 본다(`같음`이 나와야 한다).
- `config.yaml`, `config_calibrated.yaml`, `src/core/`는 고치지 않는다.
- 번호가 붙은 모듈(`src/NN_*.py`)끼리 import하지 않는다. 함께 쓰는 로직은 `src/common/`에 둔다.
- 줄 끝은 LF, 커밋 메시지는 한국어.

## 남은 일과 알려진 한계

- 2027 실제 자료로는 아직 한 번도 돌지 않았다. 협회 기록실의 2027 페이지 구조가 달라졌으면 첫 실행에서 알림이 뜨고 화면은 그대로 남는다.
- 2024 시즌은 하지 않기로 했다.
- 기록지 사진 링크가 하나라도 있으면 '다 받은 경기'로 본다. 한 팀 기록지가 늦게 올라온 경기는 그 팀 볼 비율이 빠질 수 있다.
- 전국체전은 '경기 수 = 팀 수 − 1'일 때 끝난 것으로 본다. 3·4위전이 생기면 2027 전국체전 화면이 뜨지 않는다(시즌 화면은 무관).
- 수집은 6일에 한 번 이하다. 늦게 돈 주 다음 주는 건너뛸 수 있어 자료가 최대 2주 늦는다.
- 미뤄 둔 작은 것: 같은 알림이 매주 다시 적힘, 여러 주 새 경기가 없어도 알림 없음, 상태 파일 쓰기가 원자적이지 않음, 새 경기가 없어도 실행마다 `meta.json` 커밋이 생김. 자세한 목록은 `진행기록.md`의 'minor (deferred)' 줄.
