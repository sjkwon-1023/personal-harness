# mast pane 위임 수신 규칙

`[HARNESS]` 메시지가 이 문서와 `request.json`을 가리킬 때만 적용한다.
역할별 규칙은 첫 프롬프트로 받은 역할 지침(`role_file`)을 따른다.

## 수신

1. `request.json`의 id, role, cli, model_id, workdir, output_dir, target_tab, reply_tab, helper를 읽는다.
   `MAST_TAB`이 target_tab과 다르거나 자신의 실행 모델이 요청과 다르면 수행하지 않고 현재 pane에 알린다.
2. 요청 파일에 적힌 절대경로를 그대로 써서 수신을 확인한다.

   ```bash
   python3 <helper> ack --request <request.json>
   ```

3. `<output_dir>/brief.md`와 workdir의 프로젝트 지침을 읽는다. worker가 아닌 역할은 cwd가 결과 디렉터리이므로 코드는 workdir 절대경로로 조회한다.

추가 에이전트 생성, 다른 AI CLI 실행, 다른 작업 지휘, 상태 폴링은 하지 않는다. 역할 지침보다 넓은 권한이 필요하면 그 사실을 보고하고 멈춘다.

## 결과와 회신

1. `<output_dir>/result.md`에 결과 전체를 한국어로 쓰고, 게이트 출력은 output_dir에 남긴다.
2. 모든 기록을 마친 뒤 마지막 도구 호출로 한 번만 실행한다.

   ```bash
   python3 <helper> finish --request <request.json> --outcome completed
   ```

   요청을 수행할 수 없거나 worker 게이트가 실패했을 때만 `--outcome blocked`를 쓴다. 검수에서 지적 사항을 찾았더라도 검수를 마쳤으면 `completed`다.
3. helper가 결과를 확인하고 메인 pane에 `[HARNESS-DONE]`을 보낸다. sandbox가 있는 CLI는 이 명령만 sandbox 밖 실행을 요청한다. 거부되면 결과는 그대로 두고 회신 실패를 현재 pane에 알리며, sandbox 안에서 재시도하지 않는다.
4. 짧게 완료를 표시하고 턴을 끝낸다. 이후 파일을 고치거나 다음 지시를 기다리는 도구를 호출하지 않고, 같은 회신을 반복하지 않는다.
