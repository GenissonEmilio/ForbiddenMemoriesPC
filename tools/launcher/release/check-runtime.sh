#!/bin/sh
# Run inside the clean test image: every bundled i386 DSO must resolve there,
# including libraries SDL loads dynamically, such as PulseAudio.
set -eu
PACKAGE=${1:-dist/ForbiddenMemoriesPC}
PACKAGE=$(cd "$PACKAGE" && pwd)
for library in "$PACKAGE"/runtime/lib/*.so* "$PACKAGE"/runtime/lib/dri/*.so; do
    "$PACKAGE/runtime/ld-linux.so.2" --library-path "$PACKAGE/runtime/lib" --list "$library" > /dev/null
done
printf '%s\n' 'All bundled i386 libraries resolve without host i386 packages.'
