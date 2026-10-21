#ifndef MEMORIES_PC_PLATFORM_TITLE_MENU_H
#define MEMORIES_PC_PLATFORM_TITLE_MENU_H
/* The title's two menus as the mods' "menu" key has them (title_menu.c,
 * notes/modding.md "The title's menus"): the entries the game has, and the
 * buttons the mods add, in the mods' order, each doing what its mod chose.
 * The game's MainMenu_UpdateFrontendMenu still runs the menus -- their
 * slides, fades and dialogs, and the retail entries' own choices -- and
 * this runs the cursor over all of the items, takes a choice the game would
 * not make, and draws the items the game has no sprite for, sliding them as
 * the game slides its own. title_screen.c calls it. */

struct MemoriesState;

/* MainMenu_InitFrontendMenu has made the entries: parks the ones drawn
 * here, and puts the cursor back where it was before the menu was left. */
void TitleMenu_Opened(void);
/* MainMenu_DestroyFrontendMenu: the menus are gone. */
void TitleMenu_Closed(void);
/* Before MainMenu_UpdateFrontendMenu: takes the pad's up, down and a choice
 * while a menu waits for one. Returns the pad bits the game must not see
 * this frame. */
unsigned TitleMenu_Before(void);
/* After it, with what it returned: what the title returns instead (a choice
 * made here), and the cursor and slides kept up with the game. */
int TitleMenu_After(int result);
/* Each frame, after the game's update: the game's entries at their places
 * (hidden ones, and the ones drawn here, off the screen), the widescreen
 * ones while View > Aspect is 16:9. */
void TitleMenu_Place(void);
/* The items drawn here, into the entries' ordering table
 * (MainMenu_DrawFrontendBackground). */
void TitleMenu_Draw(void);
/* Main_ApplyMenuSelection: the entry the title opens on when it comes back
 * after `selection`, for one made here that is none of the game's. */
int TitleMenu_Reopen(int selection, int reopen);
/* Save states: the cursor and the slides. */
void TitleMenu_State(struct MemoriesState *state);
/* Whether a menu is up (not PUSH START BUTTON); 0 or 1, which. -1 none. */
int TitleMenu_Showing(void);
/* Click a visible item at its actual mod/scaled/widescreen position.
 * 1 selected, -1 menu background, 0 no interactive title menu. */
int TitleMenu_Point(int x, int y);
/* The name of item `index` ("load", "my-mod:credits"), or NULL: for the
 * mods' MEMORIES_EVENT_MENU. */
const char *TitleMenu_ItemName(int index);
#endif
