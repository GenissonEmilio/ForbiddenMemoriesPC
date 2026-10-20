/* Browser build: the float-typed entry points port/web/irweb.py calls in place of the game's float instructions.
   Each passes the bit patterns to the PS2 arithmetic of port/src/softfloat_ps2.c (the 32-bit build reaches the same
   functions through -msoft-float). WebAssembly moves f32 values without touching their bits, so patterns with
   exponent 255 (ordinary numbers on the PS2) survive the trip. Compiled with hardware float and no rewriting. */
#include <stdint.h>

uint32_t __addsf3(uint32_t, uint32_t);
uint32_t __subsf3(uint32_t, uint32_t);
uint32_t __mulsf3(uint32_t, uint32_t);
uint32_t __divsf3(uint32_t, uint32_t);
int __ltsf2(uint32_t, uint32_t);
int32_t __fixsfsi(uint32_t);
uint32_t __fixunssfsi(uint32_t);
uint32_t __floatsisf(int32_t);
uint32_t __floatunsisf(uint32_t);
float fmodf(float, float);

static inline uint32_t B(float f) { return __builtin_bit_cast(uint32_t, f); }
static inline float F(uint32_t u) { return __builtin_bit_cast(float, u); }

float __web_fadd(float a, float b) { return F(__addsf3(B(a), B(b))); }
float __web_fsub(float a, float b) { return F(__subsf3(B(a), B(b))); }
float __web_fmul(float a, float b) { return F(__mulsf3(B(a), B(b))); }
float __web_fdiv(float a, float b) { return F(__divsf3(B(a), B(b))); }
float __web_frem(float a, float b) { return fmodf(a, b); }
int __web_fcmp(float a, float b) { return __ltsf2(B(a), B(b)); } /* -1 / 0 / 1: every pattern is a number */
int32_t __web_f2i(float a) { return __fixsfsi(B(a)); }
uint32_t __web_f2u(float a) { return __fixunssfsi(B(a)); }
float __web_i2f(int32_t v) { return F(__floatsisf(v)); }
float __web_u2f(uint32_t v) { return F(__floatunsisf(v)); }
/* 64-bit conversions: libgcc's IEEE code on the PS2; the processor's own here, saturating instead of trapping. */
int64_t __web_f2l(float a) {
    if (a != a) return 0;
    if (a >= 9.2233720368547758e18f) return INT64_MAX;
    if (a <= -9.2233720368547758e18f) return INT64_MIN;
    return (int64_t)a;
}
uint64_t __web_f2ul(float a) {
    if (!(a > 0.0f)) return 0;
    if (a >= 1.8446744073709552e19f) return UINT64_MAX;
    return (uint64_t)a;
}
float __web_l2f(int64_t v) { return (float)v; }
float __web_ul2f(uint64_t v) { return (float)v; }
