/* Node test build: the host's files as they are (NODERAWFS), gamedata/ unpacked by extract_disc.py. */
#include <stdio.h>

FILE *Web_Fopen(const char *path, const char *mode) { return fopen(path, mode); }
