#!/usr/bin/env python3
"""PreToolUse hook: force a user prompt for Git and GitHub operations that change state.

Permission rules match command prefixes, so forms such as `git -C . push` or `sh -c 'git push'`
miss `Bash(git push *)`, and auto mode may then approve them. This hook catches those common forms.
It reduces accidental bypasses but is not a security boundary against arbitrary code execution.
"""

import json
import re
import sys


REASON = "Git / GitHub の状態を変更する操作です。実行内容を確認して承認してください。"
UNDECIDABLE_REASON = "コマンドを解析できなかったため、実行内容の確認が必要です。"

COMMAND_START = r"(?:^|[\s;&|()`=/!])"
GIT_GLOBAL_OPTIONS = (
    r"(?:\s+(?:-C\s+\S+|-c\s+\S+|--(?:git-dir|work-tree|namespace|config-env)(?:=\S*|\s+\S+)|-{1,2}[\w-]+))*"
)
GIT_MUTATION = re.compile(
    COMMAND_START + r"git" + GIT_GLOBAL_OPTIONS + r"\s+"
    r"(?:am|apply|clean|commit|config|cherry-pick|filter-branch|merge|push|rebase|reset|restore|revert|rm|stash"
    r"|tag|update-ref)(?![\w-])"
)
# An inline config can define an alias or a command that runs in place of the visible subcommand.
GIT_INLINE_CONFIG = re.compile(COMMAND_START + r"git(?:\s+-{1,2}[\w-]+(?:=\S*)?|\s+-C\s+\S+)*\s+-c\s")
GH_MUTATION = re.compile(
    COMMAND_START + r"gh\s+(?:"
    r"pr\s+(?:close|comment|create|edit|lock|merge|ready|reopen|review|unlock|update-branch)"
    r"|run\s+(?:cancel|delete|rerun)"
    r"|workflow\s+(?:disable|enable|run)"
    r"|issue\s+(?:close|comment|create|delete|edit|lock|pin|reopen|transfer|unlock|unpin)"
    r"|release|secret|variable|ruleset|repo\s+(?:archive|create|delete|edit|fork|rename|sync|unarchive)"
    r")(?![\w-])"
)
GH_API = re.compile(COMMAND_START + r"gh\s+api(?![\w-])([^;&|\n]*)")
GH_API_WRITE_OPTION = re.compile(r"(?:^|\s)(?:-X|-f|-F|--method|--field|--raw-field|--input)(?:[=\s]|$)|(?:^|\s)-[XfF]\S")


def requires_approval(command):
    # Removing quoting exposes split names such as "git", gi''t, and g\it.
    normalized = re.sub(r"['\"\\]", "", command)
    if GIT_MUTATION.search(normalized) or GIT_INLINE_CONFIG.search(normalized):
        return True
    if GH_MUTATION.search(normalized):
        return True
    return any(GH_API_WRITE_OPTION.search(match) for match in GH_API.findall(normalized))


def decide(payload):
    """Return a permission reason, or None when this hook has no opinion."""
    if not isinstance(payload, dict):
        return UNDECIDABLE_REASON
    if payload.get("tool_name") != "Bash":
        return None
    tool_input = payload.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str):
        return UNDECIDABLE_REASON
    return REASON if requires_approval(command) else None


def main():
    try:
        reason = decide(json.loads(sys.stdin.buffer.read()))
    except Exception:  # Prompting is the safe outcome when the command cannot be inspected.
        reason = UNDECIDABLE_REASON
    if reason:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "ask",
                "permissionDecisionReason": reason,
            },
        }))


if __name__ == "__main__":
    main()
