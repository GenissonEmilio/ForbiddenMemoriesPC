/* Browser build: everything unlocked from the start (BT3_UNLOCK_ALL=1, set by the page). The game's own leftover
   debug function Save_UnlockAll does it, as the Cheats tab's "Unlock everything" button does (headless.c carries
   the request out at a vertical blank). The save in memory is replaced when a new game starts or a save is loaded
   from the card, so this looks at it every blank and asks again whenever a character is still locked: once per
   fresh save, never again on an unlocked one (the function also empties the records list).
   Never while the memory card flow is busy: a save is checksummed first and written to the card over the frames
   after, and changing it in between leaves a save the game later refuses as corrupt ("Load Failed"). */
#include "port_compat.h"
#include "sys/save.h"
#include "sys/mcflow_a.h"
#include <stdlib.h>

extern volatile int gPortUnlockAll;

void Web_AutoUnlock(void) {
    static int on = -1;
    int i;

    if (on < 0) {
        on = getenv("BT3_UNLOCK_ALL") != NULL && atoi(getenv("BT3_UNLOCK_ALL")) != 0;
    }
    if (!on || gSaveData == NULL || gPortUnlockAll || (gMcFlow != NULL && gMcFlow->state != 0)) {
        return;
    }
    for (i = 0; i < SAVE_CHARA_COUNT; i++) {
        if (!(SAVE_CHARA_WORD(gSaveData, i) & SAVE_CHARA_MASK(i))) {
            gPortUnlockAll = 1;
            return;
        }
    }
}
