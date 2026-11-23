#!/usr/bin/env python3
"""Print an xcodebuild destination for an available Simulator on one exact iOS runtime."""

import argparse
import json
import re
import subprocess
import sys


RUNTIME_PREFIX = "com.apple.CoreSimulator.SimRuntime.iOS-"
DEVICE_TYPE_PREFIX = "com.apple.CoreSimulator.SimDeviceType."
FAMILIES = {"iphone": "iPhone-", "ipad": "iPad-"}
DEFAULT_PREFERRED = {
    "iphone": ("iPhone 18 Pro", "iPhone 17"),
    "ipad": ("iPad Air 11-inch (M4)", "iPad (A16)"),
}


class SelectionError(Exception):
    pass


def simctl_list(*arguments):
    try:
        result = subprocess.run(
            ["xcrun", "simctl", "list", "--json", *arguments],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        return json.loads(result.stdout)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        raise SelectionError(f"could not read Simulator data: {error}") from error


def select_device(runtimes, devices, version, family, preferred):
    identifier = RUNTIME_PREFIX + version.replace(".", "-")
    matching = [
        runtime for runtime in runtimes
        if runtime.get("identifier") == identifier and runtime.get("isAvailable")
    ]
    if not matching:
        installed = ", ".join(
            sorted(
                f"{runtime.get('name')} [{runtime.get('identifier', '').rsplit('.', 1)[-1]}]"
                for runtime in runtimes
                if runtime.get("isAvailable")
            )
        ) or "none"
        raise SelectionError(f"iOS {version} runtime is not available. Installed: {installed}")

    type_prefix = DEVICE_TYPE_PREFIX + FAMILIES[family]
    candidates = sorted(
        (
            device for device in devices.get(identifier, [])
            if device.get("isAvailable", True)
            and device.get("deviceTypeIdentifier", "").startswith(type_prefix)
        ),
        key=lambda device: (device["name"], device["udid"]),
    )
    if not candidates:
        raise SelectionError(f"iOS {version} runtime has no available {family} Simulator.")

    for name in preferred:
        for device in candidates:
            if device["name"] == name:
                return matching[0], device
    return matching[0], candidates[0]


def arguments():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--runtime", required=True, help="Exact iOS runtime as major.minor, e.g. 27.2")
    parser.add_argument("--family", choices=FAMILIES, default="iphone", help="Device family")
    parser.add_argument(
        "--prefer",
        action="append",
        metavar="NAME",
        help="Preferred device name. Repeat in priority order.",
    )
    args = parser.parse_args()
    if not re.fullmatch(r"[1-9][0-9]*\.[0-9]+", args.runtime):
        parser.error("--runtime must use major.minor, e.g. 27.2.")
    return args


def main():
    args = arguments()
    preferred = args.prefer or DEFAULT_PREFERRED[args.family]
    try:
        runtimes = simctl_list("runtimes")["runtimes"]
        devices = simctl_list("devices", "available")["devices"]
        runtime, device = select_device(runtimes, devices, args.runtime, args.family, preferred)
    except (KeyError, SelectionError) as error:
        sys.exit(f"select_simulator: {error}")

    print(
        f"Selected Simulator: {device['name']} | "
        f"runtime iOS {runtime.get('version')} ({runtime.get('buildversion')}) | "
        f"UDID {device['udid']}",
        file=sys.stderr,
    )
    print(f"platform=iOS Simulator,id={device['udid']}")


if __name__ == "__main__":
    main()
