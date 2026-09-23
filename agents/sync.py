#!/usr/bin/env python3
"""agents.json의 에이전트 설정과 <이름>.md 본문으로 각 CLI의 서브에이전트 파일을 만든다.

모델 ID와 effort는 레포 루트 models.json에서 에이전트의 tier로 찾는다. tier가 없으면 모델 줄을 쓰지 않아
그 CLI의 메인 모델을 이어받는다.
"""
import json
from pathlib import Path

SOURCE = Path(__file__).resolve().parent
MODELS = json.loads((SOURCE.parent / "models.json").read_text())
HOME = Path.home()
NOTICE = "~/.config/coding-harness/agents에서 생성한 파일이다. 원본을 고친 뒤 install.sh를 다시 실행한다."


def quoted(text):
    return json.dumps(text, ensure_ascii=False)


def claude(name, description, settings, body):
    lines = ["---", f"# {NOTICE}", f"name: {name}", f"description: {quoted(description)}"]
    lines += [f"{key}: {settings[key]}" for key in ("tools", "model", "effort") if key in settings]
    return HOME / ".claude/agents" / f"{name}.md", "\n".join(lines + ["---", "", body])


def codex(name, description, settings, body):
    if "'''" in body:
        raise ValueError(f"{name}: 본문에 '''가 있으면 TOML 리터럴 문자열로 쓸 수 없습니다")
    lines = [f"# {NOTICE}", f"name = {quoted(name)}"]
    if "model" in settings:
        lines.append(f"model = {quoted(settings['model'])}")
    if "effort" in settings:
        lines.append(f"model_reasoning_effort = {quoted(settings['effort'])}")
    lines += [f"sandbox_mode = {quoted(settings['sandbox'])}",
              f"description = {quoted(description)}",
              f"developer_instructions = '''\n{body}'''"]
    return HOME / ".codex/agents" / f"{name}.toml", "\n".join(lines) + "\n"


def opencode(name, description, settings, body):
    lines = ["---", f"# {NOTICE}", f"description: {quoted(description)}", "mode: subagent"]
    if "model" in settings:
        lines.append(f"model: {settings['model']}")
    if "permission" in settings:
        lines.append(f"permission: {quoted(settings['permission'])}")
    return HOME / ".config/opencode/agents" / f"{name}.md", "\n".join(lines + ["---", "", body])


RENDERERS = {"claude": (claude, ".claude"), "codex": (codex, ".codex"), "opencode": (opencode, ".config/opencode")}


def settings_for(name, agent, cli):
    settings = dict(agent[cli])
    tier = agent.get("tier")
    if tier is not None:
        if tier not in MODELS.get(cli, {}):
            raise ValueError(f"{name}: models.json에 {cli}의 {tier} 등급이 없습니다")
        settings.update(MODELS[cli][tier])
    return settings


def main():
    agents = json.loads((SOURCE / "agents.json").read_text())
    for name, agent in agents.items():
        body = (SOURCE / f"{name}.md").read_text()
        for cli, (render, root) in RENDERERS.items():
            if cli not in agent or not (HOME / root).is_dir():
                continue
            path, text = render(name, agent["description"], settings_for(name, agent, cli), body)
            if path.is_file() and path.read_text() == text:
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
            print(f"생성: {path}")


if __name__ == "__main__":
    main()
