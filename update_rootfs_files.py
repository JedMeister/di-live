#!/usr/bin/python3

import argparse
import os
import re
import string
import sys
from os.path import basename, dirname, join

DEBUG_DIR = "_debug_share"
DEBUG_ROOTFS = join(DEBUG_DIR, "rootfs")
LOG_SCRIPT = "/usr/share/di-live/debug/log_info.sh"
LOG_LINE = f'{LOG_SCRIPT} "$0" "${{FUNCNAME[0]}}" "$*"'


def warning(msg: str) -> None:
    print(f"WARNING: {msg}", file=sys.stderr)


def is_text_file(path: str) -> bool:
    """Assume file is text if it can be opended in text mode."""
    try:
        open(path).close()
        return True
    except UnicodeDecodeError:
        return False


def replace_bin_sh_file(file: str) -> None:
    """Replace any use of /bin/sh with /bin/bash in a file."""
    try:
        updated_lines = []
        with open(file) as fob:
            for line in fob.readlines():
                updated_lines.append(line.replace("/bin/sh", "/bin/bash"))
        with open(file, "w") as fob:
            fob.writelines(updated_lines)
    except UnicodeDecodeError:
        # assume this means it's not a text file
        pass


def find_all_files(path: str) -> list[str]:
    """Find all files within file tree and return list of relative paths"""
    file_paths = []
    for base, _dirs, files in os.walk(path):
        for file in files:
            file_paths.append(join(base, file))
    return file_paths


def find_file(search_root: str, filename: str) -> str | None:
    """Return relative path to filename if found.

    Filename may include a subpath prefix (e.g. '/path_prefix/file').

    First match will be returned.
    """
    path_prefix = "" if "/" not in filename else dirname(filename).lstrip("/")
    filename = basename(filename)
    for file in find_all_files(search_root):
        if (
            file.startswith(path_prefix)
            and file == join(path_prefix, filename)
        ):
            return file
    return None


def find_bin_files(base_dir: str) -> list[str]:
    bin_files = []
    for file in find_all_files(base_dir):
        if "/bin/" in file or "/sbin/" in file:
            if not (
                dirname(file).endswith("/bin")
                or dirname(file).endswith("/sbin")
            ):
                warning(
                    "path includes bin dir but file not directly in bin dir"
                    f" ('{file}')"
                )
            bin_files.append(file)
    return bin_files


def find_sourced_files(file: str) -> list[str] | None:
    """Check text file for lines which source other files.

    Returns list of file names sourced within file. Returns empty list if
    file does not source any files. Returns None if file is not a text file.
    """
    if not is_text_file(file):
        return None
    sourced = []
    with open(file) as fob:
        for line in map(str.strip, fob.readlines()):
            # ensure comments are ignored
            line = line.split("#")[0]
            if len(line.split()) != 2:
                continue
            for source in (".", "source"):
                if (
                    line.startswith(source)
                    # relevant source command followed by whitespace char
                    and line[len(source)] in string.whitespace
                ):
                    sourced.append(line.split()[1])
    return sourced


def inject_in_funcs(file: str, inject_command: str) -> None:
    """Inject command into all shell functions found within a file.

    Assuming a multi-line function, the command will be injected into a new
    line at the start of the function - i.e. the line after '{'. Where possible
    the injected will have the same indent as the following line (the first
    function line prior to injection. in the case of single line functions, the
    injected command will be inserted between the '{' and the rest of the
    function; with the required trailing demi-colon appended.

    Assumptions:
        - a function starts with one of:
            - 'FUNCNAME()<whitespace>{'
                - where <whitespace> may be a newline
            - 'FUNCNAME<whitespace>()<whitespace>{'
                - where 1st <whitespace> can NOT be newline but 2nd may be
            - 'function<whitespace>FUNCNAME<whitespace>{'
                - where 1st <whitespace> can NOT be newline but 2nd may be
        - Comments (i.e. text with a '#' prefix) are not considered. So the
          command will still be injected into a function that is commented out
        - '{' and '}' are always assumed to be the start and end of a function,
          so if either of those are within comments or strings, unexpected
          results may occur.
    """

    def inject_inline(line: str) -> str:
        """Inject string into single line function."""
        start, end = line.split("{", 1)
        return f"{start}{{ {inject_command};{end}"

    funcname = r"[a-zA-Z_][a-zA-Z0-9_]*"
    func_regex = (rf"{funcname}[ \t]*()", rf"function[ \t]+{funcname}")
    with open(file) as fob:
        file_lines = []
        func_declared = False
        indent_previous = False
        for line in fob.readlines():
            if not func_declared:
                # search line for function definition
                for regex in func_regex:
                    if re.search(regex, line):
                        if "{" not in line:
                            # func declared but not opened so don't inject
                            # string yet but set relevant flags
                            func_declared = True
                            indent_previous = False
                        elif "{" in line and "}" in line:
                            # single line func so inject into existing line
                            line = inject_inline(line)
                            # reset flags to find next function
                            func_declared = False
                            indent_previous = False
                        else:
                            # func declared and opened but not on single line
                            # so append the current 'line' now replace with
                            # the string to inject
                            file_lines.append(line)
                            line = f"{inject_command}\n"
                            # set appropriate flags for next iteration
                            func_declared = True
                        # it shouldn't matter if this "function finding" loop
                        # runs again, but also shouldn't be needed
                        break
            else:
                # func_declared = True
                if indent_previous:
                    if "}" in line:
                        # this seems an unlikely possibility - but handle it
                        # anyway...
                        indent = "    "
                        # reset flag to search for next func
                        func_declared = False
                    else:
                        # find the indent of this line and insert into previous
                        # (injected) line
                        found_indent = re.search(r"^[ \t]*", line)
                        if found_indent is not None:  # it won't be ...
                            indent = found_indent.group(0)
                    if indent:
                        file_lines[-1] = f"{indent}{file_lines[-1]}"
                    # don't indent any other lines until next function
                    indent_previous = False
                elif "}" in line:
                    # end of function so reset flag to search for next func
                    func_declared = False
            file_lines.append(line)
    with open(file, "w") as fob:
        fob.writelines(file_lines)


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
                    inject_in_funcs(found_file, LOG_LINE)
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
        print("Error: at least one arg required\n", file=sys.stderr)
        parser.print_usage()
    if args.bash_update:
        print("replacing /bin/sh with /bin/bash")
        replace_bin_sh_file("rootfs")
    if args.add_logging:
        print("adding logging")
        add_logging("rootfs")


if __name__ == "__main__":
    main()
