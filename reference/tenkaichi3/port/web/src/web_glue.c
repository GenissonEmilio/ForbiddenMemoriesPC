/* Browser build: definitions that only the wasm link needs. */
unsigned char PortWeb_OverlayArea[16]; /* main.c's overlay load address (Overlay_Load's read is a no-op on PC) */

/* the top of the C heap, for the page's memory report (shell.html, ?telemetry=1) */
#include <emscripten.h>
#include <unistd.h>
EMSCRIPTEN_KEEPALIVE unsigned Web_HeapTop(void) { return (unsigned)(unsigned long)sbrk(0); }
