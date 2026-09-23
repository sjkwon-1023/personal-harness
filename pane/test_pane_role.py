import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location("pane_role", Path(__file__).with_name("pane-role.py"))
pane = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pane)


class PaneTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.brief = self.root / "brief ' $(literal).md"
        self.brief.write_text("R1: implement only this chunk")
        self.args = SimpleNamespace(role="worker", model="opencode:light", target_tab="38",
                                    workdir=self.root, brief=self.brief, output_dir=self.root / "output")
        self.env = patch.dict(os.environ, {"MAST": "1", "MAST_TAB": "6"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def prepare(self):
        pane.prepare(self.args)
        self.path = self.args.output_dir / "request.json"
        return pane.load(self.path)

    def test_send_to_busy_pane_is_rejected_without_delivery(self):
        request, status = self.prepare()
        with patch.object(pane, "tabs", return_value={"38": "opencode"}), patch.object(pane, "send_text") as send:
            with self.assertRaises(ValueError):
                pane.send(request, status)
            send.assert_not_called()
        self.assertEqual(pane.load(self.path)[1]["status"], "prepared")

    def test_send_is_not_ack_and_cannot_be_repeated(self):
        request, status = self.prepare()
        with patch.object(pane, "tabs", return_value={"38": "-"}), patch.object(pane, "send_text") as send:
            pane.send(request, status)
            self.assertEqual(status["status"], "sent")
            command = send.call_args.args[1]
            self.assertEqual(pane.shlex.split(command)[-1], str(self.path))
            with self.assertRaises(ValueError):
                pane.send(request, status)
            self.assertEqual(send.call_count, 1)

    def test_wrong_receiver_and_empty_result_cannot_complete(self):
        request, status = self.prepare()
        status["status"] = "launched"
        with self.assertRaises(ValueError):
            pane.ack(request, status)
        with patch.dict(os.environ, {"MAST_TAB": "38"}):
            pane.ack(request, status)
            with self.assertRaises(ValueError):
                pane.finish(request, status, "completed")
        self.assertEqual(status["status"], "received")

    def test_report_is_persisted_before_one_notification(self):
        request, status = self.prepare()
        status["status"] = "received"
        (self.args.output_dir / "result.md").write_text("blocked: tests failed")
        with patch.dict(os.environ, {"MAST_TAB": "38"}), patch.object(pane, "send_text") as send:
            pane.finish(request, status, "blocked")
            self.assertEqual(pane.load(self.path)[1]["status"], "reported")
            self.assertEqual(status["acceptance"], "pending")
            self.assertIn(request["id"], send.call_args.args[1])
            with self.assertRaises(ValueError):
                pane.finish(request, status, "blocked")
            self.assertEqual(send.call_count, 1)

    def test_interactive_commands_and_local_worker_config(self):
        request, _ = self.prepare()
        with patch.object(pane, "binary", side_effect=lambda name: name):
            command, environment = pane.launch_command(request)
            self.assertEqual(command[0], "opencode")
            self.assertIn("--auto", command)
            self.assertNotIn("run", command)
            self.assertIn("--prompt", command)
            self.assertNotIn("--session", command)
            config = json.loads(environment["OPENCODE_CONFIG_CONTENT"])
            self.assertEqual(config["model"], pane.MODELS["opencode"]["light"]["model"])
            self.assertEqual(config["agent"]["chunk-worker"]["permission"]["task"], "deny")
            request.update(role="review", cli="codex", model="codex:standard", model_id=pane.MODELS["codex"]["standard"]["model"])
            command, _ = pane.launch_command(request)
            self.assertNotIn("exec", command)
            self.assertNotIn("--auto", command)
            self.assertEqual(command[command.index("--cd") + 1], request["output_dir"])

    def test_nonterminal_launch_fails_without_model_start(self):
        request, status = self.prepare()
        status["status"] = "sent"
        pane.save(request, status)
        with patch.dict(os.environ, {"MAST_TAB": "38"}), patch.object(pane.sys.stdin, "isatty", return_value=False), patch.object(pane, "notify"), patch.object(pane.subprocess, "Popen") as start:
            with self.assertRaises(ValueError):
                pane.launch(request, status)
            start.assert_not_called()
        self.assertEqual(pane.load(self.path)[1]["status"], "failed")

    def test_close_cannot_interrupt_unfinished_or_replaced_session(self):
        request, status = self.prepare()
        with self.assertRaises(ValueError):
            pane.close(request, status)
        status["status"] = "reported"
        with patch.object(pane, "tabs", return_value={"38": "opencode other-project"}), patch.object(pane, "send_text") as send:
            with self.assertRaises(ValueError):
                pane.close(request, status)
            send.assert_not_called()

    def test_close_identifies_session_by_launcher_despite_truncated_pane_command(self):
        request, status = self.prepare()
        status["status"] = "reported"
        for tab, accepted in (("38", True), ("39", False)):
            launcher = subprocess.Popen(
                [sys.executable, "-c", "import time; time.sleep(30)", "launch", "--request", str(self.path)],
                env=dict(os.environ, MAST_TAB=tab))
            self.addCleanup(launcher.wait)
            self.addCleanup(launcher.kill)
            ticks = Path(f"/proc/{launcher.pid}/stat").read_text().rpartition(")")[2].split()[19]
            status.update(launcher_pid=launcher.pid, process_pid=launcher.pid, process_start_ticks=ticks)
            status.pop("close_requested_at", None)
            with patch.object(pane, "tabs", return_value={"38": "python3 /home/user/.config/coding-harn…"}), \
                    patch.object(pane, "send_text") as send:
                if accepted:
                    pane.close(request, status)
                    send.assert_called_once_with("38", "/exit")
                else:
                    with self.assertRaises(ValueError):
                        pane.close(request, status)
                    send.assert_not_called()

    def test_self_target_and_wrong_model_are_rejected(self):
        self.args.target_tab = "6"
        with self.assertRaises(ValueError):
            pane.prepare(self.args)
        self.args.target_tab = "38"
        self.args.model = "unknown-model"
        with self.assertRaises(ValueError):
            pane.prepare(self.args)

    def test_multiline_send_is_rejected(self):
        with self.assertRaises(ValueError):
            pane.send_text("38", "one\ntwo")

    def test_all_clis_support_each_role_without_headless_or_resume(self):
        project = self.root / "project"
        project.mkdir()
        for cli in pane.CLIS:
            for role in pane.ROLE_FILES:
                with self.subTest(cli=cli, role=role):
                    self.args.cli, self.args.role = cli, role
                    self.args.model = "provider/custom-model" if cli == "opencode" else "custom-model"
                    self.args.workdir = project
                    self.args.output_dir = self.root / (cli + "-" + role)
                    request, _ = self.prepare()
                    with patch.object(pane, "binary", side_effect=lambda name: name):
                        command, _ = pane.launch_command(request)
                    self.assertEqual(command[0], cli)
                    self.assertEqual(command[command.index("--model") + 1], self.args.model)
                    for option in ("exec", "run", "--print", "-p", "--resume", "--continue", "--session"):
                        self.assertNotIn(option, command)
                    self.assertTrue(any(Path(request["role_file"]).read_text() in arg for arg in command))
                    if cli == "codex":
                        cwd = project if role == "worker" else self.args.output_dir
                        self.assertEqual(command[command.index("--cd") + 1], str(cwd))
                        if role != "worker":
                            self.assertNotIn("--add-dir", command)
                    if cli == "opencode":
                        self.assertEqual("--auto" in command, role == "worker")
                    if cli == "agy":
                        self.assertIn("--prompt-interactive", command)
                    if cli == "claude":
                        self.assertNotIn("Agent", command[command.index("--tools") + 1].split(","))

    def test_only_research_role_gets_web_search(self):
        project = self.root / "project"
        project.mkdir()
        for cli in ("codex", "claude"):
            for role in ("research", "review"):
                with self.subTest(cli=cli, role=role):
                    self.args.cli, self.args.role, self.args.model = cli, role, "custom-model"
                    self.args.workdir, self.args.output_dir = project, self.root / (cli + "-" + role)
                    request, _ = self.prepare()
                    with patch.object(pane, "binary", side_effect=lambda name: name):
                        command, _ = pane.launch_command(request)
                    web = "--search" in command if cli == "codex" else "WebSearch" in command[command.index("--tools") + 1]
                    self.assertEqual(web, role == "research")

    def test_role_snapshot_survives_source_changes(self):
        request, _ = self.prepare()
        text = Path(request["role_file"]).read_text()
        self.assertEqual(pane.role_text(request), text)
        Path(request["role_file"]).write_text("saved role for this request")
        self.assertEqual(pane.role_text(request), "saved role for this request")

    def test_alias_cli_mismatch_and_unknown_cli_fail_before_creating_request(self):
        self.args.cli = "claude"
        with self.assertRaises(ValueError):
            pane.prepare(self.args)
        self.assertFalse(self.args.output_dir.exists())
        with self.assertRaises(ValueError):
            pane.model_selection("custom-model", "missing-cli")

    def test_tier_resolves_from_models_json_and_unknown_tier_fails(self):
        top = pane.MODELS["codex"]["top"]
        self.assertEqual(pane.model_selection("codex:top"), ("codex", top["model"], top.get("effort")))
        for spec in ("codex:huge", "agy:top"):
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                pane.model_selection(spec)

    def test_readonly_output_cannot_be_inside_project(self):
        self.args.role = "review"
        with self.assertRaises(ValueError):
            pane.prepare(self.args)
        self.assertFalse(self.args.output_dir.exists())

    def test_request_without_role_snapshot_reads_role_source(self):
        request, _ = self.prepare()
        request.pop("role_file")
        with patch.object(pane, "binary", side_effect=lambda name: name):
            command, _ = pane.launch_command(request)
            self.assertEqual(command[0], "opencode")

    def test_effort_is_passed_per_cli_or_explicitly_rejected(self):
        self.args.effort = "max"
        request, _ = self.prepare()
        with patch.object(pane, "binary", side_effect=lambda name: name):
            _, environment = pane.launch_command(request)
        agent = json.loads(environment["OPENCODE_CONFIG_CONTENT"])["agent"]["chunk-worker"]
        self.assertEqual(agent["variant"], "max")
        self.args.model, self.args.cli, self.args.output_dir = "custom-model", "agy", self.root / "output-agy"
        with self.assertRaises(ValueError):
            pane.prepare(self.args)
        self.assertFalse(self.args.output_dir.exists())
        self.args.cli, self.args.effort, self.args.output_dir = "claude", "high", self.root / "output-claude"
        request, _ = self.prepare()
        with patch.object(pane, "binary", side_effect=lambda name: name):
            command, _ = pane.launch_command(request)
            self.assertEqual(command[command.index("--effort") + 1], "high")

    def test_models_json_effort_applies_unless_effort_is_given(self):
        self.args.model, self.args.role = "codex:light", "review"
        self.args.workdir = self.root / "project"
        self.args.workdir.mkdir()
        with patch.dict(pane.MODELS, {"codex": {"light": {"model": "gpt-test", "effort": "max"}}}):
            request, _ = self.prepare()
            self.assertEqual((request["model_id"], request["effort"]), ("gpt-test", "max"))
            self.args.effort, self.args.output_dir = "low", self.root / "output-explicit"
            request, _ = self.prepare()
            self.assertEqual(request["effort"], "low")

    def test_custom_opencode_model_and_readonly_permissions(self):
        self.args.cli, self.args.model, self.args.role = "opencode", "provider/specific", "review"
        self.args.workdir = self.root / "project"
        self.args.workdir.mkdir()
        request, _ = self.prepare()
        with patch.object(pane, "binary", side_effect=lambda name: name):
            command, env = pane.launch_command(request)
        config = json.loads(env["OPENCODE_CONFIG_CONTENT"])
        agent = config["agent"]["chunk-worker"]
        self.assertEqual(config["model"], "provider/specific")
        self.assertEqual(agent["model"], "provider/specific")
        self.assertEqual(agent["permission"]["edit"]["*"], "deny")
        self.assertEqual(agent["permission"]["edit"][request["output_dir"] + "/*"], "allow")
        self.assertEqual(agent["permission"]["bash"]["*"], "ask")
        self.assertNotIn("--auto", command)

    def test_missing_binary_does_not_fallback(self):
        request, _ = self.prepare()
        with patch.object(pane, "binary", side_effect=ValueError("missing")):
            with self.assertRaises(ValueError):
                pane.launch_command(request)


if __name__ == "__main__":
    unittest.main()
