#!/usr/bin/python3

import argparse
import os
import string
import sys
from os.path import basename, dirname, join

LOG_SCRIPT = "/usr/share/di-live/log_info.sh"
LOG_LINE = f'{LOG_SCRIPT} "$0" "${{FUNCNAME[0]}}" "$*"'

def warning(msg: str) -> None:
    print(f"WARNING: {msg}", file=sys.stderr)


def replace_bin_sh_file(file: str) -> None:
    """Replace any use of /bin/sh with /bin/bash in a file."""
    updated_lines = []
    with open(file) as fob:
        for line in fob.readlines():
            updated_lines.append(line.replace("/bin/sh", "/bin/bash"))
    with open(file, "w") as fob:
        fob.writelines(updated_lines)


def replace_bin_sh(path: str) -> None:
    """Replace use of /bin/sh with /bin/bash in all files found in path."""
    for base, _dirs, files in os.walk(path):
        for file in files:
            replace_bin_sh_file(join(base, file))


def find_file(search_root: str, filename: str) -> str | None:
    """Return relative path to filename if found.

    Filename may include a subpath prefix (e.g. '/path_prefix/file').

    First match will be returned.
    """
    path_prefix = "" if "/" not in filename else dirname(filename).lstrip("/")
    filename = basename(filename)
    for base_dir, _dirs, files in os.walk(search_root):
        if base_dir.endswith(path_prefix) and filename in files:
            return join(base_dir, filename)
    return None


def find_bin_files(base_dir: str) -> list[str]:
    bin_files = []
    for base, dirs, files in os.walk(base_dir):
        if basename(base).endswith("bin"):
            if dirs:
                warning(f"'{base}' contains dirs: {dirs}")
            bin_files.extend([join(base, x) for x in files])
    return bin_files


def find_sourced_files(file: str) -> list[str] | None:
    """Check text file for lines with source other files.

    If file can not be opended in text mode, None will be returned.
    """
    sourced = []
    try:
        with open(file) as fob:
            for line in map(str.strip, fob.readlines()):
                line = line.split("#")[0]
                if len(line.split()) != 2:
                    continue
                for source in (".", "source"):
                    if (
                        line.startswith(source)
                        and line[len(source)] in string.whitespace
                    ):
                        sourced.append(line.split()[1])
    except UnicodeDecodeError:
        # assume this means it's not a text file
        return None
    return sourced


def find_functions(file: str) -> list[str]:
    """Search shell file for functions.

    Assumes a function is a line that includes '{' and either:
        - starts with a string followed by '()' (without or without a
          whitespace separator); or
        - starts with the string 'function'

    Returns list of verbatim line including function
    """
    function_lines = []
    with open(file) as fob:
        for line in fob.readlines():
            original_line = line
            line = line.split("#")[0].strip()
            if "{" in line:
                likely_func = ["", ""]  # if really likely func, len == 1
                possible_func = line.split("{")[0].strip()
                if possible_func.endswith("()"):
                    likely_func = [possible_func.split("(")[0].strip()]
                elif possible_func.startswith("function"):
                    likely_func = possible_func.split()[1:]
                if len(likely_func) == 1:
                    function_lines.append(original_line)
    return function_lines


def insert_log_line_in_funcs(file: str) -> None:
    funcs = find_functions(file)
    new_lines = []
    with open(file) as fob:
        for line in fob.readlines():
            line_start, *line_end_list = line.rstrip().split("#")
            comment = "#".join(line_end_list)
            if comment:
                comment = f" #{comment}"
            if line in funcs:
                if line_start.strip().endswith("{"):
                    line = f"{line_start}{comment}\n       {LOG_LINE}\n"
                elif line_start.endswith("}"):
                    line = f"{line_start[:-1]} {LOG_LINE};}}{comment}\n"
            new_lines.append(line)
    try:
        with open(file, "w") as fob:
            fob.writelines(new_lines)
    except PermissionError as e:
        warning(f"{e}")


def add_logging(path: str) -> None:
    updated: dict[str, list[str]] = {}
    skipped: dict[str, list[str]] = {}
    for bin_file in find_bin_files(path):

        sourced_files = find_sourced_files(bin_file)
        if sourced_files is not None:
            for sourced_file in sourced_files:
                found_file = find_file("rootfs", sourced_file)
                if found_file and found_file in updated.keys():
                    updated[found_file].append(bin_file)
                elif found_file:
                    insert_log_line_in_funcs(found_file)
                    updated[found_file] = [bin_file]
                else:
                    if sourced_file in skipped.keys():
                        skipped[sourced_file].append(bin_file)
                    else:
                        skipped[sourced_file] = [bin_file]

    print("###########################")
    print("### Processing finished ###")
    print("###########################")
    print(f"{len(updated)} files updated:")
    for updated_file in updated.keys():
        print(f"- '{updated_file}' sourced by:")
        for bin_file in updated[updated_file]:
            print(f"    - {bin_file}")
    print(f"{len(skipped)} sourced files not updated:")
    for skipped_file in skipped.keys():
        if basename(skipped_file).startswith("$"):
            print(f"- variable '{skipped_file}' sourced by:")
        else:
            print(f"- '{skipped_file}' sourced by:")
        for bin_file in skipped[skipped_file]:
            print(f"    - {bin_file}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-b",
        "--bash-update",
        action="store_true",
        help="Replace '/bin/sh' with '/bin/bash' in all files in 'rootfs'",
    )
    parser.add_argument(
        "-a",
        "--add-logging",
        action="store_true",
        help="Add logging to all functions in all sourced files in 'rootfs'",
    )
    args = parser.parse_args()
    if not args.bash_update and not args.add_logging:
        print("No args used; nothing to do...")
    if args.bash_update:
        print("replacing /bin/sh with /bin/bash")
        replace_bin_sh("rootfs")
    if args.add_logging:
        print("adding logging")
        add_logging("rootfs")


if __name__ == "__main__":
    main()
