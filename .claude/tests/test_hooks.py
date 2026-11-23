"""Exercise the Claude Code hooks with stub tools. Claude Code itself is not started."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


HOOKS = Path(__file__).resolve().parents[1] / "hooks"
FORMAT_HOOK = HOOKS / "swift_format_check.py"
GUARD_HOOK = HOOKS / "pr_reviewer_bash_guard.py"
APPROVAL_HOOK = HOOKS / "git_approval_guard.py"
SWIFT_SOURCE = "struct Example {}\n"


def write_executable(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


class SwiftFormatHookTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="claude-format-hook-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.repo = self.root / "repo"
        for directory in ("App/Features", "Tests/Unit", "scripts", ".claude"):
            (self.repo / directory).mkdir(parents=True)
        (self.repo / "project.yml").write_text('name: "AnyApp"\n', encoding="utf-8")
        self.swift_file = self.repo / "App/Features/Example.swift"
        self.swift_file.write_text(SWIFT_SOURCE, encoding="utf-8")
        self.calls = self.root / "calls.log"
        self.bin = self.root / "bin"
        write_executable(
            self.bin / "xcrun",
            """#!/bin/sh
printf '%s\\n' "$*" >> "$STUB_CALLS"
case "${STUB_MODE:-pass}" in
  findings) printf '%s\\n' "$4:1:1: warning: [Indentation] bad" >&2; exit 1 ;;
  missing) printf '%s\\n' "xcrun: error: unable to find utility \\"swift-format\\"" >&2; exit 72 ;;
  noisy) i=0; while [ "$i" -lt 2000 ]; do printf 'warning: finding %s\\n' "$i" >&2; i=$((i+1)); done; exit 1 ;;
