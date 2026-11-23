"""Exercise the CI helper scripts in isolated checkouts with stub Apple tools."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


TEMPLATE = Path(__file__).resolve().parents[2]
RUNTIME_PREFIX = "com.apple.CoreSimulator.SimRuntime."
DEVICE_TYPE_PREFIX = "com.apple.CoreSimulator.SimDeviceType."
DESTINATION = "platform=iOS Simulator,id=TEST-UDID"


def write_executable(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def runtime(version, identifier=None, available=True):
    suffix = identifier or f"iOS-{version.replace('.', '-')}"
    return {
        "identifier": RUNTIME_PREFIX + suffix,
        "name": f"iOS {version}",
        "version": version,
        "buildversion": "TEST",
        "isAvailable": available,
    }


def device(name, udid):
    return {
        "name": name,
        "udid": udid,
        "deviceTypeIdentifier": DEVICE_TYPE_PREFIX + name.replace(" ", "-"),
        "isAvailable": True,
        "state": "Shutdown",
    }


class SelectSimulatorTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ios-simulator-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.data = self.root / "simctl.json"
        write_executable(
            self.root / "bin/xcrun",
            """#!/usr/bin/env python3
import json
import os
import sys

assert sys.argv[1:4] == ["simctl", "list", "--json"]
data = json.load(open(os.environ["SIMCTL_DATA"], encoding="utf-8"))
key = sys.argv[4]
print(json.dumps({key: data[key]}))
""",
        )

    def select(self, *args, runtimes, devices):
        self.data.write_text(json.dumps({"runtimes": runtimes, "devices": devices}), encoding="utf-8")
        env = dict(
            os.environ,
            PATH=os.pathsep.join((str(self.root / "bin"), os.environ["PATH"])),
            SIMCTL_DATA=str(self.data),
        )
        return subprocess.run(
            [sys_executable(), str(TEMPLATE / "scripts/select_simulator.py"), *args],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=20,
        )

    def test_prefers_candidate_and_logs_selection(self):
        result = self.select(
            "--runtime", "27.2", "--prefer", "iPhone 17", "--prefer", "iPhone Air",
            runtimes=[runtime("27.2")],
            devices={RUNTIME_PREFIX + "iOS-27-2": [
                device("iPhone Air", "AIR"),
                device("iPhone 17", "SEVENTEEN"),
            ]},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "platform=iOS Simulator,id=SEVENTEEN\n")
        for expected in ("iPhone 17", "27.2", "SEVENTEEN"):
            self.assertIn(expected, result.stderr)

    def test_falls_back_to_another_iphone_on_same_runtime(self):
        result = self.select(
            "--runtime", "27.2", "--prefer", "iPhone 99",
            runtimes=[runtime("27.2"), runtime("27.1")],
            devices={
                RUNTIME_PREFIX + "iOS-27-1": [device("iPhone 99", "OTHER-RUNTIME")],
                RUNTIME_PREFIX + "iOS-27-2": [
                    device("iPad Air", "IPAD"),
                    device("iPhone Air", "AIR"),
                    device("iPhone 17e", "E"),
                ],
            },
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "platform=iOS Simulator,id=E\n")

    def test_does_not_match_device_specific_runtime(self):
        result = self.select(
            "--runtime", "27.2",
            runtimes=[runtime("27.2", identifier="iOS-27-2-iPhone19-4")],
            devices={RUNTIME_PREFIX + "iOS-27-2-iPhone19-4": [device("iPhone Duo", "DUO")]},
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("iOS 27.2", result.stderr)

    def test_missing_or_unavailable_runtime_never_uses_another_version(self):
        for runtimes in ([runtime("27.1")], [runtime("27.2", available=False), runtime("27.1")]):
            with self.subTest(runtimes=runtimes):
                result = self.select(
                    "--runtime", "27.2",
                    runtimes=runtimes,
                    devices={RUNTIME_PREFIX + "iOS-27-1": [device("iPhone 17", "OLD")]},
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertIn("27.1", result.stderr)

    def test_runtime_without_requested_family_fails(self):
        result = self.select(
            "--runtime", "27.2",
            runtimes=[runtime("27.2")],
            devices={RUNTIME_PREFIX + "iOS-27-2": [device("iPad Air", "IPAD")]},
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("iphone", result.stderr.lower())

    def test_family_option_supports_future_ipad_selection(self):
        result = self.select(
            "--runtime", "27.2", "--family", "ipad",
            runtimes=[runtime("27.2")],
            devices={RUNTIME_PREFIX + "iOS-27-2": [
                device("iPhone 17", "PHONE"),
                device("iPad Air", "IPAD"),
            ]},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "platform=iOS Simulator,id=IPAD\n")

    def test_rejects_invalid_runtime_format(self):
        for version in ("27", "latest", "27.2.1", "iOS 27.2"):
            with self.subTest(version=version):
                result = self.select("--runtime", version, runtimes=[runtime("27.2")], devices={})
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")


class SelectXcodeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ios-xcode-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.repo = self.root / "repo"
        (self.repo / "scripts").mkdir(parents=True)
        shutil.copy2(TEMPLATE / "scripts/select_xcode.sh", self.repo / "scripts/select_xcode.sh")
        self.applications = self.root / "Applications"

    def install_xcode(self, directory, reported_version):
        write_executable(
            self.applications / directory / "Contents/Developer/usr/bin/xcodebuild",
            f"#!/bin/sh\nprintf 'Xcode {reported_version}\\nBuild version TEST\\n'\n",
        )

    def select(self, version):
        (self.repo / ".xcode-version").write_text(version, encoding="utf-8")
        return subprocess.run(
            [str(self.repo / "scripts/select_xcode.sh")],
            cwd=self.root,
            env=dict(os.environ, XCODE_APPLICATIONS_DIR=str(self.applications)),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=20,
        )

    def test_prints_developer_dir_for_pinned_version(self):
        self.install_xcode("Xcode_27.2.app", "27.2")
        result = self.select("27.2\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.strip(),
            str(self.applications / "Xcode_27.2.app/Contents/Developer"),
        )
        self.assertIn("Xcode 27.2", result.stderr)

    def test_missing_version_fails_without_fallback(self):
        self.install_xcode("Xcode.app", "27.1")
        self.install_xcode("Xcode_27.1.app", "27.1")
        result = self.select("27.2\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("27.2", result.stderr)
        self.assertIn("Xcode_27.1.app", result.stderr)

    def test_reported_version_must_match(self):
        self.install_xcode("Xcode_27.2.app", "27.1")
        result = self.select("27.2\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_rejects_malformed_version_file(self):
        for version in ("", "latest\n", "27.2\nEVIL=1\n", "../27.2\n"):
            with self.subTest(version=version):
                result = self.select(version)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")


class CheckScriptTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ios-check-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.repo = self.root / "repo"
        (self.repo / "scripts").mkdir(parents=True)
        for filename in ("project.yml", ".xcode-version", "scripts/check.sh"):
            shutil.copy2(TEMPLATE / filename, self.repo / filename)
        self.xcode_version = (TEMPLATE / ".xcode-version").read_text(encoding="utf-8").strip()
        self.calls = self.root / "calls.log"
        bin_dir = self.root / "bin"
        write_executable(
            bin_dir / "xcodebuild",
            """#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys

