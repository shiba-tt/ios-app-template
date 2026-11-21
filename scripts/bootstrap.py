"""Initialize one checkout of the starter without editing it before generation."""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import signal
import string
import subprocess
import sys


ROOT = Path(__file__).resolve().parent.parent
COMPLETE = ROOT / ".bootstrap-complete"
TRANSACTION = ROOT / ".bootstrap-in-progress"
EDITED_FILES = ("project.yml", "App/AppEntry.swift", "README.md", "CLAUDE.md")
DEVICE_FAMILIES = {"iphone": "1", "universal": "1,2"}


def arguments():
    parser = argparse.ArgumentParser(
        description="Initialize an app repository created from ios-app-template.",
        epilog=(
            "Run without options for interactive mode. For unattended use, supply --app-name, "
            "--bundle-id, --platform, and --deployment-target. "
            "Use a bundle ID you control for release. com.example IDs are examples only."
        ),
        allow_abbrev=False,
    )
    parser.add_argument("--app-name", help="Internal name (ASCII letters and digits, starting with a letter)")
    parser.add_argument("--display-name", help="Home Screen name (defaults to the internal name)")
    parser.add_argument("--bundle-id", help="Reverse-DNS bundle identifier")
    parser.add_argument("--platform", choices=DEVICE_FAMILIES, help="Device family")
    parser.add_argument("--deployment-target", help="Minimum iOS version, e.g. 26.0")
    args = parser.parse_args()
    ensure_uninitialized()

    if len(sys.argv) == 1:
        if not sys.stdin.isatty():
            parser.error("interactive mode requires a terminal. Supply the four required options.")
        args.app_name = input("Internal app name (e.g. BudgetMate): ").strip()
        args.display_name = input(f"Home Screen name [{args.app_name}]: ").strip() or None
        args.bundle_id = input("Bundle ID (e.g. com.yourcompany.budgetmate): ").strip()
        args.platform = input("Device family (iphone/universal) [iphone]: ").strip() or "iphone"
        args.deployment_target = input("Minimum iOS version [26.0]: ").strip() or "26.0"

    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]{0,39}", args.app_name or ""):
        parser.error("--app-name must start with an ASCII letter and use 1–40 ASCII letters or digits.")
    if args.app_name.lower() in {"swift", "swiftui", "foundation", "testing", "xctest", "objectivec"}:
        parser.error("--app-name conflicts with a Swift or Apple framework module.")
    if args.display_name is None:
        args.display_name = args.app_name
    if not args.display_name.strip() or not args.display_name.isprintable() or "$" in args.display_name:
        parser.error("--display-name must be non-blank, fit on one line, and contain no '$'.")
    component = r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?"
    if not re.fullmatch(rf"{component}(?:\.{component})+", args.bundle_id or ""):
        parser.error("--bundle-id must use reverse-DNS syntax, e.g. com.example.budgetmate.")
    if args.platform not in DEVICE_FAMILIES:
        parser.error("--platform must be iphone or universal.")

    version = re.fullmatch(r"(1[5-8]|26)\.(0|[1-9][0-9]?)", args.deployment_target or "")
    if not version or (version[1] == "26" and int(version[2]) > 5):
        parser.error("--deployment-target must use major.minor, with iOS 15–18 or 26.0–26.5.")
    return args


def ensure_uninitialized():
    if COMPLETE.exists():
        raise ValueError("This repository is already initialized. Edit project.yml to change app settings.")
    if TRANSACTION.exists():
        raise ValueError("Initialization is in progress or was interrupted. See README.md for recovery.")


def replace_exact(content, old, new, expected=1):
    if content.count(old) != expected:
        raise ValueError(f"Unexpected template content for {old!r}. Restore the template before bootstrapping.")
    return content.replace(old, new)


def update_project(content, args):
    # Substitute the display name separately so app identifiers never alter user-provided text.
    display_setting = 'INFOPLIST_KEY_CFBundleDisplayName: "StarterApp"'
    placeholder = "INFOPLIST_KEY_CFBundleDisplayName: __BOOTSTRAP_DISPLAY_NAME__"
    content = replace_exact(content, display_setting, placeholder)
    identifiers = {
        '"StarterApp"': (f'"{args.app_name}"', 4),
        '"StarterAppTests"': (f'"{args.app_name}Tests"', 2),
        '"StarterAppUITests"': (f'"{args.app_name}UITests"', 2),
        **{
            f'"com.example.starterapp{suffix}"': (f'"{args.bundle_id}{suffix}"', 1)
            for suffix in ("", ".tests", ".uitests")
        },
    }
    for old, (_, count) in identifiers.items():
        if content.count(old) != count:
            raise ValueError(f"Unexpected occurrences of {old} in project.yml.")
    pattern = "|".join(re.escape(old) for old in identifiers)
    content = re.sub(pattern, lambda match: identifiers[match[0]][0], content)
    content = replace_exact(content, 'iOS: "26.0"', f'iOS: "{args.deployment_target}"')
    content = replace_exact(
        content, 'TARGETED_DEVICE_FAMILY: "1"', f'TARGETED_DEVICE_FAMILY: "{DEVICE_FAMILIES[args.platform]}"'
    )
    return replace_exact(
        content, placeholder,
        "INFOPLIST_KEY_CFBundleDisplayName: " + json.dumps(args.display_name, ensure_ascii=False),
    )


