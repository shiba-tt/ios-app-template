"""Exercise bootstrap against isolated template copies with a stub XcodeGen."""

import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


TEMPLATE = Path(__file__).resolve().parents[2]
APP_NAME = "BudgetMate"
BUNDLE_ID = "com.example.budgetmate"
DISPLAY_NAME = '家計簿 "Plus" & [共有]'
PROJECT_NAME = f"{APP_NAME}.xcodeproj"


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ios-bootstrap-test-")
        self.addCleanup(temporary.cleanup)
        # Match bootstrap's resolved ROOT; macOS temporary paths are under the /var symlink.
        self.temporary_path = Path(temporary.name).resolve()
        self.repo = self.temporary_path / "template"
        (self.repo / "scripts").mkdir(parents=True)
        for directory in ("App", "Tests", ".claude"):
            shutil.copytree(TEMPLATE / directory, self.repo / directory)
        for filename in ("project.yml", "README.md", "CLAUDE.md", "LICENSE",
                         "scripts/bootstrap.sh", "scripts/bootstrap.py", "scripts/check.sh"):
            shutil.copy2(TEMPLATE / filename, self.repo / filename)
        shutil.copytree(TEMPLATE / "scripts/tests", self.repo / "scripts/tests",
                        ignore=shutil.ignore_patterns("__pycache__"))

        bin_dir = self.temporary_path / "bin"
        bin_dir.mkdir()
        xcodegen = bin_dir / "xcodegen"
        xcodegen.write_text(
            """#!/usr/bin/env python3
import os
from pathlib import Path
import re
import sys

assert sys.argv[1:] == ["generate"]
assert Path.cwd().parent.name == ".bootstrap-in-progress"
assert not (Path.cwd().parents[1] / ".bootstrap-complete").exists()
name = re.search(r'^name: "([^"]+)"$', Path("project.yml").read_text(encoding="utf-8"), re.M)[1]
assert f"struct {name}Entry:" in Path("App/AppEntry.swift").read_text(encoding="utf-8")
assert Path("Tests/Unit").is_dir() and Path("Tests/UI").is_dir()
project = Path(name + ".xcodeproj")
project.mkdir()
mode = os.environ["BOOTSTRAP_TEST_XCODEGEN"]
if mode == "missing-output":
    sys.exit(0)
(project / "project.pbxproj").write_text("// XcodeGen stub\\n", encoding="utf-8")
if mode == "fail":
    sys.exit(17)
""",
            encoding="utf-8",
        )
        xcodegen.chmod(0o755)
        self.env = dict(os.environ, PATH=os.pathsep.join((str(bin_dir), os.environ["PATH"])))
        self.env["BOOTSTRAP_TEST_XCODEGEN"] = "success"
        self.before = self.snapshot()

    def snapshot(self):
        return {
            path.relative_to(self.repo): path.read_bytes() if path.is_file() else None
            for path in self.repo.rglob("*")
        }

    def options(self, **overrides):
        options = {
            "app-name": APP_NAME,
            "bundle-id": BUNDLE_ID,
            "platform": "iphone",
            "deployment-target": "26.0",
            **overrides,
        }
        return [part for key, value in options.items() for part in (f"--{key}", value)]

    def bootstrap(self, *args, mode="success"):
        return subprocess.run(
            [str(self.repo / "scripts/bootstrap.sh"), *args],
            cwd=self.temporary_path,
            env=dict(self.env, BOOTSTRAP_TEST_XCODEGEN=mode),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=20,
        )

    def read(self, filename):
        return (self.repo / filename).read_text(encoding="utf-8")

    def assert_success(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def assert_rejected(self, result, message):
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(message, result.stderr)

    def load_bootstrap(self):
        spec = importlib.util.spec_from_file_location("bootstrap_under_test", self.repo / "scripts/bootstrap.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_iphone_initialization_renames_app_and_updates_docs(self):
        result = self.bootstrap(*self.options())
        self.assert_success(result)
        self.assertIn("com.example is reserved for examples", result.stdout)

        project = self.read("project.yml")
        self.assertTrue(project.startswith(f'name: "{APP_NAME}"\n'))
        self.assertEqual(
            re.findall(r'^  "([^"]+)":$', project, re.M),
            [APP_NAME, f"{APP_NAME}Tests", f"{APP_NAME}UITests"],
        )
        for target_name in (f"{APP_NAME}Tests", f"{APP_NAME}UITests"):
            self.assertIn(f'        - "{target_name}"\n', project)
        self.assertEqual(project.count(f'      - target: "{APP_NAME}"\n'), 2)
        self.assertEqual(
            re.findall(r'PRODUCT_BUNDLE_IDENTIFIER: "([^"]+)"', project),
            [BUNDLE_ID, f"{BUNDLE_ID}.tests", f"{BUNDLE_ID}.uitests"],
        )
        self.assertIn(f'INFOPLIST_KEY_CFBundleDisplayName: "{APP_NAME}"\n', project)
        self.assertIn('TARGETED_DEVICE_FAMILY: "1"\n', project)
        self.assertIn('iOS: "26.0"\n', project)
        self.assertIn('DEVELOPMENT_TEAM: ""\n', project)
        self.assertIn(f"struct {APP_NAME}Entry: App", self.read("App/AppEntry.swift"))

        readme = self.read("README.md")
        self.assertTrue(readme.startswith(f"# {APP_NAME}\n"))
        self.assertIn("## 開発環境\n", readme)
        for document in (readme, self.read("CLAUDE.md")):
            self.assertIn(APP_NAME, document)
            self.assertIn(BUNDLE_ID, document)
            self.assertIn("iOS 26.0", document)
            self.assertNotIn("com.example.starterapp", document)
            # The template-only scripts are removed, so the app docs must not point to them.
            self.assertNotIn("bootstrap", document)
        for removed in ("scripts/bootstrap.sh", "scripts/bootstrap.py", "scripts/tests"):
            self.assertFalse((self.repo / removed).exists(), removed)
        self.assertTrue((self.repo / "scripts/check.sh").is_file())
        self.assertNotIn("StarterApp", project)
        for path, content in self.before.items():
            if path.parts[:2] == (".claude", "rules") and content is not None:
                self.assertEqual((self.repo / path).read_bytes(), content)

        self.assertTrue((self.repo / PROJECT_NAME / "project.pbxproj").is_file())
        self.assertEqual(self.read(".bootstrap-complete"), "initialized\n")
        self.assertFalse((self.repo / ".bootstrap-in-progress").exists())

    def test_universal_and_custom_display_name(self):
        self.assert_success(self.bootstrap(*self.options(**{
            "app-name": "TravelNotes",
            "bundle-id": "jp.example.travel-notes",
            "platform": "universal",
            "deployment-target": "27.1",
            "display-name": DISPLAY_NAME,
            "team-id": "ABCDE12345",
        })))
        project = self.read("project.yml")
        self.assertTrue(project.startswith('name: "TravelNotes"\n'))
        self.assertIn('TARGETED_DEVICE_FAMILY: "1,2"\n', project)
        self.assertIn('iOS: "27.1"\n', project)
        self.assertIn('DEVELOPMENT_TEAM: "ABCDE12345"\n', project)
        display_value = re.search(r"INFOPLIST_KEY_CFBundleDisplayName: (.+)", project)[1]
        self.assertEqual(json.loads(display_value), DISPLAY_NAME)
        for filename in ("README.md", "CLAUDE.md"):
            self.assertIn('家計簿 \\"Plus\\" \\& \\[共有\\]', self.read(filename))
            self.assertIn("iPhone / iPad", self.read(filename))
        self.assertTrue((self.repo / "TravelNotes.xcodeproj" / "project.pbxproj").is_file())

    def test_interactive_defaults(self):
        bootstrap = self.load_bootstrap()
        with patch.object(sys, "argv", ["bootstrap.py"]), patch.object(sys.stdin, "isatty", return_value=True):
            with patch("builtins.input", side_effect=[APP_NAME, "", BUNDLE_ID, "", "", ""]):
                args = bootstrap.arguments()
        self.assertEqual(args.display_name, APP_NAME)
        self.assertEqual(args.platform, "iphone")
        self.assertEqual(args.deployment_target, "26.0")
        self.assertIsNone(args.team_id)

    def test_accepts_deployment_target_format_and_writes_version(self):
        bootstrap = self.load_bootstrap()
        for version in ("18.0", "26.0", "26.5", "26.6", "27.0", "27.1"):
            with self.subTest(version=version):
                with patch.object(sys, "argv", ["bootstrap.py", *self.options(**{"deployment-target": version})]):
                    args = bootstrap.arguments()
                self.assertIn(f'iOS: "{version}"\n', bootstrap.update_project(self.read("project.yml"), args))

    def test_rejects_invalid_deployment_targets(self):
        for version in ("abc", "26", "26.-1", "26.0.1", "", "-26.0", "0.0", "026.0", "26.01"):
            with self.subTest(version=version):
                result = self.bootstrap(*self.options(**{"deployment-target": version}))
                self.assert_rejected(result, "--deployment-target must use major.minor")
        self.assertEqual(self.snapshot(), self.before)

    def test_rejects_invalid_or_incomplete_options(self):
        for option, value, message in (
            ("app-name", "3 bad app", "--app-name must start"),
            ("bundle-id", "com..budgetmate", "--bundle-id must use reverse-DNS syntax"),
            ("platform", "ipad", "invalid choice"),
            ("team-id", "abcde12345", "--team-id must be 10 uppercase"),
            ("team-id", "ABCDE1234", "--team-id must be 10 uppercase"),
        ):
            with self.subTest(option=option):
                self.assert_rejected(self.bootstrap(*self.options(**{option: value})), message)
        self.assert_rejected(self.bootstrap("--app-name", APP_NAME), "--bundle-id must use reverse-DNS syntax")
        self.assertEqual(self.snapshot(), self.before)

    def test_rejects_second_initialization(self):
        self.assert_success(self.bootstrap(*self.options()))
        # Bootstrap removes itself, so restore it to check the completion marker guard.
        for filename in ("scripts/bootstrap.sh", "scripts/bootstrap.py"):
            shutil.copy2(TEMPLATE / filename, self.repo / filename)
        initialized = self.snapshot()
        self.assert_rejected(self.bootstrap(*self.options()), "already initialized")
        self.assertEqual(self.snapshot(), initialized)

    @unittest.skipIf(os.geteuid() == 0, "root can delete files in a read-only directory")
    def test_cleanup_failure_keeps_completed_initialization(self):
        scripts = self.repo / "scripts"
        scripts.chmod(0o555)
        self.addCleanup(scripts.chmod, 0o755)
        result = self.bootstrap(*self.options())
        self.assert_success(result)
        self.assertIn("could not remove template files", result.stderr)
        self.assertEqual(self.read(".bootstrap-complete"), "initialized\n")
        self.assertTrue((self.repo / PROJECT_NAME / "project.pbxproj").is_file())
        self.assertTrue((scripts / "bootstrap.py").is_file())

    def test_refuses_existing_transaction_or_project(self):
        for directory, message in (
            (".bootstrap-in-progress", "in progress or was interrupted"),
            (PROJECT_NAME, "already exists"),
        ):
            with self.subTest(directory=directory):
                existing = self.repo / directory
                existing.mkdir()
                (existing / "preserve").write_text("existing data", encoding="utf-8")
                before = self.snapshot()
                self.assert_rejected(self.bootstrap(*self.options()), message)
                self.assertEqual(self.snapshot(), before)
                shutil.rmtree(existing)

    def test_rejects_unexpected_placeholder(self):
        project = self.repo / "project.yml"
        project.write_text(
            self.read("project.yml").replace("com.example.starterapp.tests", "com.example.changed.tests"),
            encoding="utf-8",
        )
        before = self.snapshot()
        self.assert_rejected(self.bootstrap(*self.options()), "Unexpected occurrences")
        self.assertEqual(self.snapshot(), before)

    def test_generator_failure_or_missing_output_leaves_originals(self):
        for mode, message in (
            ("fail", "non-zero exit status 17"),
            ("missing-output", "XcodeGen did not create"),
        ):
            with self.subTest(mode=mode):
                self.assert_rejected(self.bootstrap(*self.options(), mode=mode), message)
                self.assertEqual(self.snapshot(), self.before)
        self.assert_success(self.bootstrap(*self.options()))

    def test_publish_failure_restores_files_and_allows_retry(self):
        bootstrap = self.load_bootstrap()
        before = self.snapshot()

        with patch.object(sys, "argv", ["bootstrap.py", *self.options()]):
            args = bootstrap.arguments()
        for filename in ("README.md", ".bootstrap-complete"):
            with self.subTest(filename=filename):
                fail_at = self.repo / filename
                failed = False

                def fail_publish(source, destination):
                    nonlocal failed
                    if destination == fail_at and not failed:
                        failed = True
                        self.assertIn(APP_NAME, self.read("project.yml"))
                        self.assertTrue((bootstrap.TRANSACTION / "backup" / "project.yml").is_file())
                        self.assertEqual((self.repo / PROJECT_NAME).is_dir(), fail_at == bootstrap.COMPLETE)
                        raise OSError("injected publication failure")
                    os.replace(source, destination)

                failing_os = SimpleNamespace(replace=fail_publish)
                with patch.dict(os.environ, self.env), patch.object(bootstrap, "os", failing_os):
                    with self.assertRaisesRegex(OSError, "injected publication failure"):
                        bootstrap.initialize(args)
                self.assertEqual(self.snapshot(), before)
        self.assert_success(self.bootstrap(*self.options()))


if __name__ == "__main__":
    unittest.main()