args = sys.argv[1:]
if args == ["-version"]:
    print("Xcode " + os.environ["STUB_XCODE_VERSION"])
    print("Build version TEST")
    sys.exit(0)
if "-list" in args:
    print(json.dumps({"project": {
        "name": "StarterApp",
        "schemes": ["StarterApp"],
        "targets": os.environ.get(
            "STUB_TARGETS", "StarterApp,StarterAppTests,StarterAppUITests"
        ).split(","),
    }}))
    sys.exit(0)
with open(os.environ["STUB_CALLS"], "a", encoding="utf-8") as calls:
    calls.write("xcodebuild " + " ".join(args) + "\\n")
print("stub xcodebuild output")
if "-resultBundlePath" in args:
    Path(args[args.index("-resultBundlePath") + 1]).mkdir()
if args[-1] == os.environ.get("STUB_FAIL_ACTION"):
    sys.exit(65)
""",
        )
        write_executable(
            bin_dir / "xcrun",
            '#!/bin/sh\nprintf "xcrun %s\\n" "$*" >> "$STUB_CALLS"\n',
        )
        write_executable(
            bin_dir / "swiftlint",
            '#!/bin/sh\nprintf "swiftlint %s\\n" "$*" >> "$STUB_CALLS"\n',
        )
        write_executable(
            bin_dir / "xcodegen",
            """#!/bin/sh
