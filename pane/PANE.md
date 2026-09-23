# mast pane 위임 절차

dispatch-plan, review-plan, peer-review가 다른 pane의 외부 모델에게 계획·구현·검수를 맡길 때 따르는 절차다.
위임받는 세션은 같은 폴더의 `PROTOCOL.md`를 따른다.

## 규칙

- 외부 역할은 화면에 보이는 새 대화형 세션으로 실행한다. `codex exec`, `claude -p` 같은 headless 실행, 이전 세션 resume·fork, CLI 내장 서브에이전트로 바꾸지 않는다.
- 사용자가 지정한 CLI·모델·effort·pane이 `routing.json` 기본값보다 우선한다. 지정한 모델이 없거나 실패하면 보고하고 다른 모델로 대체하지 않는다.
- 사용자가 지정했거나 이 작업용으로 확인한 빈 shell pane에만 보낸다. 다른 작업의 세션은 종료하지 않는다.
- 전송 후 요청과 상태를 실행 기록에 남기고 턴을 끝낸다. `[HARNESS-DONE]` 회신이 오면 이어가고, 기다리는 동안 상태 조회·재전송을 하지 않는다.
- `sent`(전송 시도), `launched`(CLI 시작), `received`(수신 확인), `reported`(결과 보고)는 모두 메인의 승인이 아니다. mast의 exit 0도 전달을 보장하지 않는다. 회신이 없거나 결과가 비어 있으면 실패로 보고, 실제 pane과 `status.json`을 한 번 확인한 뒤 사용자에게 알린다.
- 결과는 `result.md`, 실제 diff, 게이트 로그로 인수한다. findings는 코드로 직접 대조해 채택·기각 근거를 남긴다.

## 요청 보내기

실행 기록은 `~/.local/share/coding-harness/runs/<task-id>/`에 둔다. `mast id`, `mast ls`로 대상 pane ID를 확인하고 요청을 만든 뒤 보낸다.

```bash
H=~/.config/coding-harness/pane/pane-role.py
python3 $H prepare --role <역할> --model <cli>:<등급> --target-tab <ID> \
  --workdir /abs/worktree --brief /abs/brief.md --output-dir /abs/runs/<task-id>/<단계>
python3 $H send --request /abs/runs/<task-id>/<단계>/request.json
```

- `--role`: `plan`, `plan-review`, `review`, `worker`. helper가 맞는 `roles/*.md`를 요청의 `role.md`로 복사해 첫 프롬프트에 넣는다.
- `--model`: `codex:top`처럼 `<cli>:<등급>`으로 준다. 등급별 모델 ID는 레포 루트 `models.json`에만 있다. 목록에 없는 모델은 `--cli claude|codex|opencode|agy`와 그 CLI의 정확한 모델 ID를 준다.
- `--effort`: 선택. 생략하면 `models.json`에 정한 effort, 거기도 없으면 Codex는 high, 나머지는 각 CLI 기본값을 쓴다. OpenCode는 지정할 수 없다.
- 계획·검수의 `--output-dir`는 프로젝트 밖이어야 한다.
- 브리프에는 원문 요구, 범위, 확정 제약, 관련 파일의 절대경로, 실제 검증 명령과 결과를 적는다. 큰 자료는 경로로 넘기고, 메인의 평가나 기대하는 결론은 넣지 않는다.

## 세션 닫기

보고가 끝난 세션을 닫아야 같은 pane에 새 요청을 보낼 수 있다. 보고되지 않은 세션에는 `/exit`나 새 명령을 보내지 않는다.

```bash
python3 ~/.config/coding-harness/pane/pane-role.py close --request /abs/.../request.json
```

`mast ls`에서 그 pane의 `COMMAND`가 `-`(빈 shell)로 돌아온 것을 확인한 뒤 새 요청을 보낸다.
