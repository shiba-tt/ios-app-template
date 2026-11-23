"""Validate the Claude Code harness files without starting Claude Code.

These tests must pass in both the template and an initialized app, so they do not rely on the
template-only scripts, on Git metadata, or on the app name.
"""

import ast
import json
from pathlib import Path
import re
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
CLAUDE = ROOT / ".claude"
SKILLS = {"implement-feature", "verify-ios", "prepare-pr", "review-pr"}
MANUAL_ONLY_SKILLS = {"prepare-pr", "review-pr"}
HOOK_SCRIPTS = {"swift_format_check.py", "pr_reviewer_bash_guard.py", "git_approval_guard.py"}
SKILL_FIELDS = {
    "name", "description", "when_to_use", "argument-hint", "arguments", "disable-model-invocation",
    "user-invocable", "allowed-tools", "disallowed-tools", "model", "effort", "context", "agent",
    "background", "hooks", "paths", "shell", "metadata", "license", "compatibility",
}
AGENT_FIELDS = {
    "name", "description", "tools", "disallowedTools", "model", "permissionMode", "maxTurns",
    "autoCompactWindow", "skills", "mcpServers", "hooks", "memory", "background", "omitClaudeMd",
    "effort", "isolation", "color", "initialPrompt", "experimental",
}
HARNESS_TEST_COMMAND = "python3 -m unittest discover -s .claude/tests -p 'test_*.py' -v"
TEMPLATE_ONLY_REFERENCES = ("scripts/bootstrap", "scripts/tests", "bootstrap.py", "bootstrap.sh")


def frontmatter(path):
    """Read top-level scalar fields. Nested values are checked against the raw text."""
    text = path.read_text(encoding="utf-8")
    match = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if match is None:
        raise AssertionError(f"{path} has no YAML frontmatter")
    fields = {}
    for line in match[1].splitlines():
        field = re.match(r"([A-Za-z_-]+):(?:\s+(.*))?$", line)
        if field:
            fields[field[1]] = (field[2] or "").strip().strip('"')
    return fields, text[match.end():]


def harness_documents():
    """Return the bundled documents. Apps may add their own skills, which these rules do not cover."""
    return [*(CLAUDE / "skills" / skill / "SKILL.md" for skill in sorted(SKILLS)), CLAUDE / "agents/pr-reviewer.md"]


def hook_scripts():
    return [CLAUDE / "hooks" / script for script in sorted(HOOK_SCRIPTS)]


