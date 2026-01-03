#!/bin/bash -e

LOG_FILE=/var/log/di-live_debian-installer.log

original_script=$1
shift

echo "$original_script: $*" >> $LOG_FILE
