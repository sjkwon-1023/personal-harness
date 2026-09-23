---
name: cross-audit
description: 사용자가 레포 간 계약 대조나 레포 전반 전수 점검을 명시적으로 요청했을 때, 발견 → Sonnet 클러스터 스크린 → 경계선·고위험 건만 심층 2렌즈 검증 순서의 워크플로로 audit을 실행한다. Claude Code 전용(Workflow 도구).
disable-model-invocation: true
allowed-tools: Workflow, Read, Bash
---

# /cross-audit

발견한 항목을 모두 비싼 모델로 검증하지 않고, Sonnet 스크린으로 거른 뒤 경계선·고위험 건만 심층 2렌즈
(반증=Opus, 재현=Sonnet)로 올린다. 에스컬레이션 판정은 스크립트 코드가 한다.

스크립트는 `~/.claude/skills/cross-audit/audit.js` 하나만 쓴다. 레포별 차이는 `args`로만 주고,
구조를 바꿀 때는 이 파일을 직접 고친다. 복사본을 만들어 고치지 않는다.

## 실행 조건

- focus(audit 질문)와 targets(대상 경로)가 명확하면 바로 실행하고, 애매하면 먼저 묻는다.
- 실행 직전에 예상 규모(발견 수에 비례해 에이전트 수십 개)를 한 줄로 알린다.
- 소규모 검토나 방금 만든 변경의 리뷰는 peer-review, 단순 탐색은 repo-scout를 쓴다.

## 절차

1. `focus`(audit 질문 한 문장)와 `targets`(name, 절대경로, 선택 hint)를 정한다. 워크스페이스 밖 레포도 절대경로면 된다.
2. 실행한다.
   ```
   Workflow({
     scriptPath: "<홈 절대경로>/.claude/skills/cross-audit/audit.js",
     args: {
       title: "<보고용 제목>",
       focus: "<audit 질문>",
       targets: [{ name: "app", path: "/abs/path", hint: "<선택>" }, ...],
       // 선택: findLenses(발견 렌즈 커스텀), finderModel('opus' 기본), clusterSize(6 기본)
     }
   })
   ```
   결과가 잘리면 출력 파일을 jq로 읽는다. 워크플로가 실패하면 `journal.jsonl`을 확인하고 실패로 보고한다.
3. 결과 `{ stats, confirmed, rejected, conflicts, gaps }`를 보고한다.
   - confirmed: 심각도순으로 근거 `file:line`과 함께. `via: 'deep'` 건은 correction을 반영한다.
   - conflicts(반증·재현 판정 불일치 또는 한쪽 실패): 직접 결론 내지 않고 양쪽 근거를 요약해 사용자에게 판단을 요청한다.
   - rejected: 건수와 대표 사례 한 줄.
   - gaps: 다음 라운드 후보.
4. 심각한 confirmed 건은 수정 계획으로 잇고, 판단이 갈리는 건은 peer-review로 다른 모델의 재검증을 제안한다.

conflicts를 임의로 confirmed나 rejected에 넣지 않는다. 같은 audit을 이 스킬 없이 수동으로 fan-out하지 않는다.
