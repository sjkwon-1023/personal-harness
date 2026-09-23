# [REVIEW] 수신 규칙

이미 열린 대화형 세션이 아래 형식의 요청을 받았을 때만 적용한다. 구현 지시가 아니며, 이 요청을 처리하는 동안은
평소의 구현 규칙보다 이 문서가 우선한다.

```text
[REVIEW] 리뷰 요청. 프로토콜: <이 파일> · brief: <BRIEF> · findings: <FINDINGS> · 회신탭: #<id>
```

1. `~/.config/coding-harness/roles/reviewer.md`를 읽고 그 역할로 리뷰한다. 허용되는 쓰기는 `<FINDINGS>` 파일 하나다.
2. 결과를 `<FINDINGS>`에 쓴 뒤 요청자에게 한 번만 회신한다.

   ```bash
   mast send '#<회신탭>' '[REVIEW] 리뷰 끝났어. findings: <FINDINGS>'
   ```

   sandbox가 있는 CLI는 이 회신 명령 하나만 sandbox 밖 실행을 요청한다. 거부되면 findings 파일에 회신 실패를 적고 현재 pane에 알린다.
3. 회신한 뒤 멈추고 후속 작업을 시작하지 않는다.
