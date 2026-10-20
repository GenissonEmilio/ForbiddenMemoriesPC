/* Browser: the game's files come from the user's own disc image, read in place by the page (port/web/web_pre.js).
   The port opens every game file with fopen (port/web/build.py compiles the port's sources with fopen renamed to
   Web_Fopen): before a file of the data root is opened for reading, the page copies it out of the disc image into
   the in-memory file system, suspending the program while it reads (JSPI). */
#include <stdio.h>
#include <emscripten.h>

EM_ASYNC_JS(int, web_disc_ensure, (const char *path), {
    return await Module.webDiscEnsure(UTF8ToString(path));
});

FILE *Web_Fopen(const char *path, const char *mode) {
    if (mode[0] == 'r' && mode[1] != '+' && !(mode[1] == 'b' && mode[2] == '+')) {
        web_disc_ensure(path);
    }
    return fopen(path, mode);
}
