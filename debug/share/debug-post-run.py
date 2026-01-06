#!/usr/bin/python3

import shutil
import subprocess
from os.path import exists


def git_cmd(*args: str) -> bool:
    return bool(
        subprocess.run(["/usr/bin/git", *args], cwd="/var/log").returncode
    )


def git_setup() -> None:
    if exists("/var/log/.git"):
        return
    git_cmd("init")
    if not git_cmd("config", "user.name"):
        git_cmd("config", "user.name", "di-live debugging")
    if not git_cmd("config", "user.email"):
        git_cmd("config", "user.email", "debug@di-live.local")
    shutil.copy2("/usr/share/di-live/log_gitignore", "/var/log/")


def rotate_and_commit() -> None:
    subprocess.run(
        ["/usr/sbin/logrotate", "--force", "/usr/share/di-live/rotate-log"]
    )
    git_cmd("add", ".")
    git_cmd("commit", "-m", "di-live debug post run commit")


if __name__ == "__main__":
    git_setup()
    rotate_and_commit()
