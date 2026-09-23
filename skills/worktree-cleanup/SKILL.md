---
name: worktree-cleanup
description: >-
  베어 워크트리 컨테이너 레포에서 GitHub에 머지된 PR의 워크트리와 브랜치만 정리한다. 기본 브랜치 워크트리,
  베어 레포, 현재 워크트리, 커밋되지 않은 변경이 있는 워크트리는 건드리지 않는다. "워크트리 정리",
  "머지된 워크트리/브랜치 정리", "clean up merged worktrees", "prune merged branches", "worktree 청소" 같은 요청에 쓴다.
---

# 머지된 워크트리 정리

`<repo>/.bare`와 브랜치별 워크트리로 운영하는 레포에서, GitHub에 이미 머지된 PR의 워크트리와 로컬 브랜치를 지운다.
애매하면 건너뛰고 보고하며 `--force`는 쓰지 않는다.

## 인자

- `--dry-run`: 계획(지울 것, 건너뛸 것과 이유)만 출력하고 멈춘다.
- `--delete-remote`: 머지된 브랜치의 원격이 남아 있으면 함께 지운다. 기본은 끈다.

## 삭제 조건 (모두 만족해야 한다)

1. `gh pr list --head <branch> --state merged`가 PR을 하나 이상 반환한다. squash·rebase 머지는 merge-base가 남지 않아
   git의 머지 판정을 믿을 수 없으므로 `gh` 결과만 기준으로 삼는다.
2. 보호 대상이 아니다: 베어 항목, 기본 브랜치 워크트리, 실행을 시작한 워크트리.
3. `git -C <path> status --porcelain`이 비어 있다.

머지됐지만 2나 3을 만족하지 않으면 이유와 함께 건너뛴다.

## 절차

1. 실행을 시작한 워크트리의 절대경로를 기록한다. 기본 브랜치는 `refs/remotes/origin/HEAD`로 확인하고(없으면 GitHub로 확인)
   `main`·`master`로 가정하지 않는다. 이후 명령은 기본 브랜치 워크트리에서 실행한다.
2. `git worktree list`에 `(bare)` 항목이 없거나 워크트리가 하나뿐이면 할 일이 없다고 알리고 멈춘다.
3. `git fetch --prune origin`
4. 후보를 모은다. `git worktree list --porcelain`에서 베어와 기본 브랜치 워크트리를 뺀 워크트리, 그리고 워크트리 없는
   로컬 브랜치(`git branch --format '%(refname:short) %(worktreepath)'`에서 경로가 빈 것, 기본 브랜치 제외).
5. 후보마다 머지 여부(`gh pr list --head <branch> --state merged --json number,title,mergedAt`)와 clean 여부를 확인해
   REMOVE와 SKIP(한 줄 이유)으로 나눈다. 실행을 시작한 워크트리는 머지됐더라도 SKIP이다.
6. 계획을 출력한다. REMOVE에는 PR 번호와 mergedAt을 근거로 붙인다. `--dry-run`이면 여기서 멈춘다.
7. 삭제한다. 실패하면 강제하지 않고 SKIP으로 보고한다.
   - 워크트리: `git worktree remove <path>`
   - 로컬 브랜치: `git branch -D <branch>`. squash 머지 브랜치는 `-d`가 거부하므로, `gh`로 머지를 확인했을 때만 `-D`를 쓴다.
   - `--delete-remote`이고 `origin/<branch>`가 남아 있으면 `git push origin --delete <branch>`
8. `git worktree prune`을 실행하고, 기본 브랜치 워크트리에서 `git pull --ff-only`를 실행한다.
9. 지운 워크트리·브랜치, 건너뛴 항목과 이유, 기본 브랜치의 새 HEAD를 보고한다. 건너뛴 항목은 눈에 띄게 알린다.
   실행한 워크트리가 머지돼 건너뛰었다면 기본 브랜치 워크트리에서 다시 실행하라고 안내한다.
