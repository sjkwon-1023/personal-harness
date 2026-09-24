#!/usr/bin/env python3
import argparse
import contextlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
import uuid


MODELS = json.loads((Path(__file__).resolve().parents[1] / "models.json").read_text())
CLIS = ("claude", "codex", "opencode", "agy")
EFFORTS = {"claude": ("low", "medium", "high", "xhigh", "max"), "agy": ("low", "medium", "high")}
TERMINAL = {"reported", "failed", "closed"}
ROLE_FILES = {"worker": "implementer.md", "plan": "planner.md", "research": "researcher.md",
              "plan-review": "reviewer.md", "review": "reviewer.md"}


def model_selection(model, cli=None):
    """(cli, 모델 ID, models.json에 정한 effort 또는 None)을 돌려준다."""
    tier_cli, _, tier = model.partition(":")
    if tier and tier_cli in CLIS:
        if tier not in MODELS.get(tier_cli, {}):
            raise ValueError(f"models.json에 {tier_cli}의 {tier} 등급이 없습니다")
        if cli and cli != tier_cli:
            raise ValueError("등급 지정의 CLI와 --cli가 다릅니다")
        entry = MODELS[tier_cli][tier]
        return tier_cli, entry["model"], entry.get("effort")
    if cli not in CLIS or not model or model.startswith("-") or any(c.isspace() for c in model):
        raise ValueError("--model에는 <cli>:<등급> 또는 --cli와 함께 공백 없는 정확한 모델 ID가 필요합니다")
    entry = next((e for e in MODELS.get(cli, {}).values() if e["model"] == model), {})
    return cli, model, entry.get("effort")


def role_text(request):
    role_file = request.get("role_file")
    if role_file:
        return Path(role_file).read_text()
    return (Path(__file__).resolve().parents[1] / "roles" / ROLE_FILES[request["role"]]).read_text()


def binary(name):
    found = shutil.which(name)
    if found:
        return found
    path = Path.home() / (".opencode/bin/opencode" if name == "opencode" else f".local/bin/{name}")
    if path.is_file() and os.access(path, os.X_OK):
        return str(path)
    raise ValueError(f"실행 파일이 없습니다: {name}")


def tab(value):
    value = str(value).removeprefix("#")
    if not re.fullmatch(r"[1-9][0-9]*", value):
        raise ValueError("pane은 mast ls의 숫자 ID로 지정해야 합니다")
    return value


def current_tab():
    if not os.environ.get("MAST"):
        raise ValueError("mast pane 안에서 실행해야 합니다")
    return tab(os.environ.get("MAST_TAB", ""))


def tabs():
    result = subprocess.run([binary("mast"), "ls"], capture_output=True, text=True, check=True)
    lines = result.stdout.splitlines()
    if not lines or "COMMAND" not in lines[0]:
        raise ValueError("mast ls 응답 형식을 확인할 수 없습니다")
    column = lines[0].index("COMMAND")
    return {match[1]: line[column:].strip() for line in lines[1:]
            if (match := re.match(r"^#([0-9]+)\s", line))}


def send_text(target, text):
    if any(c in text for c in "\r\n") or len(text.encode()) > 32768:
        raise ValueError("mast에는 32 KiB 이하의 한 줄만 전송할 수 있습니다")
    subprocess.run([binary("mast"), "send", f"#{tab(target)}", text], check=True)


def write_json(path, data):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def replace_text(path, text):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text)
    shutil.copymode(path, temporary)
    temporary.replace(path)


@contextlib.contextmanager
def codex_trust(path):
    # Codex는 처음 여는 폴더마다 trust를 묻고, 상위 폴더 trust나 -c projects 오버라이드로는 이를 건너뛰지 않는다.
    config = (Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "config.toml").resolve(strict=True)
    block = ["\n", f"[projects.{json.dumps(path, ensure_ascii=False)}]\n", "trust_level = \"trusted\"\n"]
    replace_text(config, config.read_text().rstrip("\n") + "\n" + "".join(block))
    try:
        yield
    finally:
        lines = config.read_text().splitlines(keepends=True)
        for start in range(len(lines) - 2):
            if lines[start:start + 3] == block:
                replace_text(config, "".join(lines[:start] + lines[start + 3:]))
                break


