#!/bin/sh
export PATH="/usr/lib/audiowmark-desktop:$PATH"
exec python3 /usr/lib/audiowmark-desktop/audiowmark_gui.py "$@"
