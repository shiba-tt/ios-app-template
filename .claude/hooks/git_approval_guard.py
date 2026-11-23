#!/usr/bin/env python3
"""PreToolUse hook: force a user prompt for Git and GitHub commands that are not read-only.

Permission rules match command prefixes, so forms such as `git -C . push`, `gh -R o/r pr merge`, or
`sh -c 'git push'` miss the ask rules, and auto mode may then approve them. This hook tokenizes the
command and prompts unless each git or gh invocation is on a read-only list. It reduces accidental
bypasses but is not a security boundary against arbitrary code execution.
"""

import json
import os
import re
import shlex
import sys


REASON = "Git / GitHub の状態を変更する可能性がある操作です。実行内容を確認して承認してください。"
UNDECIDABLE_REASON = "コマンドを解析できなかったため、実行内容の確認が必要です。"

OPERATORS = ";&|()<>"
MAX_NESTING = 4
SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "eval"}
ASSIGNMENT = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)=")
SHELL_TEXT = re.compile(r"[\s$;&|]")
JQ_ENVIRONMENT = re.compile(r"\benv\b|\$ENV")
JQ_SHORT_OPTION = re.compile(r"-[A-Za-z]*q(.*)", re.S)

GIT_READ_ONLY = {
    "blame", "check-ignore", "describe", "diff", "for-each-ref", "grep", "log", "ls-files", "ls-tree",
    "merge-base", "rev-list", "rev-parse", "shortlog", "show", "show-ref", "status",
}
GIT_MUTATIONS = {
    "add", "am", "apply", "checkout", "cherry-pick", "clean", "commit", "config", "fetch", "filter-branch",
    "merge", "pull", "push", "rebase", "reset", "restore", "revert", "rm", "stash", "switch", "tag",
    "update-ref",
}
# Git accepts abbreviated long options, so these are prefixes of --output, --ext-diff, and
# --open-files-in-pager. -O is the short form of the last one.
GIT_UNSAFE_OPTIONS = ("--ou", "--ext", "--op", "-O")
GIT_SAFE_GLOBAL_OPTIONS = {"--no-pager", "-P", "--no-optional-locks"}
GIT_VALUE_GLOBAL_OPTIONS = {"-C", "--git-dir", "--work-tree", "--namespace", "--super-prefix", "--attr-source"}
GIT_BRANCH_READ_OPTIONS = {"--show-current", "--list", "-l", "-a", "--all", "-r", "--remotes", "-v", "-vv", "--verbose"}

GH_READ_ONLY = {
    ("auth", "status"), ("issue", "list"), ("issue", "view"), ("pr", "checks"), ("pr", "diff"), ("pr", "list"),
    ("pr", "status"), ("pr", "view"), ("repo", "view"), ("run", "list"), ("run", "view"), ("run", "watch"),
    ("workflow", "list"), ("workflow", "view"),
}
GH_GROUPS = {
    "alias", "api", "auth", "extension", "issue", "pr", "release", "repo", "ruleset", "run", "secret",
    "variable", "workflow",
}
# Each option maps to whether it consumes a value. Anything else may change the request method.
GH_API_READ_OPTIONS = {
    "-H": True, "--header": True, "--jq": True, "-q": True, "-t": True, "--template": True, "--cache": True,
    "-p": True, "--preview": True, "--paginate": False, "--slurp": False, "-i": False, "--include": False,
    "--silent": False,
}


def git_is_read_only(subcommand, arguments):
    if subcommand == "branch":
        return all(argument in GIT_BRANCH_READ_OPTIONS for argument in arguments)
    if subcommand == "remote":
        return arguments in ([], ["-v"], ["--verbose"]) or (len(arguments) == 2 and arguments[0] == "get-url")
    if subcommand not in GIT_READ_ONLY:
        return False
    return not any(argument.startswith(GIT_UNSAFE_OPTIONS) for argument in arguments)


