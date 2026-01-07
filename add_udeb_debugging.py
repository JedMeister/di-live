#!/usr/bin/python3

"""Generate modified udeb package contents to ease debugging.

- Use bash instead of generic shell (i.e. '/bin/sh' -> '/bin/bash'.
- Inject logging into shared shell functions (i.e. files sourced by udeb
  scripts).

This script is called by the debian/rules file at package build time and
resulting updated files will be contained within the 'di-live-di-debug'
package ('di-live' package includes unmodified source).

Important:
This script makes a number of assumptions (documented in comments & doc
strings). To reduce the associated risks of failure this script should be
manually run whenever udeb packages are updated and the diff manually
inspected.
"""

import argparse
import os
import re
import shutil
import string
import sys
from os.path import basename, dirname, exists, join
from typing import NoReturn

ROOTFS = "rootfs"
DEBUG_DIR = "debug"
DEBUG_ROOTFS = join(DEBUG_DIR, ROOTFS)
LOG_SCRIPT = "/usr/share/di-live/debug/log_info.sh"
LOG_LINE = f'{LOG_SCRIPT} "$0" "${{FUNCNAME[0]}}" "$*"'


def heading_1(msg: str) -> None:
    msg = f"### {msg} ###"
    border = "#" * len(msg)
    print(f"\n{border}\n{msg}\n{border}")


def heading_2(msg: str) -> None:
    underline = "-" * len(msg)
    print(f"{msg}\n{underline}")


def info(msg: str, indent: int = 0) -> None:
    intent_text = " " * indent
    print(f"{intent_text}- {msg}")


def warning(msg: str) -> None:
    print(f"WARNING: {msg}", file=sys.stderr)


def fatal(msg: str) -> NoReturn:
    print(f"FATAL: {msg}", file=sys.stderr)
    sys.exit(1)


def setup(
    source: str = ROOTFS,
    destination: str = DEBUG_ROOTFS,
    force: bool = False,
    update_source: bool = False,
) -> None:
    if source == destination and not update_source:
        fatal(
            f"Source ('{source}') & destination ('{destination}') dirs are"
            f" the same - use '--update-source' to override",
        )
    elif exists(destination) and not (force or update_source):
        fatal(
            f"Destination path ('{destination}') exists - rerun with '--force'"
            " to overwrite."
        )
    if exists(destination) and not update_source:
        shutil.rmtree(destination)
    if source != destination:
        shutil.copytree(source, destination)


def is_text_file(path: str) -> bool:
    """Assume file is text if it can be opended in text mode."""
    try:
        with open(path) as fob:
            fob.read()
        return True
    except UnicodeDecodeError:
        return False


def find_all_files(search_path: str) -> list[str]:
    """Find all files within file tree and return list of relative paths.

    All results will include search_path as the first element.
    """
    file_paths = []
    for base, _dirs, files in os.walk(search_path):
        for file in files:
            file_paths.append(join(base, file))
    return file_paths


def find_filename(search_root: str, file_name: str) -> list[str]:
    """Search for file_name within search_root.

    Returns a list of all files matching file_name within search_root; an empty
    list if no matches found.

    Each result will be the full path relative to search_root - including
    search_root, e.g. ['search_root/path/to/file_name', ...]

    A path prefix may be included in file_name - e.g.
    'path/to/file_name' - although any leading '/' will be stripped if
    included.
    """
    found_files = []
    path_prefix = (
        "" if "/" not in file_name else dirname(file_name).lstrip("/")
    )
    file_path = join(path_prefix, basename(file_name))
    for file in find_all_files(search_root):
        if file.endswith(file_path):
            found_files.append(file)
    return found_files


def replace_bin_sh(root_path: str) -> list[str]:
    """Replace /bin/sh with /bin/bash in all text files within path."""
    updated = []
    all_files_found = find_all_files(root_path)
    heading_2(f"{len(all_files_found)} total files found")
    for file in all_files_found:
        if not is_text_file(file):
            continue
        with open(file) as fob:
            file_contents = fob.read()
            if "/bin/sh" not in file_contents:
                continue
            updated.append(file)
            file_contents = file_contents.replace("/bin/sh", "/bin/bash")
        with open(file, "w") as fob:
            fob.write(file_contents)
    return updated


def find_sourced_files(file: str) -> list[str] | None:
    """Check text file for lines which source other files.

    Returns list of file names sourced within file. Returns empty list if
    file does not source any files. Returns None if file is not a text file.

    Comments (strings with '#' prefix) are ignored, but because of this
    assumption, strings containing '#' will be incorrectly identified as
    comments.

    Also assumes that "source FILE_PATH" occurs on a line with no other code.
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
    injected command will have the same indent as the following line (the first
    function line prior to injection. In the case of single line functions, the
    injected command will be inserted between the '{' and the rest of the
    function, with the required semi-colon separator appended.

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
          results may occur. It is assumed that if any updates under those
          circumstance do occur they will cause explicit error.

    """

    def inject_inline(line: str) -> str:
        """Inject string into single line function."""
        start, end = line.split("{", 1)
        return f"{start}{{ {inject_command};{end}"

    funcname = r"[a-zA-Z_][a-zA-Z0-9_]*"
    func_regex = (rf"{funcname}[ \t]*\(\)", rf"function[ \t]+{funcname}")
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
                            indent_previous = True
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


