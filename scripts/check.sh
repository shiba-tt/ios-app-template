#!/usr/bin/env bash
set -euo pipefail

if [[ ${1:-} == --help ]]; then
  printf '%s\n' "Usage: $0 'platform=iOS Simulator,id=<UDID>'"
  exit 0
fi
if [[ $# -ne 1 || $1 != 'platform=iOS Simulator,'* ]]; then
  printf '%s\n' "Usage: $0 'platform=iOS Simulator,id=<UDID>'" \
    "Run 'xcrun simctl list devices booted' or 'xcrun simctl list devices available' for a UDID." >&2
  exit 2
fi

cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
if [[ -d .bootstrap-in-progress ]]; then
  printf '%s\n' 'check: bootstrap is in progress or was interrupted. See README.md.' >&2
  exit 1
fi

for tool in xcodebuild xcrun xcodegen swiftlint; do
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

xcrun swift-format lint --strict --recursive App Tests
swiftlint lint --strict
xcodegen generate
build_args=(
  -project "$project_name.xcodeproj"
  -scheme "$project_name"
  -destination "$1"
  -derivedDataPath DerivedData
)
xcodebuild "${build_args[@]}" build
xcodebuild "${build_args[@]}" test