class SkillTests(unittest.TestCase):
    def test_bundled_skills_exist(self):
        found = {path.parent.name for path in (CLAUDE / "skills").glob("*/SKILL.md")}
        self.assertLessEqual(SKILLS, found)

    def test_required_and_supported_frontmatter(self):
        for skill in SKILLS:
            with self.subTest(skill=skill):
                fields, body = frontmatter(CLAUDE / "skills" / skill / "SKILL.md")
                self.assertEqual(fields["name"], skill)
                self.assertTrue(fields["description"].startswith("Use when"))
                self.assertLessEqual(len(fields["description"]), 1024)
                self.assertTrue(fields["argument-hint"])
                self.assertLessEqual(set(fields), SKILL_FIELDS)
                self.assertIn("$ARGUMENTS", body)

    def test_invocation_policy(self):
        for skill in SKILLS:
            with self.subTest(skill=skill):
                fields, _ = frontmatter(CLAUDE / "skills" / skill / "SKILL.md")
                self.assertNotEqual(fields.get("user-invocable"), "false")
                expected = "true" if skill in MANUAL_ONLY_SKILLS else None
                self.assertEqual(fields.get("disable-model-invocation"), expected)

    def test_skills_do_not_widen_permissions_or_register_hooks(self):
        for skill in SKILLS:
            with self.subTest(skill=skill):
                fields, _ = frontmatter(CLAUDE / "skills" / skill / "SKILL.md")
                self.assertNotIn("allowed-tools", fields)
                self.assertNotIn("hooks", fields)

    def test_review_skill_forks_into_reviewer(self):
        fields, _ = frontmatter(CLAUDE / "skills/review-pr/SKILL.md")
        self.assertEqual(fields["context"], "fork")
        self.assertEqual(fields["agent"], "pr-reviewer")
        self.assertEqual(fields["background"], "false")

    def test_skill_references(self):
        implement = (CLAUDE / "skills/implement-feature/SKILL.md").read_text(encoding="utf-8")
        prepare = (CLAUDE / "skills/prepare-pr/SKILL.md").read_text(encoding="utf-8")
        verify = (CLAUDE / "skills/verify-ios/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("`verify-ios`", implement)
        self.assertIn("`verify-ios`", prepare)
        self.assertIn("`review-pr`", prepare)
        self.assertIn("./scripts/check.sh --tests unit", verify)
        self.assertIn("./scripts/select_simulator.py --runtime", verify)
        self.assertIn("IOS_SIMULATOR_RUNTIME", verify)

    def test_prepare_pr_runs_each_git_operation_separately(self):
        prepare = (CLAUDE / "skills/prepare-pr/SKILL.md").read_text(encoding="utf-8")
        section = prepare.split("### 承認後の実行\n", 1)[1].split("\n## ", 1)[0]
        positions = [section.index(f"`{command}") for command in ("git add -- ", "git commit ", "git push ", "gh pr create ")]
        self.assertEqual(positions, sorted(positions))
        for separator in ("`&&`", "`;`", "`|`"):
            self.assertIn(separator, section)
        self.assertIn("commit と push を別々のコマンドで実行", prepare.split("## 5. CI 失敗時", 1)[1])

    def test_verification_skill_reports_every_check(self):
        verify = (CLAUDE / "skills/verify-ios/SKILL.md").read_text(encoding="utf-8")
        for check in ("swift-format", "SwiftLint", "XcodeGen", "Build", "Unit Test", "UI Test"):
            self.assertIn(f"| {check} | PASS / FAIL / SKIP |", verify)


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.path = CLAUDE / "agents/pr-reviewer.md"
        self.fields, self.body = frontmatter(self.path)
        self.raw = self.path.read_text(encoding="utf-8")

    def test_supported_frontmatter(self):
        self.assertEqual(self.fields["name"], "pr-reviewer")
        self.assertTrue(self.fields["description"])
        self.assertLessEqual(set(self.fields), AGENT_FIELDS)

    def test_has_only_read_tools(self):
        tools = {tool.strip() for tool in self.fields["tools"].split(",")}
        self.assertEqual(tools, {"Read", "Grep", "Glob", "Bash"})
        self.assertNotIn("mcpServers", self.fields)

    def test_permission_mode_does_not_bypass(self):
        self.assertEqual(self.fields["permissionMode"], "dontAsk")

    def test_bash_guard_is_registered_and_fails_closed(self):
        header = self.raw[:self.raw.index(self.body)]
        self.assertRegex(header, r'PreToolUse:\n\s+- matcher: "Bash"')
        self.assertIn('"$CLAUDE_PROJECT_DIR/.claude/hooks/pr_reviewer_bash_guard.py"', header)
        self.assertIn("onFailure: block", header)
        self.assertTrue((CLAUDE / "hooks/pr_reviewer_bash_guard.py").is_file())

    def test_report_contract(self):
        for term in ("Critical", "High", "Medium", "Low", "対象", "発生条件", "根拠", "推奨修正", "指摘なし"):
            self.assertIn(term, self.body)


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.settings = json.loads((CLAUDE / "settings.json").read_text(encoding="utf-8"))
        self.permissions = self.settings["permissions"]

    def test_schema_and_permission_lists(self):
        self.assertEqual(self.settings["$schema"], "https://json.schemastore.org/claude-code-settings.json")
        for key in ("allow", "ask", "deny"):
            rules = self.permissions[key]
            self.assertTrue(rules)
            self.assertEqual(len(rules), len(set(rules)), key)
            for rule in rules:
                self.assertRegex(rule, r"^[A-Za-z][A-Za-z0-9_]*(\(.+\))?$")

    def test_bypass_is_not_enabled(self):
        self.assertNotIn("defaultMode", self.permissions)
        self.assertEqual(self.permissions["disableBypassPermissionsMode"], "disable")
        self.assertNotIn("bypassPermissions", json.dumps(self.settings))

    def test_allow_rules_are_narrow(self):
        allow = self.permissions["allow"]
        for rule in ("Bash", "Bash(*)", "Bash(git *)", "Bash(gh *)", "Bash(mise *)", "Bash(mise exec *)",
                     "Bash(python3 *)", "Bash(xcrun *)", "Edit", "Edit(**)", "Edit(/**)", "Read(**)"):
            self.assertNotIn(rule, allow)
        for rule in allow:
            if rule.startswith("Bash("):
                self.assertNotRegex(rule, r"^Bash\((git|sh|bash|zsh|env|eval|xargs|curl|wget)\b", rule)
        self.assertFalse([rule for rule in allow if rule.startswith("Read(")])

    def test_allow_covers_local_edit_and_validation(self):
        allow = self.permissions["allow"]
        for rule in (
            "Edit(/App/**)",
            "Edit(/Tests/**)",
            "Bash(./scripts/select_simulator.py --runtime *)",
            "Bash(mise exec -- ./scripts/check.sh --tests unit 'platform=iOS Simulator,id=*')",
            "Bash(mise exec -- ./scripts/check.sh 'platform=iOS Simulator,id=*')",
            "Bash(gh pr view *)",
            "Bash(gh pr checks *)",
            "Bash(gh run view *)",
        ):
            self.assertIn(rule, allow)

    def test_important_operations_require_approval(self):
        ask = self.permissions["ask"]
        for rule in (
            "Bash(git commit *)",
            "Bash(git push *)",
            "Bash(gh pr create *)",
            "Bash(gh pr edit *)",
            "Bash(gh pr comment *)",
            "Bash(gh pr review *)",
            "Bash(mise use *)",
            "Bash(swift package *)",
            "Edit(/project.yml)",
            "Edit(/mise.toml)",
            "Edit(/.claude/**)",
            "Edit(/.github/**)",
            "Edit(/scripts/**)",
        ):
            self.assertIn(rule, ask)

    def test_destructive_operations_and_secrets_are_denied(self):
        deny = self.permissions["deny"]
        for rule in (
            "Bash(git push --force*)",
            "Bash(git push -f*)",
            "Bash(git reset --hard*)",
            "Bash(git clean *)",
            "Bash(gh pr merge *)",
            "Bash(gh repo delete *)",
            "Bash(sudo *)",
            "Read(**/.env)",
            "Read(**/*.p12)",
            "Read(**/*.p8)",
            "Read(~/.ssh/**)",
            "Read(~/.config/gh/**)",
            "Edit(**/.env)",
        ):
            self.assertIn(rule, deny)

    def test_no_rule_is_shadowed_into_allow(self):
        self.assertFalse(set(self.permissions["allow"]) & set(self.permissions["ask"]))
        self.assertFalse(set(self.permissions["allow"]) & set(self.permissions["deny"]))

    def test_hook_registration_is_lightweight(self):
        hooks = self.settings["hooks"]
        for event, matcher, script in (
            ("PostToolUse", "Write|Edit", "swift_format_check.py"),
            ("PreToolUse", "Bash", "git_approval_guard.py"),
        ):
            with self.subTest(event=event):
                command = f'python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/{script}"'
                registered = [
                    (entry, handler)
                    for entry in hooks[event]
                    for handler in entry["hooks"]
                    if handler.get("command") == command
                ]
                self.assertEqual(len(registered), 1)
                entry, handler = registered[0]
                self.assertEqual(entry["matcher"], matcher)
                self.assertEqual(handler["type"], "command")
                self.assertLessEqual(handler["timeout"], 30)
                self.assertTrue((CLAUDE / "hooks" / script).is_file())


class HookScriptTests(unittest.TestCase):
    def test_scripts_parse_and_use_only_standard_library(self):
        for script in hook_scripts():
            with self.subTest(script=script.name):
                tree = ast.parse(script.read_text(encoding="utf-8"))
                imported = set()
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        imported.update(alias.name.split(".")[0] for alias in node.names)
                    elif isinstance(node, ast.ImportFrom):
                        imported.add((node.module or "").split(".")[0])
                self.assertLessEqual(imported, set(sys.stdlib_module_names))

    def test_format_hook_cannot_rewrite_or_start_builds(self):
        source = (CLAUDE / "hooks/swift_format_check.py").read_text(encoding="utf-8")
        for forbidden in ("--in-place", '"format"', "xcodebuild", "shell=True", "write_text", "open("):
            self.assertNotIn(forbidden, source)

    def test_guards_do_not_run_commands(self):
        for script in ("pr_reviewer_bash_guard.py", "git_approval_guard.py"):
            source = (CLAUDE / "hooks" / script).read_text(encoding="utf-8")
            for forbidden in ("subprocess", "os.system", "shell=True"):
                with self.subTest(script=script, forbidden=forbidden):
                    self.assertNotIn(forbidden, source)


class ReuseTests(unittest.TestCase):
    def test_referenced_files_exist(self):
        pattern = re.compile(r"(?<![\w/])((?:scripts|docs|\.claude|\.github)/[A-Za-z0-9_./-]*[A-Za-z0-9_/-])")
        for document in harness_documents():
            for reference in pattern.findall(document.read_text(encoding="utf-8")):
                with self.subTest(document=document.name, reference=reference):
                    self.assertTrue((ROOT / reference).exists(), reference)

    def test_harness_has_no_app_specific_values(self):
        for document in [*harness_documents(), CLAUDE / "settings.json", *hook_scripts()]:
            text = document.read_text(encoding="utf-8")
            with self.subTest(document=document.name):
                self.assertNotIn("StarterApp", text)
                self.assertNotIn("starterapp", text)
                self.assertNotRegex(text, r"(?<![\d.])\d{2}\.\d(?![\d.])", "version numbers belong in repo config")

    def test_harness_does_not_depend_on_template_only_files(self):
        documents = [
            *harness_documents(),
            CLAUDE / "settings.json",
            *hook_scripts(),
            ROOT / "docs/claude-harness.md",
        ]
        for document in documents:
            text = document.read_text(encoding="utf-8")
            for reference in TEMPLATE_ONLY_REFERENCES:
                with self.subTest(document=document.name, reference=reference):
                    self.assertNotIn(reference, text)

    def test_scripts_kept_after_initialization_exist(self):
        for script in ("scripts/check.sh", "scripts/select_simulator.py", "scripts/select_xcode.sh"):
            self.assertTrue((ROOT / script).is_file(), script)

    def test_project_guide_keeps_harness_after_replaced_intro(self):
        guide = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertEqual(guide.count("## 開発\n"), 1)
        self.assertGreater(guide.index("## Claude Code ハーネス\n"), guide.index("## 開発\n"))
        self.assertNotIn("bootstrap", guide)

    def test_readme_keeps_harness_after_replaced_intro(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertEqual(readme.count("## 開発環境\n"), 1)
        kept = readme.split("## 開発環境\n", 1)[1]
        self.assertIn("## Claude Code ハーネス\n", kept)
        self.assertNotIn("bootstrap", kept)

    def test_operations_guide_covers_every_command(self):
        guide = (ROOT / "docs/claude-harness.md").read_text(encoding="utf-8")
        for command in ("/implement-feature", "/verify-ios quick", "/verify-ios full", "/prepare-pr", "/review-pr 123"):
            self.assertIn(command, guide)


class ContinuousIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    def job(self, name):
        match = re.search(rf"^  {name}:\n(.*?)(?=^  [a-z-]+:\n|\Z)", self.workflow, re.M | re.S)
        self.assertIsNotNone(match, name)
        return match[1]

    def test_harness_tests_run_in_quality_job_without_template_condition(self):
        job = self.job("quality-and-security")
        step = re.search(r"- name: Run Claude Code harness tests\n(.*?)(?=\n\s+- name:|\Z)", job, re.S)
        self.assertIsNotNone(step)
        self.assertIn(HARNESS_TEST_COMMAND, step[1])
        self.assertNotIn("if:", step[1])

    def test_ci_does_not_start_claude_or_use_api_keys(self):
        self.assertNotIn("ANTHROPIC", self.workflow)
        self.assertNotRegex(self.workflow, r"(?m)^\s*(?:run:\s*)?claude\s")
        self.assertNotIn("claude-code-action", self.workflow)
        self.assertNotIn("secrets.", self.workflow)

    def test_existing_job_names_are_kept(self):
        for job in ("quality-and-security", "ios-build-and-unit-tests", "ios-ui-tests"):
            self.assertIn(f"    name: {job}\n", self.workflow)


if __name__ == "__main__":
    unittest.main()
