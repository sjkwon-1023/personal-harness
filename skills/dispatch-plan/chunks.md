# 청크 실행과 인수

dispatch-plan 3단계의 세부 절차다. 외부 모델 위임은 `~/.config/coding-harness/pane/PANE.md`를 따른다.

## 실행 기록

`~/.local/share/coding-harness/runs/<task-id>/`에 둔다. 확정 설계 문서는 프로젝트 문서 규칙을 따르고, 여기에는 그 경로와 버전만 적는다.

- `plan.md`: 원문 요구, 설계 근거와 공통 계약, 순서 있는 전체 청크 계획, 전체 게이트.
- `progress.json`: worktree 경로, 기준 commit, 계획 버전, 난이도, 현재 청크, 청크별 상태
  (`pending`/`running`/`needs-review`/`accepted`/`blocked`)와 요청 파일 경로. 청크별 `attempts`에는 원인별 `cause_id`·진단·수정 횟수·결과를
  남겨 세션이 바뀌어도 같은 원인의 누적 횟수를 잇는다. CLI·모델·pane은 각 `request.json`에 있으므로 다시 적지 않는다.
- `chunks/<id>.md`: 요구사항 ID, 선행 청크, 대상 파일, 필요한 이전 결과와 공통 계약, 완료 조건, 실제 검증 명령,
  원인별 누적 횟수와 남은 시도 횟수. 대화 기록은 복사하지 않는다.
- `checks/<id>.md`: 메인의 판정과 근거, 검증 로그 경로, 승인한 코드 상태(HEAD, tracked diff 해시, untracked 파일 경로와 내용 해시).
  미커밋 변경이 있으므로 HEAD만으로는 승인 상태를 식별할 수 없다.

계획을 고치면 버전을 올리고 영향받는 청크 자료를 갱신한다. worker가 계약을 바꾸거나 다음 청크로 넘어가게 두지 않는다.

## 청크 하나의 흐름

1. 작업 전용 worktree에서 선행 청크가 모두 `accepted`인지 확인한다. 시작 전 `git status`, tracked diff, untracked 목록을 저장해
   사용자 변경과 이번 청크를 구분한다. 같은 worktree에 worker를 동시에 돌리지 않는다.
2. `--role worker`로 요청을 보내고 `sent`를 기록한 뒤 턴을 끝낸다.
3. `[HARNESS-DONE]`이 오면 요청 ID·pane·경로를 기록과 대조한다. `outcome: blocked`면 다음 청크로 넘어가지 않는다.
4. 메인이 청크를 직접 확인한다. 새 검수 세션은 만들지 않는다.
   - 실제 diff와 새 파일이 완료 조건을 충족하는가
   - 범위 이탈이나 인터페이스·불변식 변경이 있는가
   - 이 코드 상태에 대한 실제 게이트 출력과 종료 코드가 있는가

   로그가 부족하거나 코드와 맞지 않으면 그 검증을 직접 실행한다.
5. 통과하면 `checks/<id>.md`를 남기고 `accepted`로 바꾼 뒤, 이전 세션을 닫고 다음 청크를 보낸다.
   문제가 있으면 `blocked`로 두고, 이번 작업이 만든 것으로 확인된 오류는 수정 지시를 보낸다. 같은 원인이 세션을 바꿔 3회 실패하면
   메인이 다시 판단한다. 원인 불명·환경 문제·범위 밖 수정은 먼저 보고하고, 범위·계약 변경은 사용자가 정한다.

## 재개

중단 후에는 `progress.json`, 실제 worktree, pane과 프로세스 상태를 한 번 대조한다.

- worker 생존 여부는 `status.json`의 `process_pid`·`process_start_ticks`를 `/proc/<pid>/stat`의 시작 tick과 비교해 판단한다.
  PID만 보고 종료 명령을 보내지 않고, 살아 있는 worker 위에 새 worker를 띄우지 않는다.
- `running` 표시만 보고 성공 처리하거나 `accepted` 청크를 자동으로 다시 실행하지 않는다.
- 마지막 승인 상태의 해시를 현재 코드와 비교하고, 달라졌다면 영향받는 청크와 게이트를 다시 검토한다.
- 메인 세션을 바꿀 때는 session-handoff에 실행 기록 경로, 완료·현재·다음 청크, 각 요청의 `request.json`·`result.md`·`status.json` 경로,
  메인의 인수 판정을 넣는다.
