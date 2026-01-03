#!/usr/bin/python3

import os
import string
import sys
from os.path import basename, dirname, join


def warning(msg: str) -> None:
    print(f"WARNING: {msg}", file=sys.stderr)


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
    log_line = '/usr/share/di-live/log_info "$0" "$@"'
    funcs = find_functions(file)
    new_lines = []
    with open(file) as fob:
        for line in fob.readlines():
            line_start, *line_end_list = line.rstrip().split("#")
            comment = "#".join(line_end_list)
            if comment:
                comment = f"#{comment}"
            if line in funcs:
                if line_start.strip().endswith("{"):
                    line = f"{line_start}{comment}\n       {log_line}\n"
                elif line_start.endswith("}"):
                    line = f"{line_start[:-1]} {log_line};}}#{comment}\n"
            new_lines.append(line)
    try:
        with open(file, "w") as fob:
            fob.writelines(new_lines)
    except PermissionError as e:
        warning(f"{e}")


def main() -> None:
    updated: dict[str, list[str]] = {}
    skipped: dict[str, list[str]] = {}
    for bin_file in find_bin_files("rootfs"):
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


if __name__ == "__main__":
    main()
