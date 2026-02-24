#!/usr/bin/python3

import subprocess
import sys
from os.path import basename

CMD = basename(sys.argv.pop(0))
DUMMY_CMD = f"dummy_{CMD}"


def log(level: str, msg: str) -> None:
    subprocess.run(
        ["/usr/bin/logger", "--tag", DUMMY_CMD, "--priority", level, msg],
    )


def a_install() -> None:
    log("warn", f"{DUMMY_CMD} does nothing (args: {', '.join(sys.argv)})")


def udpkg() -> None:
    if len(sys.argv) != 1:
        log("warn", "called with more than one arg")
    if len(sys.argv) == 1:
        arg = sys.argv[0]
        if arg == "--print-os":
            print("linux")
        elif arg == "--print-architecture":
            subprocess.run(["/usr/bin/dpkg", arg])
        else:
            log("err", f"unknown arg '{arg}'")
    else:
        log("err", "called with more than one arg - not sure what to do...")


def main() -> None:
    log("info", f"command called: {CMD} {' '.join(sys.argv)}")
    if CMD in ["apt-install", "anna-install"]:
        a_install()
    elif CMD == "udpkg":
        udpkg()
    else:  # this shouldn't ever happen - but just in case...
        log("err", f"Unknown dummy app: '{CMD}'")


if __name__ == "__main__":
    main()
