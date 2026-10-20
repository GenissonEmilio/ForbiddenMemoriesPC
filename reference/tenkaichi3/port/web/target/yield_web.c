/* Browser: the waits of web_yield.h, suspending the WebAssembly program (JSPI or Asyncify, port/web/link.py).
   Also measures, each second, how much of the time the program ran (the rest it waited): Module.webStats. */
#include <emscripten.h>
#include "web_yield.h"

static double sLastYield, sWindow, sWaited, sPresents, sWaits, sAsked, sLong, sProf[4];

/* time spent in a part of the program (slot 0: the GL back end's frame submission), for Module.webStats.prof */
void Web_ProfAdd(int slot, double ms) { sProf[slot & 3] += ms; }

EM_ASYNC_JS(void, web_wait_ms, (double ms), {
    if (ms <= 0) {
        // a zero wait: a message (setTimeout(0) is held to 4 ms after a few in a row)
        await new Promise(r => { const c = new MessageChannel(); c.port1.onmessage = () => r(); c.port2.postMessage(0); });
    } else {
        await new Promise(r => setTimeout(r, ms));
    }
});

EM_JS(void, web_stats, (double wall, double waited, double presents, double waits, double asked, double longest, double p0, double p1, double p2, double p3), {
    Module.webStats = { busy: (wall - waited) / wall, fps: presents * 1000 / wall, at: performance.now(),
                        waits: waits, askedMs: asked, waitedMs: waited, longestMs: longest, prof: [p0 / wall, p1 / wall, p2 / wall, p3 / wall] };
    if (Module.onWebStats) Module.onWebStats(Module.webStats);
});

void Web_SleepMs(double ms) {
    double t = emscripten_get_now();
    web_wait_ms(ms);
    sLastYield = emscripten_get_now();
    sWaited += sLastYield - t;
    sWaits++;
    sAsked += ms > 0 ? ms : 0;
    if (sLastYield - t > sLong) {
        sLong = sLastYield - t;
    }
    if (sWindow == 0) {
        sWindow = sLastYield;
        sWaited = 0;
    } else if (sLastYield - sWindow >= 1000) {
        web_stats(sLastYield - sWindow, sWaited, sPresents, sWaits, sAsked, sLong, sProf[0], sProf[1], sProf[2], sProf[3]);
        sProf[0] = sProf[1] = sProf[2] = sProf[3] = 0;
        sWindow = sLastYield;
        sWaited = sPresents = sWaits = sAsked = sLong = 0;
    }
}

void Web_FrameDone(void) {
    sPresents++;
    if (emscripten_get_now() - sLastYield > 20.0) {
        Web_SleepMs(0);
    }
}
