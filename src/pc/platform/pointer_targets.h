#ifndef MEMORIES_POINTER_TARGETS_H
#define MEMORIES_POINTER_TARGETS_H
#include "menu.h"
/* Rectangles are registered by the drawing code, so scaling, scrolling,
 * wrapped rows and confirmation dialogs share their real hit geometry. */
typedef struct {
    struct {int id,x,y,w,h;} items[16];
    int count,view,down;
} PointerTargets;
static inline void PointerTargets_Begin(PointerTargets *p,int view) {
    if(p->view!=view) p->down=-1;
    p->view=view;p->count=0;
}
static inline void PointerTargets_Add(PointerTargets *p,int id,int x,int y,int w,int h) {
    if(p->count<16) {int n=p->count++;p->items[n].id=id;p->items[n].x=x;p->items[n].y=y;p->items[n].w=w;p->items[n].h=h;}
}
static inline int PointerTargets_Hit(const PointerTargets *p,int x,int y) {
    int i;
    for(i=p->count-1;i>=0;i--) if(x>=p->items[i].x && x<p->items[i].x+p->items[i].w &&
        y>=p->items[i].y && y<p->items[i].y+p->items[i].h) return p->items[i].id;
    return -1;
}
static inline int PointerTargets_Event(PointerTargets *p,const MenuEvent *e,int view) {
    int hit;
    if(p->view!=view) {p->down=-1;return -1;}
    if(e->type==MENU_EVENT_LEAVE || e->type==MENU_EVENT_KEY_DOWN || e->type==MENU_EVENT_KEY_UP) {
        p->down=-1;return -1;
    }
    if(e->button!=1) return -1;
    hit=PointerTargets_Hit(p,e->x,e->y);
    if(e->type==MENU_EVENT_BUTTON_DOWN) p->down=hit;
    else if(e->type==MENU_EVENT_BUTTON_UP) {int selected=p->down;p->down=-1;return hit==selected?hit:-1;}
    return -1;
}
#endif
