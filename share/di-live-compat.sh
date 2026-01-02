#!/bin/bash -eu

# Dummy di-live compatability script
#
# A number of commands that debian-installer calls are not required by di-live.
# This script provides dummy functionality via an appropriately named symlink.

LOGFILE=/var/log/di-live-compat.log

# First just log what has been called
for msg in \
    "'$0' di-live compat script called - full command:" \
    "# $0 $*"
do
    logger -t di-live-compat "$msg"
    echo "$msg" >> $LOGFILE
done

case $(basename "$0") in
    anna-install|apt-install)
        # do nothing
        ;;
    udpkg)
        # Some d-i scripts use 'udpkg' to figure out the architecture/OS
        # otherwise just send the command to "proper" dpkg
        if [[ "$1" = --print-os ]]; then
            echo linux
        else
            exec dpkg "$@"
        fi
        ;;
    *)
        echo "ERROR: unhandled di-live-compat command '$0' - exiting"
        exit 1
        ;;
esac

exit 0
