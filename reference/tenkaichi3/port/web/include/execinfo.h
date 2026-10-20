/* Browser build: no native backtraces (plat_crash.c prints none; the browser's console has the wasm stack). */
#ifndef PORT_WEB_EXECINFO_H
#define PORT_WEB_EXECINFO_H
static inline int backtrace(void **buf, int size) { (void)buf; (void)size; return 0; }
static inline char **backtrace_symbols(void *const *buf, int size) { (void)buf; (void)size; return 0; }
static inline void backtrace_symbols_fd(void *const *buf, int size, int fd) { (void)buf; (void)size; (void)fd; }
#endif
