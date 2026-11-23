#!/usr/bin/env bash
# Print DEVELOPER_DIR for the Xcode pinned in .xcode-version. Never falls back to another Xcode.
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
applications_dir="${XCODE_APPLICATIONS_DIR:-/Applications}"

version_file="$(cat .xcode-version)"
if [[ ! $version_file =~ ^[0-9]+(\.[0-9]+){1,2}$ ]]; then
  printf '%s\n' 'select_xcode: .xcode-version must contain one version such as 27.2.' >&2
  exit 1
fi

developer_dir="$applications_dir/Xcode_$version_file.app/Contents/Developer"
if [[ ! -x $developer_dir/usr/bin/xcodebuild ]]; then
  printf 'select_xcode: Xcode %s is not installed at %s.\nInstalled Xcode apps:\n' \
    "$version_file" "$developer_dir" >&2
  find "$applications_dir" -maxdepth 1 -name 'Xcode*.app' -print 2>/dev/null | sort >&2
  exit 1
fi

reported="$(DEVELOPER_DIR="$developer_dir" "$developer_dir/usr/bin/xcodebuild" -version)"
if [[ ${reported%%$'\n'*} != "Xcode $version_file" ]]; then
  printf 'select_xcode: expected Xcode %s at %s, but found:\n%s\n' \
    "$version_file" "$developer_dir" "$reported" >&2
  exit 1
fi

printf '%s\n' "$reported" >&2
printf '%s\n' "$developer_dir"