def add_logging_to_files(
        root_path: str, log_line: str = LOG_LINE
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Add logging to functions in files sourced by another."""

    # 'updated sourced file' : list['files_that_sourced', ...]
    updated: dict[str, list[str]] = {}

    # 'untouched sourced file' : list['files_that_sourced', ...]
    skipped: dict[str, list[str]] = {}

    def verify_path_depth(original_file: str, found_file: str) -> str | None:
        file_length = []
        for file in (original_file, found_file):
            file_length.append(len(file.lstrip("/").split("/")))
        # sourced_file will have path prefix of 'rootfs/udeb_name' hence '- 2'
        if file_length[0] == file_length[1] - 2:
            return found_file
        return None

    for file in find_all_files(root_path):
        sourced_files = find_sourced_files(file)
        if sourced_files is None:
            continue
        for sourced_file in set(sourced_files):
            found_files = find_filename(root_path, sourced_file)
            if not found_files:
                if sourced_file in skipped.keys():
                    skipped[sourced_file].append(file)
                else:
                    skipped[sourced_file] = [file]
                continue
            elif len(found_files) > 1:
                warning(
                    f"Search for '{sourced_file}' returned multiple results"
                    f" ({', '.join(found_files)}); using first match"
                )
            found_sourced_file = found_files[0]
            if not verify_path_depth(sourced_file, found_sourced_file):
                warning(
                    f"Found sourced file '{found_sourced_file}' does not match"
                    " expected file"
                )
            if found_sourced_file in updated.keys():
                updated[found_sourced_file].append(file)
            else:
                inject_in_funcs(found_sourced_file, log_line)
                updated[found_sourced_file] = [file]
    return updated, skipped


def update_shell(root_path: str) -> None:
    """Function that runs replace_bin_sh() and echos results."""
    heading_1("Replacing /bin/sh with /bin/bash complete")
    updated_files = replace_bin_sh(root_path)
    heading_2(f"Complete - {len(updated_files)} files updated:")
    for file in updated_files:
        info(file, indent=2)


def add_logging(root_path: str, log_line: str = LOG_LINE) -> None:
    """Function that runs add_logging_to_files() and echos results."""
    heading_1("Injecting logging command")
    updated, skipped = add_logging_to_files(root_path, log_line)
    heading_2(f"{len(updated)} files updated:")
    for updated_file in updated.keys():
        info(f"'{updated_file}' sourced by:")
        for bin_file in updated[updated_file]:
            info(f"{bin_file}", indent=4)
    heading_2(f"{len(skipped)} sourced files not updated:")
    for skipped_file in skipped.keys():
        if basename(skipped_file).startswith("$"):
            info(f"variable '{skipped_file}' sourced by:")
        else:
            info(f"'{skipped_file}' sourced by:")
        for bin_file in skipped[skipped_file]:
            info(f"{bin_file}", indent=4)


def main() -> None:
    parser = argparse.ArgumentParser(
        epilog="One of '--all-updates', '--bash-update', '--add-logging' is"
        " required.",
    )
    parser.add_argument(
        "-s",
        "--source",
        default=ROOTFS,
        help=f"source directory - default: {ROOTFS}/"
    )
    parser.add_argument(
        "-d",
        "--destination",
        default=DEBUG_ROOTFS,
        help=f"destination directory - default: {DEBUG_ROOTFS}/"
    )
    parser.add_argument(
        "-b",
        "--bash-update",
        action="store_true",
        help="replace '/bin/sh' with '/bin/bash' in files found in /sbin &"
        " /bin subdirs",
    )
    parser.add_argument(
        "-l",
        "--add-logging",
        action="store_true",
        help="add logging to all functions in all sourced files",
    )
    parser.add_argument(
        "-a",
        "--all-updates",
        action="store_true",
        help="apply all updates; same as '--bash-update --add-logging ",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="force overwrite of existing destination",
    )
    parser.add_argument(
        "-u",
        "--update-source",
        action="store_true",
        help="apply changes to source path (set destination = source; implies"
        " --force)",
    )
    args = parser.parse_args()

    if not args.bash_update and not args.add_logging and not args.all_updates:
        print(
            "ERROR: one of '-a|--all-updates', '-b|--bash-update' or"
            " '-l|--add-logging' is required",
            file=sys.stderr,
        )
        parser.print_usage()
        sys.exit(1)

    if args.all_updates:
        args.bash_update = True
        args.add_logging = True

    if args.update_source:
        args.destination = args.source

    setup(
        source=args.source,
        destination=args.destination,
        force=args.force,
        update_source=args.update_source,
    )

    if args.bash_update:
        update_shell(root_path=args.destination)

    if args.add_logging:
        add_logging(root_path=args.destination)


if __name__ == "__main__":
    main()
