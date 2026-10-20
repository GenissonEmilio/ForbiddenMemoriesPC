/* Node test build: nothing to give way to; the waits are plain (blocking) sleeps or nothing. */
#include <time.h>
#include "web_yield.h"

void Web_SleepMs(double ms) {
    if (ms > 0) {
        struct timespec ts = {(time_t)(ms / 1000.0), (long)((ms - (double)(time_t)(ms / 1000.0) * 1000.0) * 1e6)};
        nanosleep(&ts, 0);
    }
}

void Web_FrameDone(void) {}
