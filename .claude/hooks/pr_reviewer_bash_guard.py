#!/usr/bin/env python3
"""PreToolUse hook for pr-reviewer: allow one read-only git or gh command at a time.

This is an allowlist. Anything it does not recognize is denied, including malformed input, shell
composition, and flags that write files, run programs, or read outside the repository.
"""

import json
import re
import shlex
import sys
from urllib.parse import unquote


DENY_REASON = (
    "pr-reviewer は読み取り専用です。許可されるのは単一の git / gh 読み取りコマンドだけです。"
    "パイプ、リダイレクト、複合コマンド、書き込みや外部実行を伴うオプションは使えません。"
)
ALLOW_REASON = "pr-reviewer の読み取り専用コマンドです。"
# Unquoted characters that would make the shell do more than run a single argument list.
SHELL_SYNTAX = set(";&|<>()$`\\{}*?[]#!")

# A URL could name another repository, so only numbers that gh resolves in this repository pass.
PR_TARGET = re.compile(r"[1-9][0-9]*")
RUN_ID = re.compile(r"[1-9][0-9]*")
API_PATH = re.compile(
    r"repos/\{owner\}/\{repo\}/(?:contents|pulls|commits|compare)"
    r"(?:/[A-Za-z0-9._~%+@/-]*)?(?:\?[A-Za-z0-9._~%+=&/-]*)?"
)
API_ACCEPT = re.compile(r"Accept: application/vnd\.github[a-z0-9.+-]*")

# Each flag maps to whether it consumes a value. --jq is excluded because jq can read env secrets.
OUTPUT_FLAGS = {"--json": True}
GH_COMMANDS = {
    ("pr", "view"): ({**OUTPUT_FLAGS, "--comments": False, "-c": False}, PR_TARGET),
    ("pr", "diff"): ({"--name-only": False, "--patch": False}, PR_TARGET),
    ("pr", "checks"): ({**OUTPUT_FLAGS, "--required": False}, PR_TARGET),
    ("run", "view"): (
        {**OUTPUT_FLAGS, "--log-failed": False, "--log": False, "--job": True, "-j": True,
         "--attempt": True, "-a": True},
        RUN_ID,
    ),
    ("run", "list"): (
        {**OUTPUT_FLAGS, "--branch": True, "-b": True, "--commit": True, "-c": True,
         "--limit": True, "-L": True},
        None,
    ),
    ("repo", "view"): (OUTPUT_FLAGS, None),
}
GH_API_FLAGS = {"--paginate": False, "-H": True, "--header": True}

GIT_COMMANDS = {"status", "diff", "log", "show", "rev-parse", "ls-files", "blame", "merge-base", "grep"}
# Git accepts abbreviated long options, so flags are matched exactly instead of denylisted.
GIT_FLAGS = {
    "--abbrev-commit", "--abbrev-ref", "--all", "--branch", "--cached", "--decorate", "--first-parent",
    "--follow", "--is-inside-work-tree", "--merges", "--name-only", "--name-status", "--no-color",
    "--no-merges", "--no-patch", "--no-renames", "--numstat", "--oneline", "--patch", "--porcelain",
    "--reverse", "--short", "--shortstat", "--show-toplevel", "--staged", "--stat", "--verify",
    "--extended-regexp", "--files-with-matches", "--fixed-strings", "--ignore-case", "--line-number",
    "-E", "-F", "-I", "-i", "-l", "-p", "-s", "-w",
}
GIT_VALUE_FLAG = re.compile(r"--(?:format|pretty|max-count|unified|since|until|author|diff-filter)=.*")
GIT_SHORT_FLAG = re.compile(r"-(?:n[0-9]*|U[0-9]+|L[0-9]*(?:,[0-9+-]*)?|[0-9]+)")


def is_single_command(command):
    """Reject anything the shell would expand, chain, or redirect."""
    if not command.strip() or any(character in command for character in "\n\r\0"):
        return False
    quote = None
    for character in command:
        if quote == "'":
            if character == "'":
                quote = None
        elif quote == '"':
            if character in '$`\\':
                return False
            if character == '"':
                quote = None
        elif character in "'\"":
            quote = character
        elif character in SHELL_SYNTAX:
            return False
    return quote is None


def parse_flags(arguments, flags):
    """Split arguments into (flag, value) pairs and positionals. Unlisted flags return None."""
    options = []
    positionals = []
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        index += 1
        if not argument.startswith("-"):
            positionals.append(argument)
            continue
        name, separator, value = argument.partition("=")
        if name not in flags:
            return None
        if flags[name] and not separator:
            if index >= len(arguments):
                return None
            value = arguments[index]
            index += 1
        elif not flags[name] and separator:
            return None
        options.append((name, value))
    return options, positionals


def is_allowed_api(arguments):
    parsed = parse_flags(arguments, GH_API_FLAGS)
    if parsed is None:
        return False
    options, positionals = parsed
    if len(positionals) != 1 or not API_PATH.fullmatch(positionals[0]):
        return False
    decoded = unquote(positionals[0])
    if ".." in decoded or "%" in decoded:
        return False
    return all(
        API_ACCEPT.fullmatch(value) for name, value in options if name in ("-H", "--header")
    )


def is_allowed_gh(arguments):
    if arguments[:1] == ["api"]:
        return is_allowed_api(arguments[1:])
    rule = GH_COMMANDS.get(tuple(arguments[:2]))
    if rule is None:
        return False
    flags, target = rule
    parsed = parse_flags(arguments[2:], flags)
    if parsed is None:
        return False
    positionals = parsed[1]
    if target is None:
        return not positionals
    return len(positionals) <= 1 and all(target.fullmatch(value) for value in positionals)


def is_repository_argument(argument):
    # git diff silently switches to --no-index for paths outside the work tree.
    return not (
        argument.startswith(("/", "~"))
        or argument == ".."
        or argument.startswith("../")
        or "/../" in argument
        or argument.endswith("/..")
    )


def is_allowed_git(arguments):
    if arguments == ["branch", "--show-current"]:
        return True
    if not arguments or arguments[0] not in GIT_COMMANDS:
        return False
    after_separator = False
    for argument in arguments[1:]:
        if after_separator or not argument.startswith("-"):
            if not is_repository_argument(argument):
                return False
        elif argument == "--":
            after_separator = True
        elif not (
            argument in GIT_FLAGS
            or GIT_VALUE_FLAG.fullmatch(argument)
            or GIT_SHORT_FLAG.fullmatch(argument)
        ):
            return False
    return True


def is_allowed(payload):
    if not isinstance(payload, dict) or payload.get("tool_name") != "Bash":
        return False
    tool_input = payload.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str) or not is_single_command(command):
        return False
    tokens = shlex.split(command)
    if not tokens:
        return False
    if tokens[0] == "git":
        return is_allowed_git(tokens[1:])
    if tokens[0] == "gh":
        return is_allowed_gh(tokens[1:])
    return False


def main():
    try:
        allowed = is_allowed(json.loads(sys.stdin.buffer.read()))
    except Exception:  # Fail closed: a guard that cannot decide must not allow the command.
        allowed = False
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow" if allowed else "deny",
            "permissionDecisionReason": ALLOW_REASON if allowed else DENY_REASON,
        },
    }))


if __name__ == "__main__":
    main()
