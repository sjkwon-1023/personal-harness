---
name: peer-review
description: 사용자가 옆 mast pane의 다른 모델에게 계획이나 변경 리뷰를 받아 달라고 할 때 요청을 전달하고 결과를 취합한다. Claude Code, Codex, OpenCode, Antigravity CLI를 지원한다.
---

# Peer Review

다른 pane의 모델에게 계획 또는 변경의 읽기 전용 리뷰를 맡긴다. 구현 위임이 아니다.
리뷰할 CLI·모델·pane은 사용자가 정한다. 정해지지 않았으면 고르지 말고 묻는다.

1. 원문 요구, 리뷰 종류(계획/변경), 대상과 범위, 실제 diff나 계획 경로, 관련 지침과 검증 결과를 브리프 파일에 적는다.
   실행 기록은 `~/.local/share/coding-harness/runs/<task-id>/`에 둔다.
2. 기본은 새 세션이다. `~/.config/coding-harness/pane/PANE.md` 절차로 변경은 `--role review`, 계획은 `--role plan-review`로 보낸다.
3. 사용자가 이미 열린 세션의 맥락을 유지하라고 했을 때만 `[REVIEW]` 경로를 쓴다. 파일 본문은 보내지 않고 한 줄만 보낸다.

   ```bash
   mast send '#<대상>' '[REVIEW] 리뷰 요청. 프로토콜: ~/.config/coding-harness/skills/peer-review/REVIEW-PROTOCOL.md · brief: <절대경로> · findings: <절대경로> · 회신탭: #<내 ID>'
   ```

요청을 보낸 뒤 턴을 끝낸다. 회신이 오면 비어 있지 않은 결과 파일을 확인하고 findings의 근거를 직접 대조한다.
`[HARNESS]`와 `[REVIEW]` 형식을 섞지 않고, 리뷰 완료를 구현 승인으로 받아들이지 않는다.