def replace_intro(content, next_heading, introduction):
    if content.count(next_heading) != 1:
        raise ValueError(f"Could not find the documentation section {next_heading.strip()!r}.")
    return introduction + next_heading + content.split(next_heading, 1)[1]


def stage_files(stage, args):
    for directory in ("App", "Tests"):
        shutil.copytree(ROOT / directory, stage / directory)

    display_name = args.display_name.translate({ord(char): "\\" + char for char in string.punctuation})
    devices = {"iphone": "iPhone", "universal": "iPhone / iPad"}[args.platform]
    product = (
        f"ホーム画面での表示名は「{display_name}」です。"
        f"Bundle ID は `{args.bundle_id}`、対応デバイスは {devices}、"
        f"Deployment Target は iOS {args.deployment_target} です。\n"
    )
    replacements = {
        "project.yml": lambda content: update_project(content, args),
        "App/AppEntry.swift": lambda content: replace_exact(content, "StarterAppEntry", f"{args.app_name}Entry"),
        "README.md": lambda content: replace_intro(
            content, "## 開発環境\n",
            f"# {args.app_name}\n\n{product}\n"
            "このリポジトリは初期化済みです。アプリ設定は `project.yml` で管理します。\n\n",
        ),
        "CLAUDE.md": lambda content: replace_intro(
            content, "## 開発\n",
            f"# CLAUDE.md\n\n## アプリ概要\n\n{product}\n",
        ),
    }
    for filename, update in replacements.items():
        source = ROOT / filename
        (stage / filename).write_text(update(source.read_text(encoding="utf-8")), encoding="utf-8")


def publish(stage, project):
    backup = TRANSACTION / "backup"
    staged_project = stage / project.name
    try:
        for filename in EDITED_FILES:
            os.replace(stage / filename, ROOT / filename)
        os.replace(staged_project, project)
        os.replace(stage / COMPLETE.name, COMPLETE)
    except BaseException:
        # Once the completion marker is installed, all app files are in place.
        if not COMPLETE.exists():
            for filename in EDITED_FILES:
                shutil.copy2(backup / filename, stage / filename)
                os.replace(stage / filename, ROOT / filename)
            if not staged_project.exists():
                os.replace(project, staged_project)
        shutil.rmtree(TRANSACTION)
        raise


def initialize(args):
    if shutil.which("xcodegen") is None:
        raise ValueError("xcodegen is missing. Run mise install, then mise exec -- ./scripts/bootstrap.sh.")
    try:
        TRANSACTION.mkdir()
    except FileExistsError:
        raise ValueError("Initialization is in progress or was interrupted. See README.md for recovery.") from None

    stage = TRANSACTION / "stage"
    project = ROOT / f"{args.app_name}.xcodeproj"
    try:
        if COMPLETE.exists():
            raise ValueError("This repository is already initialized.")
        if project.exists() or project.is_symlink():
            raise ValueError(f"{project.name} already exists. Move it aside before running bootstrap.")
        stage.mkdir()
        stage_files(stage, args)
        subprocess.run(["xcodegen", "generate"], cwd=stage, check=True)
        if not (stage / project.name / "project.pbxproj").is_file():
            raise ValueError(f"XcodeGen did not create {project.name}/project.pbxproj.")
        (stage / COMPLETE.name).write_text("initialized\n", encoding="utf-8")
        for filename in EDITED_FILES:
            original = TRANSACTION / "backup" / filename
            original.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / filename, original)
        if project.exists() or project.is_symlink():
            raise ValueError(f"{project.name} appeared during generation. Move it aside and retry.")
    except BaseException:
        shutil.rmtree(TRANSACTION)
        raise

    # A failed rollback leaves the transaction and original files available for recovery.
    publish(stage, project)
    shutil.rmtree(TRANSACTION)

    if args.bundle_id.lower() == "com.example" or args.bundle_id.lower().startswith("com.example."):
        print("Note: com.example is reserved for examples. Use your own bundle ID for release.")
    print(f"Initialized {args.app_name}. Open {project.name} to build and test.")


def interrupt(_signum, _frame):
    raise KeyboardInterrupt


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, interrupt)
    try:
        initialize(arguments())
    except (EOFError, KeyboardInterrupt):
        sys.exit("bootstrap: interrupted.")
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        sys.exit(f"bootstrap: {error}")
