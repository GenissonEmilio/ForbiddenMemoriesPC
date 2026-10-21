#ifndef MEMORIES_GAME_POINTER_H
#define MEMORIES_GAME_POINTER_H
#include "menu.h"
#include <stdint.h>

/* Desktop mouse adapter. Coordinates are window logical pixels, converted
 * through the actual game viewport (letterboxing, internal scale and HiDPI
 * never change the hit targets). It emits ordinary pad input; game rules
 * still own every play, fusion, target, dialog and turn transition. */
int GamePointer_Height(void);
void GamePointer_Viewport(float x, float y, float w, float h, int game_w, int win_w, int win_h);
int GamePointer_Event(const MenuEvent *event);
void GamePointer_Frame(unsigned frame, int blocked);
int GamePointer_Dirty(void);
uint16_t GamePointer_Bits(void);
void GamePointer_Reset(void);
void GamePointer_Draw(MenuCanvas *canvas);
int GamePointer_WantsCard(void);
void GamePointer_CaptureCard(const uint32_t *pixels, int width, int height);
/* Called by the dialog at its live highlight rectangle, not guessed text
 * coordinates. Returns a clicked enabled row, or -1. */
int GamePointer_Choice(int x, int y, int w, int row_height, int selected, int count, unsigned enabled);
#endif