def load(path):
    path = path.resolve(strict=True)
    request = json.loads(path.read_text())
    if Path(request["output_dir"]).resolve() != path.parent:
        raise ValueError("요청 경로와 output_dir가 일치하지 않습니다")
    return request, json.loads((path.parent / "status.json").read_text())


def save(request, status):
    write_json(Path(request["output_dir"]) / "status.json", status)


def require_owner(request, receiver=False):
    expected = request["target_tab"] if receiver else request["reply_tab"]
    if current_tab() != expected:
        raise ValueError(f"이 동작은 #{expected} pane에서 수행해야 합니다")


def notify(request, status):
    status["notification"] = "attempted"
    save(request, status)
    send_text(request["reply_tab"], f"[HARNESS-DONE] id={request['id']} request={shlex.quote(str(Path(request['output_dir']) / 'request.json'))} 결과 파일과 실제 변경을 확인하세요.")


def prepare(args):
    role, model = args.role, args.model
    cli, model_id, model_effort = model_selection(model, getattr(args, "cli", None))
    effort = getattr(args, "effort", None) or model_effort
    if effort and cli in EFFORTS and effort not in EFFORTS[cli]:
        raise ValueError(f"{cli} helper effort는 {', '.join(EFFORTS[cli])}만 지원합니다")
    target, reply = tab(args.target_tab), current_tab()
    if target == reply:
        raise ValueError("자신의 pane에는 위임할 수 없습니다")
    workdir, brief = args.workdir.resolve(strict=True), args.brief.resolve(strict=True)
    if not workdir.is_dir() or not brief.is_file() or not brief.read_text().strip():
        raise ValueError("작업 디렉터리와 비어 있지 않은 브리프 파일이 필요합니다")
    output = args.output_dir.resolve()
    if role != "worker" and (output == workdir or workdir in output.parents):
        raise ValueError("계획·검수 결과 디렉터리는 프로젝트 밖이어야 합니다")
    role_source = Path(__file__).resolve().parents[1] / "roles" / ROLE_FILES[role]
    role_prompt = role_source.read_text()
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    request = {"id": uuid.uuid4().hex, "role": role, "model": model, "model_id": model_id,
               "cli": cli, "effort": effort, "role_file": str(output / "role.md"),
               "target_tab": target, "reply_tab": reply, "workdir": str(workdir), "output_dir": str(output),
               "protocol": str(Path(__file__).resolve().with_name("PROTOCOL.md")),
               "helper": str(Path(__file__).resolve()), "created_at": time.time()}
    (output / "brief.md").write_text(brief.read_text())
    (output / "role.md").write_text(role_prompt)
    write_json(output / "request.json", request)
    save(request, {"id": request["id"], "status": "prepared", "acceptance": "pending"})
    print(output / "request.json")


def send(request, status):
    require_owner(request)
    if status["status"] != "prepared":
        raise ValueError("이미 전송한 요청은 자동 재전송하지 않습니다. 수신 상태를 확인하세요")
    if tabs().get(request["target_tab"]) != "-":
        raise ValueError("대상은 확인된 전용 shell pane이어야 합니다. 다른 작업 중인 pane을 덮어쓰지 않습니다")
    command = shlex.join([sys.executable, request["helper"], "launch", "--request", str(Path(request["output_dir"]) / "request.json")])
    status.update(status="sent", sent_at=time.time())
    save(request, status)
    send_text(request["target_tab"], command)
    print("전송을 시도했습니다. mast의 exit 0은 수신 확인이 아닙니다.")


