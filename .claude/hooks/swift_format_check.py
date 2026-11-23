#!/usr/bin/env python3
"""PostToolUse hook: report swift-format findings for one edited Swift file.

The hook only reads. It never rewrites code or blocks Claude, and it always exits 0 so a
half-finished edit does not interrupt the work. Builds and tests belong to the verify-ios skill.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


EDIT_TOOLS = {"Write", "Edit", "MultiEdit"}
SOURCE_DIRECTORIES = {"App", "Tests"}
FORMAT_TIMEOUT_SECONDS = 10
MAX_FINDINGS_CHARACTERS = 2000


def project_root(payload):
    """Find the checkout from the session cwd so linked worktrees check their own files."""
    for candidate in (payload.get("cwd"), os.environ.get("CLAUDE_PROJECT_DIR")):
        if not isinstance(candidate, str) or not candidate or "\0" in candidate:
            continue
        try:
            start = Path(candidate).resolve()
            for directory in (start, *start.parents):
                if (directory / "project.yml").is_file() and (directory / ".claude").is_dir():
                    return directory
        except (OSError, RuntimeError, ValueError):
            continue
    return None


def target_file(payload, root):
    """Return the resolved Swift file when it is a real file under App/ or Tests/."""
    tool_input = payload.get("tool_input")
    if payload.get("tool_name") not in EDIT_TOOLS or not isinstance(tool_input, dict):
        return None
    raw_path = tool_input.get("file_path")
    if not isinstance(raw_path, str) or not raw_path or "\0" in raw_path:
        return None
    try:
        path = Path(raw_path)
        if not path.is_absolute():
            path = root / path
        # Resolving first means a symlink cannot lead the check outside the project.
        resolved = path.resolve()
        parts = resolved.relative_to(root).parts
        if path.suffix != ".swift" or resolved.suffix != ".swift":
            return None
        if not parts or parts[0] not in SOURCE_DIRECTORIES or not resolved.is_file():
            return None
    except (OSError, RuntimeError, ValueError):
        return None
    return resolved


def printable(text):
    return "".join(character for character in text if character.isprintable() or character in "\n\t")


def lint(file_path, root):
    """Return a message for Claude, or None when the file passes."""
    xcrun = shutil.which("xcrun")
    if xcrun is None:
        return "swift-format の確認をスキップしました。xcrun が見つかりません。固定した Xcode を選択してください。"
    try:
        # An argument list keeps file names from being interpreted by a shell.
        result = subprocess.run(
            [xcrun, "swift-format", "lint", "--strict", str(file_path)],
            cwd=root,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=FORMAT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return f"swift-format が {FORMAT_TIMEOUT_SECONDS} 秒でタイムアウトしたため確認をスキップしました。"
    except OSError as error:
        return f"swift-format の確認をスキップしました。実行できません: {error}"
    if result.returncode == 0:
        return None

    output = printable((result.stderr + result.stdout).strip())
    if "unable to find utility" in output:
        return "swift-format の確認をスキップしました。選択中の Xcode に swift-format がありません。"
    if len(output) > MAX_FINDINGS_CHARACTERS:
        output = output[:MAX_FINDINGS_CHARACTERS] + "\n…（以降は省略）"
    return (
        "swift-format の指摘です。Hook は自動修正していません。"
        "編集途中の構文エラーであれば、実装の区切りで確認してください。\n" + output
    )


def main():
    try:
        payload = json.loads(sys.stdin.buffer.read())
    except (ValueError, RecursionError):
        return
    if not isinstance(payload, dict):
        return
    root = project_root(payload)
    if root is None:
        return
    file_path = target_file(payload, root)
    if file_path is None:
        return
    message = lint(file_path, root)
    if message:
        print(json.dumps({
            "hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": message},
        }))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:  # A lint helper must never interrupt the edit it follows.
        print(f"swift_format_check: {error}", file=sys.stderr)
    sys.exit(0)
