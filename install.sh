#!/usr/bin/env bash
# personal-harness를 이 컴퓨터의 에이전트 CLI에 연결한다. 여러 번 실행해도 결과가 같다.
# macOS 기본 bash 3.2와 BSD 도구에서도 돌아야 하므로 GNU 전용 옵션과 bash 4 문법을 쓰지 않는다.
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd -P)"
HARNESS="$HOME/.config/coding-harness"

link() {
	local target="$1" path="$2"
	if [ -L "$path" ]; then
		if [ "$(readlink "$path")" = "$target" ]; then return 0; fi
		rm "$path"
	elif [ -e "$path" ]; then
		printf '건너뜀: %s 이(가) 링크가 아닌 파일로 있습니다. 확인해 옮긴 뒤 다시 실행하세요.\n' "$path" >&2
		return 0
	fi
	mkdir -p "$(dirname "$path")"
	ln -s "$target" "$path"
	printf '링크: %s -> %s\n' "$path" "$target"
}

link_skills() {
	local source="$1" dir="$2" skill path
	for skill in "$REPO/$source"/*/; do
		link "$HARNESS/$source/$(basename "$skill")" "$dir/$(basename "$skill")"
	done
	# 레포에서 지운 스킬의 링크는 끊긴 채 남으므로 하네스를 가리키는 것만 정리한다.
	for path in "$dir"/*; do
		if [ -L "$path" ] && [ ! -e "$path" ]; then
			case "$(readlink "$path")" in
			"$HARNESS"/*) rm "$path" && printf '삭제: 끊긴 링크 %s\n' "$path" ;;
			esac
		fi
	done
}

# mast가 관리 블록을 덧붙이면서 링크를 일반 파일로 바꾸므로 Codex 지침은 복사본으로 두고 블록을 보존한다.
sync_codex_agents() {
	local file="$HOME/.codex/AGENTS.md" block=""
	if [ -f "$file" ] && [ ! -L "$file" ]; then
		block="$(sed -n '/^<!-- >>> mast integration/,$p' "$file")"
	fi
	{
		cat "$HARNESS/AGENTS.md"
		if [ -n "$block" ]; then printf '\n%s\n' "$block"; fi
	} >"$file.tmp"
	if [ -f "$file" ] && [ ! -L "$file" ] && cmp -s "$file.tmp" "$file"; then
		rm "$file.tmp"
		return 0
	fi
	rm -f "$file"
	mv "$file.tmp" "$file"
	printf '갱신: %s\n' "$file"
}

# OpenCode는 disable-model-invocation을 모르므로, 명시 호출 전용 스킬은 skill 권한을 ask로 두어 자동 호출을 막는다.
sync_opencode_skill_permissions() {
	python3 - "$REPO/skills" "$HOME/.config/opencode" <<'PY'
import json
import re
import sys
from pathlib import Path

skills, config_dir = Path(sys.argv[1]), Path(sys.argv[2])
explicit = sorted(p.parent.name for p in skills.glob("*/SKILL.md")
                  if re.search(r"^disable-model-invocation:\s*true\s*$", p.read_text().split("\n---", 1)[0], re.M))
path = next((config_dir / name for name in ("opencode.jsonc", "opencode.json") if (config_dir / name).is_file()),
            config_dir / "opencode.jsonc")
wanted = {"permission": {"skill": {name: "ask" for name in explicit}}}
try:
    config = json.loads(path.read_text()) if path.is_file() else {}
except json.JSONDecodeError:
    config = None
permission = config.setdefault("permission", {}) if isinstance(config, dict) else None
if not isinstance(permission, dict):
    print(f"건너뜀: {path}을(를) 자동으로 고칠 수 없습니다(주석 등). 다음 설정을 직접 넣으세요.\n  {json.dumps(wanted)}",
          file=sys.stderr)
    sys.exit(0)
skill = permission.get("skill", {})
if isinstance(skill, str):
    skill = {"*": skill}
missing = [name for name in explicit if name not in skill]
if missing:
    skill.update({name: "ask" for name in missing})
    permission["skill"] = skill
    path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n")
    print(f"갱신: {path} (skill 권한 ask: {', '.join(missing)})")
PY
}

for tool in git python3; do
	if ! command -v "$tool" >/dev/null 2>&1; then
		printf '필수 도구가 없습니다: %s\n' "$tool" >&2
		exit 1
	fi
done

link "$REPO" "$HARNESS"

if [ -d "$HOME/.claude" ]; then
	link "$HARNESS/AGENTS.md" "$HOME/.claude/CLAUDE.md"
	link_skills skills "$HOME/.claude/skills"
fi
if [ -d "$HOME/.codex" ]; then
	sync_codex_agents
	link_skills skills "$HOME/.codex/skills"
fi
if [ -d "$HOME/.config/opencode" ]; then
	link "$HARNESS/AGENTS.md" "$HOME/.config/opencode/AGENTS.md"
	link_skills skills "$HOME/.config/opencode/skills"
	sync_opencode_skill_permissions
fi
if [ -d "$HOME/.gemini/antigravity-cli" ]; then
	link "$HARNESS/AGENTS.md" "$HOME/.gemini/GEMINI.md"
	link_skills skills "$HOME/.gemini/antigravity-cli/skills"
fi
link_skills skills "$HOME/.agents/skills"

python3 "$REPO/agents/sync.py"

link "$HARNESS/bin/new-worktree" "$HOME/.local/bin/new-worktree"
case ":$PATH:" in
*":$HOME/.local/bin:"*) ;;
*) printf '알림: ~/.local/bin이 PATH에 없습니다. 셸 설정(zsh는 ~/.zshrc)에 다음 줄을 추가하세요.\n  export PATH="$HOME/.local/bin:$PATH"\n' ;;
esac

missing=""
for cli in claude codex opencode agy gh mast; do
	if command -v "$cli" >/dev/null 2>&1; then continue; fi
	if [ "$cli" = opencode ] && [ -x "$HOME/.opencode/bin/opencode" ]; then continue; fi
	missing="$missing $cli"
done
if [ -n "$missing" ]; then
	printf '알림: 없는 명령:%s — 쓰려는 CLI는 설치 후 로그인하세요.\n' "$missing"
fi