def launch_command(request):
    prompt = (role_text(request) + "\n[HARNESS] 프로토콜" +
              f" {request['protocol']} 을 먼저 읽고 요청 {Path(request['output_dir']) / 'request.json'} 을 수행하세요. "
              "ack 후 브리프를 실행하고 결과 저장·finish 회신으로 끝내세요. 다른 AI를 호출하지 마세요.")
    environment = os.environ.copy()
    cli = request["cli"]
    worker = request["role"] == "worker"
    cwd = request["workdir"] if worker else request["output_dir"]
    effort = request.get("effort")
    if cli == "opencode":
        config = json.loads(environment.get("OPENCODE_CONFIG_CONTENT", "{}"))
        if not isinstance(config, dict) or not isinstance(config.get("agent", {}), dict):
            raise ValueError("OPENCODE_CONFIG_CONTENT와 agent는 객체여야 합니다")
        template = json.loads(Path(__file__).with_name("worker-config.json").read_text())
        agent = template["agent"]["chunk-worker"]
        agent["model"] = request["model_id"]
        if effort:
            # OpenCode는 reasoning effort를 모델별 variant 이름(예: low/high/max)으로 받는다.
            agent["variant"] = effort
        agent["prompt"] = role_text(request)
        agent["permission"]["external_directory"] = {
            "*": "ask", request["output_dir"] + "/*": "allow",
            str(Path(request["protocol"]).parent) + "/*": "allow"}
        if not worker:
            agent["permission"]["edit"] = {"*": "deny", request["output_dir"] + "/*": "allow"}
            agent["permission"]["bash"]["*"] = "ask"
        config["model"] = config["small_model"] = request["model_id"]
        config.setdefault("agent", {})["chunk-worker"] = agent
        environment["OPENCODE_CONFIG_CONTENT"] = json.dumps(config, ensure_ascii=False)
        command = [binary("opencode"), cwd, "--model", request["model_id"],
                   "--agent", "chunk-worker", "--prompt", prompt]
        if worker:
            command.append("--auto")
    elif cli == "codex":
        command = [binary("codex"), "--model", request["model_id"], "--cd", cwd,
                   "--sandbox", "workspace-write", "-c", "features.multi_agent=false",
                   "-c", "notify=[]"]
        if worker:
            command.extend(["--add-dir", request["output_dir"]])
        if effort:
            command.extend(["-c", "model_reasoning_effort=" + json.dumps(effort)])
        command.append(prompt)
    elif cli == "claude":
        command = [binary("claude"), "--model", request["model_id"],
                   "--tools", "Bash,Read,Write,Edit,Grep,Glob,WebSearch,WebFetch"]
        if not worker:
            command.extend(["--add-dir", request["workdir"]])
        else:
            command.extend(["--add-dir", request["output_dir"]])
        if effort:
            command.extend(["--effort", effort])
        command.extend(["--", prompt])
    elif cli == "agy":
        command = [binary("agy"), "--model", request["model_id"],
                   "--add-dir", request["output_dir"] if worker else request["workdir"]]
        if effort:
            command.extend(["--effort", effort])
        command.extend(["--prompt-interactive", prompt])
    else:
        raise ValueError(f"지원하지 않는 CLI: {cli}")
    return command, environment


def launch(request, status):
    require_owner(request, receiver=True)
    if status["status"] != "sent":
        raise ValueError("sent 상태인 새 요청만 실행할 수 있습니다")
    try:
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise ValueError("화면에 보이는 대화형 pane에서만 실행할 수 있습니다")
        command, environment = launch_command(request)
        status.update(status="launched", launched_at=time.time(), command=command)
        save(request, status)
        cwd = request["workdir"] if request["role"] == "worker" else request["output_dir"]
        trust = codex_trust(cwd) if request["cli"] == "codex" and cwd == request["output_dir"] else contextlib.nullcontext()
        with trust, subprocess.Popen(command, cwd=cwd, env=environment) as process:
            status.update(process_pid=process.pid, launcher_pid=os.getpid())
            status["process_start_ticks"] = Path(f"/proc/{process.pid}/stat").read_text().rpartition(")")[2].split()[19]
            save(request, status)
            previous = signal.signal(signal.SIGINT, signal.SIG_IGN)
            try:
                code = process.wait()
            finally:
                signal.signal(signal.SIGINT, previous)
            if code:
                raise subprocess.CalledProcessError(code, command)
        _, status = load(Path(request["output_dir"]) / "request.json")
        if status["status"] not in TERMINAL:
            raise ValueError("결과 보고 없이 대화형 세션이 종료됐습니다")
        status["session_closed_at"] = time.time()
        save(request, status)
    except (OSError, ValueError, subprocess.CalledProcessError, KeyboardInterrupt) as error:
        _, status = load(Path(request["output_dir"]) / "request.json")
        if status["status"] not in TERMINAL:
            status.update(status="failed", error=str(error) or type(error).__name__)
            save(request, status)
            notify(request, status)
        raise


