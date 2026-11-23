#!/usr/bin/env bash
set -euo pipefail

usage() {
  printf '%s\n' \
    "Usage: $0 [options] 'platform=iOS Simulator,id=<UDID>'" \
    "       $0 --stage quality|generate" \
    '' \
    'Options:' \
    '  --stage all|quality|generate|build|test  Stage to run (default: all)' \
    '  --tests all|unit|ui                      Test targets to run (default: all)' \
    '  --ci-output DIR                          Disable code signing and save logs and results in DIR' \
    '  --help                                   Show this help'
}

usage_error() {
  usage >&2
  printf '%s\n' \
    "Run 'xcrun simctl list devices booted' or 'xcrun simctl list devices available' for a UDID." >&2
  exit 2
}

stage=all
tests=all
ci_output=''
destination=''
while [[ $# -gt 0 ]]; do
  case $1 in
    --help)
      usage
      exit 0
      ;;
    --stage | --tests | --ci-output)
      [[ $# -ge 2 ]] || usage_error
      case $1 in
        --stage) stage=$2 ;;
        --tests) tests=$2 ;;
        --ci-output) ci_output=$2 ;;
      esac
      shift 2
      ;;
    *)
      [[ -z $destination && $1 == 'platform=iOS Simulator,'* ]] || usage_error
      destination=$1
      shift
      ;;
  esac
done

case $stage in
  all | build | test) [[ -n $destination ]] || usage_error ;;
  quality | generate) [[ -z $destination ]] || usage_error ;;
  *) usage_error ;;
esac
case $tests in
  all | unit | ui) ;;
  *) usage_error ;;
esac

if [[ -n $ci_output ]]; then
  mkdir -p -- "$ci_output"
  ci_output="$(cd -- "$ci_output" && pwd)"
fi

cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
if [[ -d .bootstrap-in-progress ]]; then
  printf '%s\n' 'check: bootstrap is in progress or was interrupted. See README.md.' >&2
  exit 1
fi

for tool in xcodebuild xcrun xcodegen swiftlint python3; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    printf 'check: %s is missing. Select Xcode and run with mise exec --.\n' "$tool" >&2
    exit 1
  fi
done

expected_xcode="$(cat .xcode-version)"
xcode_version="$(xcodebuild -version)"
if [[ ${xcode_version%%$'\n'*} != "Xcode $expected_xcode" ]]; then
  printf 'check: expected Xcode %s. Selected version:\n%s\n' "$expected_xcode" "$xcode_version" >&2
  exit 1
fi

project_name="$(sed -n 's/^name: "\([A-Za-z][A-Za-z0-9]*\)"$/\1/p' project.yml)"
if [[ -z $project_name ]]; then
  printf '%s\n' 'check: expected a quoted app name at the top level of project.yml.' >&2
  exit 1
fi

runs_stage() {
  [[ $stage == all || $stage == "$1" ]]
}

verify_project() {
  local scheme_file="$project_name.xcodeproj/xcshareddata/xcschemes/$project_name.xcscheme"
  local target
  xcodebuild -list -json -project "$project_name.xcodeproj" | python3 -c '
import json
import sys

name = sys.argv[1]
project = json.load(sys.stdin)["project"]
missing = [t for t in (name, f"{name}Tests", f"{name}UITests") if t not in project["targets"]]
if name not in project["schemes"]:
    missing.append(f"scheme {name}")
if missing:
    sys.exit("check: generated project is missing: " + ", ".join(missing))
' "$project_name"
  if [[ ! -f $scheme_file ]]; then
    printf 'check: shared scheme is missing: %s\n' "$scheme_file" >&2
    return 1
  fi
  for target in "${project_name}Tests" "${project_name}UITests"; do
    if ! grep -Fq "BlueprintName = \"$target\"" "$scheme_file"; then
      printf 'check: scheme %s does not include %s.\n' "$project_name" "$target" >&2
      return 1
    fi
  done
}

# Keep xcodebuild's exit status when CI mirrors its output to a diagnostics log.
run_xcodebuild() {
  local label=$1
  shift
  if [[ -z $ci_output ]]; then
    xcodebuild "${build_args[@]}" "$@"
  else
    xcodebuild "${build_args[@]}" CODE_SIGNING_ALLOWED=NO "$@" 2>&1 | tee "$ci_output/$label.log"
  fi
}

if runs_stage quality; then
  xcrun swift-format lint --strict --recursive App Tests
  swiftlint lint --strict
fi

if runs_stage generate; then
  xcodegen generate
  verify_project
fi

build_args=(
  -project "$project_name.xcodeproj"
  -scheme "$project_name"
  -destination "$destination"
  -derivedDataPath DerivedData
)

if runs_stage build; then
  run_xcodebuild build build
fi

if runs_stage test; then
  test_args=()
  case $tests in
    unit) test_args+=("-only-testing:${project_name}Tests") ;;
    ui) test_args+=("-only-testing:${project_name}UITests") ;;
  esac
  if [[ -n $ci_output ]]; then
    test_args+=(-resultBundlePath "$ci_output/test-$tests.xcresult")
  fi
  # The guarded expansion supports empty arrays under set -u in macOS's Bash 3.2.
  run_xcodebuild "test-$tests" ${test_args[@]+"${test_args[@]}"} test
fi
