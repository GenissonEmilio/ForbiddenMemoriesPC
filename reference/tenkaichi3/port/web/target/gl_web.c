/* Browser: the per-attachment blend switch and write mask the GL back end wants (GL 3.0 glEnablei / glColorMaski),
   from WebGL 2's OES_draw_buffers_indexed, which Emscripten's GL layer does not wrap. Without them the second
   colour attachment (the alpha ids the destination alpha test and the outline read) gets wrong values, and
   sprites that test it are dropped. */
#include <emscripten.h>

EM_JS(int, Web_GlIndexedInit, (void), {
    Module.glIndexed = GLctx.getExtension('OES_draw_buffers_indexed');
    return Module.glIndexed ? 1 : 0;
});
EM_JS(void, Web_glEnablei, (unsigned cap, unsigned i), { Module.glIndexed.enableiOES(cap, i); });
EM_JS(void, Web_glDisablei, (unsigned cap, unsigned i), { Module.glIndexed.disableiOES(cap, i); });
EM_JS(void, Web_glColorMaski, (unsigned i, unsigned char r, unsigned char g, unsigned char b, unsigned char a), {
    Module.glIndexed.colorMaskiOES(i, !!r, !!g, !!b, !!a);
});

/* Depth as the native back end sets it up: clip-space z in 0..w (EXT_clip_control, the GL 4.5 glClipControl) and the
   depth clamped instead of cut at the near and far planes (EXT_depth_clamp, GL_DEPTH_CLAMP). The game draws much of
   its 2D at depths outside the range; without the clamp WebGL drops those sprites. */
EM_JS(int, Web_GlClipControlInit, (void), {
    Module.glClip = GLctx.getExtension('EXT_clip_control');
    return Module.glClip ? 1 : 0;
});
EM_JS(void, Web_glClipControl, (unsigned origin, unsigned depth), { Module.glClip.clipControlEXT(origin, depth); });
EM_JS(int, Web_GlDepthClamp, (void), {
    const e = GLctx.getExtension('EXT_depth_clamp');
    if (e) GLctx.enable(e.DEPTH_CLAMP_EXT);
    return e ? 1 : 0;
});