def ack(request, status):
    require_owner(request, receiver=True)
    if status["status"] != "launched":
        raise ValueError("새로 시작한 세션의 요청만 수신 확인할 수 있습니다")
    status.update(status="received", received_at=time.time())
    save(request, status)


def finish(request, status, outcome):
    require_owner(request, receiver=True)
    if status["status"] != "received":
        raise ValueError("수신된 요청만 한 번 보고할 수 있습니다")
    result = Path(request["output_dir"]) / "result.md"
    if not result.is_file() or not result.read_text().strip():
        raise ValueError("비어 있지 않은 result.md가 필요합니다")
    status.update(status="reported", outcome=outcome, reported_at=time.time())
    save(request, status)
    notify(request, status)


def launcher_runs(request, status):
    # mast ls는 COMMAND 열을 40자로 잘라 보여 주므로 요청 경로는 launcher의 /proc 정보로 확인한다.
    proc = Path(f"/proc/{status.get('launcher_pid', 0)}")
    try:
        argv = (proc / "cmdline").read_bytes().split(b"\0")
        environ = (proc / "environ").read_bytes().split(b"\0")
    except OSError:
        return False
    request_path = str(Path(request["output_dir"]) / "request.json").encode()
    return (b"launch" in argv and request_path in argv
            and f"MAST_TAB={request['target_tab']}".encode() in environ)


def close(request, status):
    require_owner(request)
    if status["status"] not in TERMINAL:
        raise ValueError("보고가 끝나지 않은 세션을 자동 종료할 수 없습니다")
    command = tabs().get(request["target_tab"])
    if command == "-":
        return
    if status.get("session_closed_at") or status.get("close_requested_at"):
        raise ValueError("이미 종료했거나 종료를 요청한 세션입니다")
    if not command or not launcher_runs(request, status):
        raise ValueError("대상 pane의 실행 명령이 이 요청과 다릅니다")
    stat = Path(f"/proc/{status['process_pid']}/stat").read_text().rpartition(")")[2].split()
    if stat[19] != status["process_start_ticks"] or stat[0] == "Z":
        raise ValueError("원래 실행한 프로세스가 아닙니다")
    status["close_requested_at"] = time.time()
    save(request, status)
    send_text(request["target_tab"], "/exit")


def main():
    parser = argparse.ArgumentParser(description="mast 전용 pane에 새 대화형 AI 세션을 전송합니다")
    commands = parser.add_subparsers(dest="action", required=True)
    p = commands.add_parser("prepare")
    p.add_argument("--role", choices=["plan", "plan-review", "research", "review", "worker"], required=True)
    p.add_argument("--model", required=True, help="<cli>:<등급>(models.json) 또는 --cli와 함께 쓰는 정확한 모델 ID")
    p.add_argument("--cli", choices=CLIS)
    p.add_argument("--effort", choices=["minimal", "low", "medium", "high", "xhigh", "max"])
    p.add_argument("--target-tab", required=True)
    for name in ["workdir", "brief", "output-dir"]:
        p.add_argument("--" + name, type=Path, required=True)
    for name in ["send", "launch", "ack", "finish", "close"]:
        p = commands.add_parser(name)
        p.add_argument("--request", type=Path, required=True)
        if name == "finish":
            p.add_argument("--outcome", choices=["completed", "blocked"], required=True)
    args = parser.parse_args()
    try:
        if args.action == "prepare":
            prepare(args)
        else:
            request, status = load(args.request)
            if args.action == "finish":
                finish(request, status, args.outcome)
            else:
                globals()[args.action](request, status)
    except (ValueError, OSError, subprocess.CalledProcessError, KeyboardInterrupt) as error:
        print(str(error) or type(error).__name__, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