printf 'xcodegen %s\\n' "$*" >> "$STUB_CALLS"
mkdir -p StarterApp.xcodeproj/xcshareddata/xcschemes
{
  printf 'BlueprintName = "StarterAppTests"\\n'
  [ -n "${STUB_SCHEME_WITHOUT_UI_TESTS:-}" ] || printf 'BlueprintName = "StarterAppUITests"\\n'
} > StarterApp.xcodeproj/xcshareddata/xcschemes/StarterApp.xcscheme
""",
        )
        self.env = dict(
            os.environ,
            PATH=os.pathsep.join((str(bin_dir), os.environ["PATH"])),
            STUB_CALLS=str(self.calls),
            STUB_XCODE_VERSION=self.xcode_version,
        )

    def check(self, *args, **env):
        return subprocess.run(
            [str(self.repo / "scripts/check.sh"), *args],
            cwd=self.root,
            env=dict(self.env, **env),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=20,
        )

    def recorded(self):
        if not self.calls.exists():
            return []
        return self.calls.read_text(encoding="utf-8").splitlines()

    def xcodebuild_call(self, action):
        matches = [
            line for line in self.recorded()
            if line.startswith("xcodebuild ") and line.endswith(f" {action}")
        ]
        self.assertEqual(len(matches), 1, self.recorded())
        return matches[0]

    def test_default_invocation_keeps_full_local_validation(self):
        result = self.check(DESTINATION)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        calls = self.recorded()
        self.assertTrue(calls[0].startswith("xcrun swift-format lint --strict"))
        self.assertTrue(calls[1].startswith("swiftlint lint --strict"))
        self.assertEqual(calls[2], "xcodegen generate")
        self.assertNotIn("-only-testing", self.xcodebuild_call("test"))
        self.assertNotIn("CODE_SIGNING_ALLOWED", self.xcodebuild_call("build"))

    def test_unit_scope_excludes_ui_tests(self):
        result = self.check("--stage", "test", "--tests", "unit", DESTINATION)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        call = self.xcodebuild_call("test")
        self.assertIn("-only-testing:StarterAppTests", call)
        self.assertNotIn("StarterAppUITests", call)

    def test_ui_scope_runs_only_ui_tests(self):
        result = self.check("--stage", "test", "--tests", "ui", DESTINATION)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        call = self.xcodebuild_call("test")
        self.assertIn("-only-testing:StarterAppUITests", call)
        self.assertNotIn("-only-testing:StarterAppTests", call)

    def test_ci_output_disables_signing_and_saves_diagnostics(self):
        output = self.root / "diagnostics"
        for arguments in (("--stage", "build"), ("--stage", "test", "--tests", "unit")):
            result = self.check(*arguments, "--ci-output", str(output), DESTINATION)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("CODE_SIGNING_ALLOWED=NO", self.xcodebuild_call("build"))
        self.assertIn("CODE_SIGNING_ALLOWED=NO", self.xcodebuild_call("test"))
        self.assertIn("stub xcodebuild output", (output / "build.log").read_text(encoding="utf-8"))
        self.assertIn("stub xcodebuild output", (output / "test-unit.log").read_text(encoding="utf-8"))
        self.assertTrue((output / "test-unit.xcresult").is_dir())

    def test_xcodebuild_failure_propagates_through_log_capture(self):
        result = self.check(
            "--stage", "test", "--tests", "unit",
            "--ci-output", str(self.root / "diagnostics"),
            DESTINATION,
            STUB_FAIL_ACTION="test",
        )
        self.assertEqual(result.returncode, 65, result.stdout + result.stderr)

    def test_generate_stage_needs_no_destination_and_verifies_project(self):
        result = self.check("--stage", "generate")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.recorded(), ["xcodegen generate"])

    def test_generate_stage_fails_when_test_target_is_missing(self):
        for env, message in (
            ({"STUB_TARGETS": "StarterApp,StarterAppTests"}, "StarterAppUITests"),
            ({"STUB_SCHEME_WITHOUT_UI_TESTS": "1"}, "StarterAppUITests"),
        ):
            with self.subTest(env=env):
                result = self.check("--stage", "generate", **env)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)

    def test_rejects_invalid_usage(self):
        for arguments in (
            (),
            ("not-a-destination",),
            ("--stage", "deploy", DESTINATION),
            ("--tests", "smoke", DESTINATION),
            ("--stage", "build"),
            ("--stage", "quality", DESTINATION),
            ("--ci-output",),
        ):
            with self.subTest(arguments=arguments):
                self.assertEqual(self.check(*arguments).returncode, 2)
        self.assertEqual(self.recorded(), [])


def sys_executable():
    return shutil.which("python3") or "python3"


if __name__ == "__main__":
    unittest.main()
