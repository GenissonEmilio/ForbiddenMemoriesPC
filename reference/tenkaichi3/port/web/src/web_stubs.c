/* Browser build: stand-ins for parts of the PC build that have no browser counterpart. */
#include <stddef.h>
#include "gs/gs_draw.h"

/* The Vulkan back end (gs_gpu.c) is not built: SDL's GPU API has no browser back end. Its init fails, so
   gs_draw.c falls back to the OpenGL back end (WebGL 2 here). */
static int no_init(void) { return 0; }
GsBackend sVulkanBackend = {"vulkan", no_init};

/* headless.c's memory dump covers [__data_start, _end); a wasm program has no such markers (unused in the browser). */
char __data_start[16], _end[16];