def git_requires_approval(arguments, at_command_position):
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument == "-c" or argument.startswith("--config-env"):
            return True  # Inline config can define aliases or commands that run in place of the subcommand.
        if argument in GIT_VALUE_GLOBAL_OPTIONS:
            if at_command_position and argument != "-C":
                return True
            index += 2
        elif argument in GIT_SAFE_GLOBAL_OPTIONS:
            index += 1
        elif argument.startswith("-"):
            if at_command_position:
                return True
            index += 1
        else:
            break
    if index >= len(arguments):
        return False
    subcommand, rest = arguments[index], arguments[index + 1:]
    if at_command_position:
        return not git_is_read_only(subcommand, rest)
    return subcommand in GIT_MUTATIONS


def jq_reads_environment(arguments):
    for index, argument in enumerate(arguments):
        following = arguments[index + 1] if index + 1 < len(arguments) else ""
        short_option = JQ_SHORT_OPTION.fullmatch(argument)
        if argument == "--jq":
            expression = following
        elif argument.startswith("--jq="):
            expression = argument[len("--jq="):]
        elif short_option:
            expression = short_option[1] or following
        else:
            continue
        if JQ_ENVIRONMENT.search(expression):
            return True
    return False


def gh_api_is_read_only(arguments):
    positionals = 0
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        index += 1
        if not argument.startswith("-"):
            positionals += 1
            continue
        name, separator, value = argument.partition("=")
        if name not in GH_API_READ_OPTIONS:
            return False
        if GH_API_READ_OPTIONS[name] and not separator:
            if index >= len(arguments):
                return False
            value = arguments[index]
            index += 1
        elif not GH_API_READ_OPTIONS[name] and separator:
            return False
        if name in ("-H", "--header") and not value.lower().startswith("accept:"):
            return False
    return positionals == 1


def gh_requires_approval(arguments, at_command_position):
    if jq_reads_environment(arguments):
        return True
    words = []
    index = 0
    while index < len(arguments) and len(words) < 2:
        argument = arguments[index]
        index += 1
        if argument in ("-R", "--repo"):
            index += 1
        elif argument.startswith(("-R", "--repo=")):
            continue
        elif argument.startswith("-"):
            if at_command_position:
                return True
        elif not words and argument == "api":
            return not gh_api_is_read_only(arguments[index:])
        else:
            words.append(argument)
    if not words or tuple(words) in GH_READ_ONLY:
        return False
    return at_command_position or words[0] in GH_GROUPS


def segment_requires_approval(words, depth):
    start = 0
    while start < len(words):
        assignment = ASSIGNMENT.match(words[start])
        if assignment is None:
            break
        if assignment[1].startswith("GIT_"):
            return True  # Git reads commands and config from its environment variables.
        start += 1
    # A command name that needs expansion cannot be identified before it runs.
    if start < len(words) and "$" in words[start]:
        return True

    has_shell = False
    for position in range(start, len(words)):
        name = os.path.basename(words[position])
        rest = words[position + 1:]
        at_command_position = position == start
        has_shell = has_shell or name in SHELLS
        if name == "git" and git_requires_approval(rest, at_command_position):
            return True
        if name == "gh" and gh_requires_approval(rest, at_command_position):
            return True
        if name.startswith("git-") and (at_command_position or name[len("git-"):] in GIT_MUTATIONS):
            return True

    for word in words:
        if "$(" in word or " ; " in word or (has_shell and SHELL_TEXT.search(word)):
            if requires_approval(word, depth + 1):
                return True
    return False


def requires_approval(command, depth=0):
    if depth > MAX_NESTING:
        return True
    # Line continuations join words. Backticks and line breaks start another command.
    text = command.replace("\\\n", "")
    for separator in ("`", "\n", "\r"):
        text = text.replace(separator, " ; ")
    lexer = shlex.shlex(text, posix=True, punctuation_chars=OPERATORS)
    lexer.whitespace_split = True
    lexer.commenters = ""
    words = []
    for token in lexer:
        if token and set(token) <= set(OPERATORS):
            if segment_requires_approval(words, depth):
                return True
            words = []
        else:
            words.append(token)
    return segment_requires_approval(words, depth)


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
