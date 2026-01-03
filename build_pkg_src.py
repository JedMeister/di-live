#!/usr/bin/python3

"""A dirty script to rebuild/update the di-live pkg source.

Uses apt to download the udeb binary packages that di-live requires and include
the relevant components.

Specific steps:
    - Add 'debian-installer.sources' file (if needed).
    - Read udeb names from 'udebs.txt'.
    - Download udeb binary packages with 'apt-get download <udebs>'.
    - Unpack udebs with 'dpkg-deb -R <udeb> rootfs/<udeb_name>'.
    - Remove files listed in 'blacklist.txt'.
    - Generate consolidated 'debian/di-live.templates' file from base.
      'di-live.templates' and contents of individual udeb 'templates' files;
      translations are stripped to minimise the size.
    - Write list of udebs and their respective versions (and arch) to
      'package_list.txt' - for quick reference.
"""

import os
import shutil
import subprocess
from os.path import exists, isfile, join, splitext

from debian.deb822 import Deb822

SOURCES_FILE = "debian-installer.sources"
TMP = "tmp"
ROOTFS = "rootfs"


def heading(msg: str) -> None:
    msg = f"### {msg} ###"
    border = "#" * len(msg)
    print(f"\n{border}\n{msg}\n{border}")


def info(msg: str) -> None:
    print(f"- {msg}")


def setup() -> None:
    """Clear working directories and prepare apt."""
    for dir in (TMP, ROOTFS):
        if exists(dir):
            shutil.rmtree(dir)
        os.makedirs(dir)
    etc_apt_sources = join("/etc/apt/sources.list.d", SOURCES_FILE)
    if not exists(etc_apt_sources):
        shutil.copy2(SOURCES_FILE, etc_apt_sources)
    subprocess.run(["apt-get", "update"], check=True)


def read_txt_file(path: str) -> list[str]:
    values_to_return = []
    with open(path) as fob:
        for line in fob:
            line = line.strip()
            if line and not line.startswith("#"):
                values_to_return.append(line.split("#")[0])
    return values_to_return


def download_and_unpack_udebs(udebs: list[str]) -> None:
    subprocess.run(["apt-get", "download", *udebs], cwd=TMP, check=True)
    package_list_lines = []
    for item in os.listdir(TMP):
        if len(item.split("_")) != 3:
            continue
        udeb_name, version, arch = splitext(item)[0].split("_")
        if udeb_name in udebs:
            subprocess.run(
                ["dpkg-deb", "-R", item, udeb_name], cwd=TMP, check=True
            )
            package_list_lines.append(f"{udeb_name}={version} # {arch}")
    with open("package_list.txt", "w") as fob:
        for line in sorted(package_list_lines):
            fob.write(f"{line}\n")


def get_template_paths(path: str = TMP) -> list[str]:
    templates = []
    for base_dir, _dirs, files in os.walk(path):
        if "templates" in files:
            templates.append(join(base_dir, "templates"))
    return sorted(templates)


def read_template(path: str) -> list[Deb822]:
    """Read template file and remove translated descriptions."""
    tpl_path = path
    if tpl_path.startswith("tmp"):
        tpl_path = ".".join(
            [x for x in path.split("/") if x not in ["tmp", "DEBIAN"]]
        )
    info(f"reading template file: {tpl_path}")
    template_items = []
    with open(path) as fob:
        for paragraph in Deb822.iter_paragraphs(fob):
            for key in dict(paragraph).keys():
                # only keep English - alt languages have '-xxx' suffix
                if (
                    (key.startswith("Description") and key != "Description")
                    or (key.startswith("Choices") and key != "Choices")
                    or key == "Help"  # some udeb templates include 'Help'
                ):
                    del paragraph[key]

                # Some udeb templates include a 'Help' field e.g.:
                #
                # Template: partman-target/choose_method
                # Type: select
                # Choices: ${DESCRIPTIONS}
                # Description: How to use this partition:
                # Help: partman-target/help
                #
                # However they cause warnings when processed by debconf:
                #
                # debconf: Unknown template field 'help', in stanza #xxx of
                #               /var/lib/dpkg/info/di-live.templates
                #
                # I was unable to find _any_ info about the 'Help' field. So
                # this needs further investigation, but for now just remove

                elif key == "Help":
                    del paragraph[key]

            template_items.append(paragraph)
    return template_items


def write_template_file(path: str, templates: list[Deb822]) -> None:
    info(f"writing consolidated template file: {path}")
    with open(path, "w") as fob:
        for item in templates:
            fob.write(str(item))
            fob.write("\n")


def copy_rootfs_files(udebs: list[str]) -> None:
    for udeb in udebs:
        if "DEBIAN" in os.listdir(join(TMP, udeb)):
            shutil.rmtree(join(TMP, udeb, "DEBIAN"))
        shutil.move(join(TMP, udeb), ROOTFS)


def clean_empty_dirs(path: str) -> None:
    if isfile(path):
        return
    dirs_with_dirs = []
    for base, dirs, files in os.walk(path):
        if files:
            continue
        if dirs:
            dirs_with_dirs.append(base)
        else:
            info(f"removing: {base}")
            os.rmdir(base)
    for dir in reversed(dirs_with_dirs):
        if not os.listdir(dir):
            info(f"removing: {dir}")
            os.rmdir(dir)


def main() -> None:
    heading("initial setup")
    setup()

    udebs = read_txt_file("udebs.txt")
    heading("downloading and unpackaging udebs")
    for udeb in udebs:
        info(udeb)
    download_and_unpack_udebs(udebs)

    heading("consolidating template files")
    template_files = get_template_paths(TMP)
    all_template_items = read_template("di-live.templates")
    for template in template_files:
        all_template_items.extend(read_template(template))
    write_template_file("debian/di-live.templates", all_template_items)

    heading("copying rootfs files and removing blacklisted files")
    copy_rootfs_files(udebs)
    for file in read_txt_file("blacklist.txt"):
        info(f"removing: {file}")
        os.remove(join(ROOTFS, file))

    heading(f"removing empty directories from {ROOTFS}")
    clean_empty_dirs(ROOTFS)
    heading("done")
    info(
        "If debugging is required, run 'add_logging.py' now."
        "\nThat will add logging lines to functions in files that are"
        " sourced."
        "\nIf that script is run, re-run this script before stable build."
    )


if __name__ == "__main__":
    main()
