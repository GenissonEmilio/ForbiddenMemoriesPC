/* Browser build: the points where the game gives the page its turn (port/web/target/yield_*.c). A browser tab
   cannot block, so the port's sleeps and its frame swap become waits that suspend the program (JSPI) and let the
   page draw, deliver input and feed the sound. */
#ifndef PORT_WEB_YIELD_H
#define PORT_WEB_YIELD_H
#ifdef __EMSCRIPTEN__
void Web_SleepMs(double ms); /* sleep (suspends; also yields when ms is 0) */
void Web_FrameDone(void);    /* a picture was presented: yield if the page has not had its turn for a while */
#endif
#endif