esac
""",
        )

    def run_hook(self, stdin, mode="pass", path=None):
        env = {
            "PATH": str(self.bin) if path is None else path,
            "STUB_CALLS": str(self.calls),
            "STUB_MODE": mode,
        }
        return subprocess.run(
            [sys.executable, str(FORMAT_HOOK)],
            input=stdin,
            env=env,
            capture_output=True,
            timeout=20,
        )

    def payload(self, file_path, tool_name="Edit", cwd=None):
        return json.dumps({
            "hook_event_name": "PostToolUse",
            "tool_name": tool_name,
            "tool_input": {"file_path": str(file_path)},
            "cwd": str(cwd or self.repo),
        }).encode()

    def recorded(self):
        return self.calls.read_text(encoding="utf-8").splitlines() if self.calls.exists() else []

    def context(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertNotIn("decision", output)
        specific = output["hookSpecificOutput"]
        self.assertEqual(specific["hookEventName"], "PostToolUse")
        return specific["additionalContext"]

    def assert_skipped(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(self.recorded(), [])

    def test_valid_swift_file_is_linted_without_output(self):
        result = self.run_hook(self.payload(self.swift_file))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(self.recorded(), [f"swift-format lint --strict {self.swift_file}"])

    def test_write_tool_and_tests_directory_are_checked(self):
        test_file = self.repo / "Tests/Unit/ExampleTests.swift"
        test_file.write_text(SWIFT_SOURCE, encoding="utf-8")
        result = self.run_hook(self.payload(test_file, tool_name="Write"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.recorded(), [f"swift-format lint --strict {test_file}"])

    def test_relative_path_resolves_inside_project(self):
        result = self.run_hook(self.payload("App/Features/Example.swift"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.recorded(), [f"swift-format lint --strict {self.swift_file}"])

    def test_non_swift_file_is_skipped(self):
        readme = self.repo / "App/notes.md"
        readme.write_text("# Notes\n", encoding="utf-8")
        self.assert_skipped(self.run_hook(self.payload(readme)))

    def test_missing_file_is_skipped(self):
        self.assert_skipped(self.run_hook(self.payload(self.repo / "App/Missing.swift")))

    def test_invalid_json_is_ignored(self):
        for stdin in (b"", b"{not json", b"\xff\xfe", b"[]", b"null", b'"text"', b"[" * 100000):
            with self.subTest(stdin=stdin[:16]):
                self.assert_skipped(self.run_hook(stdin))

    def test_invalid_file_paths_are_ignored(self):
        for file_path in (None, 7, "", "App/\u0000Example.swift", ["App/Example.swift"], "a" * 5000 + ".swift"):
            with self.subTest(file_path=str(file_path)[:24]):
                stdin = json.dumps({
                    "tool_name": "Edit",
                    "tool_input": {"file_path": file_path},
                    "cwd": str(self.repo),
                }).encode()
                self.assert_skipped(self.run_hook(stdin))

    def test_malformed_payload_shapes_are_ignored(self):
        for payload in (
            {"tool_name": "Edit", "cwd": str(self.repo)},
            {"tool_name": "Edit", "tool_input": "App/Example.swift", "cwd": str(self.repo)},
            {"tool_name": "Edit", "tool_input": {"file_path": str(self.swift_file)}, "cwd": 42},
        ):
            with self.subTest(payload=payload):
                self.assert_skipped(self.run_hook(json.dumps(payload).encode()))

    def test_other_tools_are_skipped(self):
        self.assert_skipped(self.run_hook(self.payload(self.swift_file, tool_name="Read")))

    def test_file_outside_project_is_skipped(self):
        outside = self.root / "Outside.swift"
        outside.write_text(SWIFT_SOURCE, encoding="utf-8")
        for path in (outside, self.repo / "App/../../Outside.swift"):
            with self.subTest(path=path):
                self.assert_skipped(self.run_hook(self.payload(path)))

    def test_project_file_outside_source_directories_is_skipped(self):
        script = self.repo / "scripts/Tool.swift"
        script.write_text(SWIFT_SOURCE, encoding="utf-8")
        self.assert_skipped(self.run_hook(self.payload(script)))

    def test_symlink_escaping_project_is_skipped(self):
        outside = self.root / "Secret.swift"
        outside.write_text(SWIFT_SOURCE, encoding="utf-8")
        link = self.repo / "App/Link.swift"
        link.symlink_to(outside)
        directory_link = self.repo / "App/Linked"
        directory_link.symlink_to(self.root, target_is_directory=True)
        for path in (link, directory_link / "Secret.swift"):
            with self.subTest(path=path):
                self.assert_skipped(self.run_hook(self.payload(path)))

    def test_symlink_to_non_swift_file_is_skipped(self):
        target = self.repo / "App/data.txt"
        target.write_text("data\n", encoding="utf-8")
        link = self.repo / "App/Disguised.swift"
        link.symlink_to(target)
        self.assert_skipped(self.run_hook(self.payload(link)))

    def test_formatter_failure_reports_context_without_blocking(self):
        context = self.context(self.run_hook(self.payload(self.swift_file), mode="findings"))
        self.assertIn("[Indentation] bad", context)
        self.assertIn("自動修正", context)

    def test_long_findings_are_truncated(self):
        context = self.context(self.run_hook(self.payload(self.swift_file), mode="noisy"))
        self.assertLess(len(context), 2600)
        self.assertIn("省略", context)

    def test_missing_formatter_is_reported(self):
        for mode, path in (("pass", str(self.root / "empty-bin")), ("missing", None)):
            with self.subTest(mode=mode):
                context = self.context(self.run_hook(self.payload(self.swift_file), mode=mode, path=path))
                self.assertIn("swift-format", context)
                self.assertIn("スキップ", context)

    def test_formatter_timeout_is_reported_once(self):
        spec = importlib.util.spec_from_file_location("swift_format_check_under_test", FORMAT_HOOK)
        hook = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hook)
        expired = subprocess.TimeoutExpired(cmd="xcrun", timeout=hook.FORMAT_TIMEOUT_SECONDS)
        with patch.object(hook.shutil, "which", return_value="/stub/xcrun"):
            with patch.object(hook.subprocess, "run", side_effect=expired) as run:
                message = hook.lint(self.swift_file, self.repo)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.kwargs["timeout"], hook.FORMAT_TIMEOUT_SECONDS)
        self.assertIn("タイムアウト", message)

    def test_paths_with_spaces_and_shell_characters_are_passed_literally(self):
        directory = self.repo / "App/Feature $(touch pwned); `x` 'q'"
        directory.mkdir()
        swift_file = directory / "My View.swift"
        swift_file.write_text(SWIFT_SOURCE, encoding="utf-8")
        result = self.run_hook(self.payload(swift_file))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.recorded(), [f"swift-format lint --strict {swift_file}"])
        self.assertFalse((self.repo / "pwned").exists())
        self.assertFalse(Path("pwned").exists())

    def test_hook_does_not_modify_any_file(self):
        before = {
            path: path.read_bytes() for path in self.repo.rglob("*") if path.is_file()
        }
        self.run_hook(self.payload(self.swift_file), mode="findings")
        after = {
            path: path.read_bytes() for path in self.repo.rglob("*") if path.is_file()
        }
        self.assertEqual(after, before)


class GitApprovalGuardTests(unittest.TestCase):
    def run_guard(self, stdin):
        result = subprocess.run(
            [sys.executable, str(APPROVAL_HOOK)],
            input=stdin,
            env={"PATH": os.environ["PATH"]},
            capture_output=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def decision(self, command, tool_name="Bash"):
        stdout = self.run_guard(json.dumps({"tool_name": tool_name, "tool_input": {"command": command}}).encode())
        if not stdout:
            return None
        output = json.loads(stdout)["hookSpecificOutput"]
        self.assertEqual(output["hookEventName"], "PreToolUse")
        self.assertTrue(output["permissionDecisionReason"])
        return output["permissionDecision"]

    def test_requires_approval_for_direct_operations(self):
        for command in (
            "git commit -m x",
            "git push",
            "git push origin HEAD",
            "git merge main",
            "git rebase main",
            "git reset HEAD~1",
            "git cherry-pick abc",
            "git revert abc",
            "git tag v1",
            "git config alias.p push",
            "gh pr create --fill",
            "gh pr edit 1 --title x",
            "gh pr merge 1",
            "gh pr comment 1 --body x",
            "gh pr review 1 --approve",
            "gh pr close 1",
            "gh run rerun 1",
            "gh run cancel 1",
            "gh workflow run ci.yml",
            "gh release create v1",
            "gh repo delete octo/app",
        ):
            with self.subTest(command=command):
                self.assertEqual(self.decision(command), "ask")

    def test_requires_approval_through_wrappers_and_composition(self):
        for command in (
            "git -C . push",
            "git -C /tmp/repo commit -m x",
            "git --no-pager push",
            "git --git-dir=.git push",
            "git --git-dir .git --work-tree . push",
            "git -c core.sshCommand=evil fetch",
            "git -c alias.p=push p",
            "/usr/bin/git push",
            "env git push",
            "command git push",
            "FOO=bar git push",
            "xargs git push",
            "sh -c 'git push'",
            'bash -lc "git commit -m x"',
            "git status && git push",
            "git status; git push",
            "git status | git push",
            "git status\ngit push",
            "echo $(git push)",
            "echo `git push`",
            '"git" push',
            "g\\it push",
            "gi''t push",
            "GH_TOKEN=x gh pr comment 1 --body x",
            "/opt/homebrew/bin/gh pr create --fill",
            "sh -c 'gh pr merge 1'",
            "gh api repos/octo/app/pulls -f title=x",
            "gh api repos/octo/app/pulls --raw-field title=x",
            "gh api -X POST repos/octo/app/pulls",
            "gh api --method=PUT repos/octo/app/pulls/1/merge",
            "gh api repos/octo/app/pulls --input body.json",
            "gh api graphql -F query=x",
        ):
            with self.subTest(command=command):
                self.assertEqual(self.decision(command), "ask")

    def test_leaves_read_only_and_unrelated_commands_alone(self):
        for command in (
            "git status --short",
            "git diff --stat",
            "git log --oneline -- scripts/push.sh",
            "git log --grep=commit",
            "git show HEAD:README.md",
            "git branch --show-current",
            "gh pr view 1 --json title",
            "gh pr diff 1",
            "gh pr checks 1",
            "gh run view 1 --log-failed",
            "gh api 'repos/{owner}/{repo}/contents/App?ref=abc' -H 'Accept: application/vnd.github.raw'",
            "ls -la",
            "echo pushing commits",
            "legit push",
            "mise exec -- ./scripts/check.sh --tests unit 'platform=iOS Simulator,id=ABC'",
        ):
            with self.subTest(command=command):
                self.assertIsNone(self.decision(command))

    def test_other_tools_are_ignored(self):
        self.assertIsNone(self.decision("git push", tool_name="Read"))

    def test_undecidable_bash_input_requires_approval(self):
        for stdin in (
            b"",
            b"{not json",
            b"\xff\xfe",
            b"[]",
            b"[" * 100000,
            b'{"tool_name": "Bash"}',
            b'{"tool_name": "Bash", "tool_input": {"command": 7}}',
        ):
            with self.subTest(stdin=stdin[:32]):
                output = json.loads(self.run_guard(stdin))["hookSpecificOutput"]
                self.assertEqual(output["permissionDecision"], "ask")


class PullRequestReviewerGuardTests(unittest.TestCase):
    def decide(self, command, tool_name="Bash"):
        stdin = json.dumps({"tool_name": tool_name, "tool_input": {"command": command}}).encode()
        return self.decide_raw(stdin)

    def decide_raw(self, stdin):
        result = subprocess.run(
            [sys.executable, str(GUARD_HOOK)],
            input=stdin,
            env={"PATH": os.environ["PATH"]},
            capture_output=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)["hookSpecificOutput"]
        self.assertEqual(output["hookEventName"], "PreToolUse")
        self.assertTrue(output["permissionDecisionReason"])
        return output["permissionDecision"]

    def test_allows_read_only_commands(self):
        for command in (
            "gh pr view",
            "gh pr view 123 --json title,body,headRefOid,baseRefName,files",
            "gh pr view https://github.com/octo/app/pull/9 --comments",
            "gh pr view 12 --json files --jq '.files[] | .path'",
            "gh pr diff 123",
            "gh pr diff 123 --name-only",
            "gh pr checks 123 --json name,state,link",
            "gh run view 456 --log-failed",
            "gh run view 456 --json jobs --job 789",
            "gh run list --branch feature/x --limit 5 --json databaseId,headSha,status",
            "gh repo view --json nameWithOwner",
            "gh api 'repos/{owner}/{repo}/contents/App/My%20View.swift?ref=abc123' -H 'Accept: application/vnd.github.raw'",
            "gh api 'repos/{owner}/{repo}/pulls/12/files?per_page=100' --paginate --jq '.[].filename'",
            "git status --short",
            "git branch --show-current",
            "git rev-parse HEAD",
            "git rev-parse --abbrev-ref HEAD",
            "git diff --stat origin/main...HEAD",
            "git diff origin/main...HEAD -- App/Features/Home/HomeView.swift",
            "git log --oneline -n 5",
            "git log -5 --format=%H origin/main..HEAD",
            "git show HEAD~1:App/AppEntry.swift",
            "git show --stat HEAD",
            "git blame -L 10,20 App/AppEntry.swift",
            "git ls-files App",
            "git merge-base origin/main HEAD",
            "git grep -n 'HomeView' -- App Tests",
            "git grep -n -i -F 'destination' abc123 -- scripts",
            "git grep -l -E 'foo|bar' HEAD",
        ):
            with self.subTest(command=command):
                self.assertEqual(self.decide(command), "allow")

    def test_denies_write_and_remote_operations(self):
        for command in (
            "git commit -m x",
            "git push",
            "git push origin HEAD",
            "git add .",
            "git checkout main",
            "git switch main",
            "git reset --hard",
            "git fetch origin",
            "git stash",
            "git tag v1",
            "git branch -D main",
            "git branch new-branch",
            "git config user.name x",
            "git grep -O evil pattern",
            "gh pr comment 1 --body x",
            "gh pr review 1 --approve",
            "gh pr review 1 --request-changes --body x",
            "gh pr merge 1",
            "gh pr create --fill",
            "gh pr edit 1 --title x",
            "gh pr close 1",
            "gh pr checkout 1",
            "gh run rerun 1",
            "gh run cancel 1",
            "gh run download 1",
            "gh workflow run ci.yml",
            "gh repo delete octo/app",
            "gh auth token",
            "gh secret list",
        ):
            with self.subTest(command=command):
                self.assertEqual(self.decide(command), "deny")

    def test_denies_flags_that_write_execute_or_escape(self):
        for command in (
            "git diff --output=/tmp/x",
            "git diff --outp=/tmp/x",
            "git log --output /tmp/x",
            "git show --output=/tmp/x HEAD",
            "git diff --ext-diff",
            "git diff --no-index /etc/passwd /dev/null",
            "git diff /etc/passwd /dev/null",
            "git diff ../outside.txt App/AppEntry.swift",
            "git diff '~/secret' App/AppEntry.swift",
            "git blame --contents /etc/passwd App/AppEntry.swift",
            "git grep --open-files-in-pager=evil pattern",
            "git grep --no-index secret",
            "git grep --untracked secret",
            "git grep pattern -- /etc",
            "git -c core.pager=evil log",
            "git -C /tmp status",
            "git --git-dir=/tmp/x log",
            "gh pr view 1 --web",
            "gh pr view 1 -w",
            "gh pr diff 1 --web",
            "gh pr checks 1 --watch",
            "gh pr view 1 --repo other/repo",
            "gh pr view not-a-number",
            "gh pr view https://evil.example/octo/app/pull/1",
            "gh run view --web 1",
            "gh api repos/octo/app/pulls/1",
            "gh api graphql -f query=x",
            "gh api 'repos/{owner}/{repo}/pulls/1/reviews' -f event=APPROVE",
            "gh api 'repos/{owner}/{repo}/pulls/1/merge' -X PUT",
            "gh api 'repos/{owner}/{repo}/issues/1/comments' --input body.json",
            "gh api 'repos/{owner}/{repo}/contents/../../../user'",
            "gh api 'repos/{owner}/{repo}/contents/%2e%2e/%2e%2e/user'",
            "gh api 'repos/{owner}/{repo}/contents/a' -H 'X-HTTP-Method-Override: DELETE'",
        ):
            with self.subTest(command=command):
                self.assertEqual(self.decide(command), "deny")

    def test_denies_shell_composition(self):
        for command in (
            "git status; rm -rf .",
            "git status && git push",
            "git status || git push",
            "git log | tee out.txt",
            "git log > out.txt",
            "git log >> out.txt",
            "git diff < in.txt",
            "git log &",
            "git log $(git push)",
            "git log `git push`",
            'git log "$(git push)"',
            'git log "`git push`"',
            "git log ${IFS}",
            "git status\ngit push",
            "git status\rgit push",
            "git log \\\n--oneline",
            "(git status)",
            "{ git status; }",
            "GH_TOKEN=x gh pr view",
            "env git status",
            "/usr/bin/git status",
            "./git status",
            "sh -c 'git push'",
            "bash -c 'git status'",
            "python3 -c 'print(1)'",
            "xargs git push",
            "git log *",
            "git log 'unterminated",
            "",
            "   ",
        ):
            with self.subTest(command=command):
                self.assertEqual(self.decide(command), "deny")

    def test_fails_closed_on_malformed_input(self):
        for stdin in (
            b"",
            b"{not json",
            b"\xff\xfe",
            b"[]",
            b"null",
            b"[" * 100000,
            b'{"tool_name": "Bash"}',
            b'{"tool_name": "Bash", "tool_input": "git status"}',
            b'{"tool_name": "Bash", "tool_input": {"command": 7}}',
            b'{"tool_name": "Write", "tool_input": {"command": "git status"}}',
        ):
            with self.subTest(stdin=stdin[:32]):
                self.assertEqual(self.decide_raw(stdin), "deny")


if __name__ == "__main__":
    unittest.main()
