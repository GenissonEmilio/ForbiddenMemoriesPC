/* Browser build: the page's touch controls (shell.html) as a pad. The page calls Web_TouchSet whenever a finger
   goes down, moves or lifts; port/src/gs/gs_input.c adds it to player 1's pad at each read. A press that begins and
   ends between two reads (a quick tap) is still seen once: the latch keeps every button pressed since the last read. */
#include <emscripten.h>

static unsigned sHeld, sLatch;
static unsigned char sLx = 0x80, sLy = 0x80;

EMSCRIPTEN_KEEPALIVE void Web_TouchSet(unsigned buttons, int lx, int ly) {
    sHeld = buttons;
    sLatch |= buttons;
    sLx = (unsigned char)lx;
    sLy = (unsigned char)ly;
}

/* the buttons (pad.h bits, 1 = pressed) and, when the stick is off centre, its position. While the menus run, the
   stick also presses the D-pad in its main direction past half way (the menus read only the D-pad; the game itself
   turns the stick into directions the same way, src/sys/pad.c). Not in a battle: there the D-pad is four buttons of
   its own (src/battle/btl_input.c), on the page's D-pad. */
unsigned Web_TouchRead(unsigned char *lx, unsigned char *ly) {
    extern int gPortMenuMode; /* headless.c: 1 while the menus run */
    unsigned b = sHeld | sLatch;
    sLatch = 0;
    if (gPortMenuMode) {
        int x = (int)sLx - 128, y = (int)sLy - 128;
        if ((x < 0 ? -x : x) > (y < 0 ? -y : y)) {
            b |= x > 64 ? 0x20u : x < -64 ? 0x80u : 0u; /* right, left */
        } else {
            b |= y > 64 ? 0x40u : y < -64 ? 0x10u : 0u; /* down, up */
        }
    }
    if (sLx != 0x80 || sLy != 0x80) {
        *lx = sLx;
        *ly = sLy;
    }
    return b;
}
