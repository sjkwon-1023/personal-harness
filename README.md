# personal-harness

Claude Code, Codex, OpenCode, Antigravity CLI가 함께 쓰는 개인 전역 지침·스킬·역할·서브에이전트 설정이다.

| 경로 | 내용 |
|---|---|
| `AGENTS.md` | 전역 지침 |
| `skills/` | 모든 CLI 공용 스킬 |
| `claude/skills/` | Claude Code 전용 스킬 |
| `roles/` | 위임 세션에 주입하는 역할 지침 |
| `pane/` | mast pane 위임 절차, helper, 모델 별칭(`routing.json`) |
| `agents/` | 서브에이전트 본문, CLI별 모델(`agents.json`), 생성 스크립트 |
| `bin/new-worktree` | 베어 워크트리 컨테이너용 워크트리 생성 명령 |

## 설치

필요한 것: git, python3 3.9 이상(macOS는 Xcode Command Line Tools), 쓰려는 CLI의 설치와 로그인.

```bash
mkdir -p ~/code/personal-harness && cd ~/code/personal-harness
git clone --bare https://github.com/sjkwon-1023/personal-harness.git .bare
printf 'gitdir: ./.bare\n' > .git
git -C .bare config remote.origin.fetch '+refs/heads/*:refs/remotes/origin/*'
git -C .bare fetch origin
git -C .bare remote set-head origin -a
git -C .bare worktree add ../main main
./main/install.sh
```

`install.sh`는 다음을 한다. 링크가 아닌 파일이 이미 있으면 덮어쓰지 않고 알린다.

- `~/.config/coding-harness`를 이 워크트리로 링크한다. 지침과 스킬은 이 경로를 기준으로 서로를 가리킨다.
- 설치된 CLI마다 전역 지침 파일과 스킬 폴더를 링크한다.
- `~/.codex/AGENTS.md`는 mast 관리 블록을 유지한 복사본으로 갱신한다.
- `agents/sync.py`로 CLI별 서브에이전트 파일을 만든다.
- `~/.local/bin/new-worktree`를 링크하고 PATH와 CLI 설치 여부를 확인한다.

## 업데이트

`main` 워크트리에서 `git pull`하면 링크된 지침과 스킬은 바로 반영된다. `AGENTS.md`, `agents/`, 스킬 목록이 바뀌었으면
`./install.sh`를 다시 실행한다. 수정은 `new-worktree`로 만든 기능 워크트리에서 하고 PR로 머지한다.

## 레포에 두지 않는 것

인증 정보, `~/.claude/settings.json`·`~/.codex/config.toml` 같은 컴퓨터별 설정, mast가 설치하는 스킬과 훅,
claude.ai에서 동기화되는 스킬, 실행 기록(`~/.local/share/coding-harness/`).

## 제약

`pane/pane-role.py`는 `/proc`를 쓰므로 아직 macOS에서 동작하지 않는다. mast의 macOS 지원에 맞춰 옮길 예정이다.
