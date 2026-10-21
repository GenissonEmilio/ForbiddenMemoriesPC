#include "game_pointer.h"

#if defined(__linux__) && defined(__i386__) && !defined(__ANDROID__)
#include "title_menu.h"
#include "platform.h"
#include "pc/saves/save_menu.h"
#include "pc/saves/deck_menu.h"
#include "game/main_mode_state.h"
#include "game/duel_scene_state.h"
#include "game/duel_side_state.h"
#include "game/duel_selection_layout.h"
#include "game/duel_scene_hand_actions.h"
#include "game/duel_effect.h"
#include "game/display_object.h"
#include "overlays/free_duel/free_duel.h"
#include <stdlib.h>
#include <stdio.h>
#include <string.h>

extern u8 D_8009B174;
extern u8 D_8009B26E;
extern u16 D_8009B162;
extern s16 gGraphics_sViewportY;

enum { UP=0x10, RIGHT=0x20, DOWN=0x40, LEFT=0x80, START=8,
       CROSS=0x4000, CIRCLE=0x2000, TRIANGLE=0x1000 };
enum { IDLE, SELECT_HAND, WAIT_FACE, PLAY_FACE, PLACE, FREE_SELECT, FIELD_SELECT };
static struct {
    float x,y,w,h;
    int game_w,win_w,win_h,mx,my,inside,pressed,drag,source,px,py;
    int action,slot,col,row,face,confirm,mode,button;
    int click,xclick,yclick,redraw,ghost,offset_x,offset_y,blocked;
    unsigned frame,expires,pulse_end,next;
    uint16_t bits;
} ui;
static uint32_t card_picture[52*60];

static int enabled(void) { const char *p=getenv("MEMORIES_MOUSE"); return !p || strcmp(p,"0"); }
int GamePointer_Height(void) { return enabled()?44:0; }
static int mode(void) { return D_8009B26C[0] & 31; }
static int duel(void) { return mode()==3 && D_8009B26E!=0x80; }
static int phase(void) { return gDuel_wSceneStateFlags & 15; }
static int hand_ready(void) {
    return duel() && D_8009B1D5==0 && phase()==4 && (D_8009B174&15)==1 &&
           (gDuel_wSceneStateFlags&0xC000)==0x8000 && !gDuel_bEffectState;
}
static int face_ready(void) {
    return duel() && D_8009B1D5==0 && phase()==4 && (D_8009B174&15)==3 &&
           !(D_8009B174&0x60) && (D_8009B174&0x80) && !gDuel_bEffectState;
}
static DuelSelectionRecord *selection(int i) { return &((DuelSelectionSide *)D_800E9F10)->records[i]; }
static HandCardObject *hand_object(int slot) {
    return slot>=0 && slot<5 ? (HandCardObject *)D_800EA030[slot].object:NULL;
}
static int game_xy(int x,int y,int *gx,int *gy) {
    if(ui.w<=0 || ui.h<=0 || x<ui.x || y<ui.y || x>=ui.x+ui.w || y>=ui.y+ui.h) return 0;
    *gx=(int)((x-ui.x)*ui.game_w/ui.w)-(ui.game_w-320)/2;
    *gy=(int)((y-ui.y)*240/ui.h); return 1;
}
void GamePointer_Viewport(float x,float y,float w,float h,int game_w,int win_w,int win_h) {
    ui.x=x;ui.y=y;ui.w=w;ui.h=h;ui.game_w=game_w;ui.win_w=win_w;ui.win_h=win_h;
}
void GamePointer_Reset(void) {
    ui.bits=0;ui.action=IDLE;ui.drag=ui.pressed=ui.click=0;ui.source=-1;ui.confirm=0;ui.ghost=0;
    ui.col=ui.row=ui.button=-1;ui.next=ui.frame+2;ui.redraw=1;
}
static void pulse(unsigned bits) {
    ui.bits=(uint16_t)bits;ui.pulse_end=ui.frame+2;ui.next=ui.frame+5;
}
static void begin(int action) {
    ui.action=action;ui.mode=mode();ui.expires=ui.frame+300;ui.next=ui.frame+2;
}
static int hand_hit(int x,int y) {
    int i;
    if(!hand_ready() || SaveMenu_Active() || DeckMenu_Active()) return -1;
    for(i=4;i>=0;i--) {
        HandCardObject *o=hand_object(i);
        if(o && (o->flags&0x40) && x>=(s16)o->pos.xy.x && x<(s16)o->pos.xy.x+52 &&
           y>=(s16)o->pos.xy.y && y<(s16)o->pos.xy.y+60) return i;
    }
    return -1;
}
/* Explicit drop targets appear during a drag. They name columns rather
 * than pretending that the perspective camera is a flat 2D board. */
static int zone_hit(int x,int y) {
    int top=duel() && phase()==5?182:112;
    int height=top==182?22:44;
    return x>=15 && x<305 && y>=top && y<top+height ? (x-15)/58:-1;
}
static int button_hit(int x,int y) {
    int width=ui.win_w/8;
    if(width<1 || y<ui.win_h-44 || y>=ui.win_h) return -1;
    return x>=0 && x<ui.win_w ? x/width<8?x/width:7:-1;
}
static void toolbar(int index) {
    static const unsigned directions[]={LEFT,UP,DOWN,RIGHT};
    if(index>=2 && index<=5) { ui.action=IDLE;pulse(directions[index-2]);return; }
    if(index==0) { GamePointer_Reset();pulse(CIRCLE);return; }
    if(index==6) { ui.action=IDLE;pulse(duel()&&phase()==4?UP:TRIANGLE);return; }
    if(index==7) { GamePointer_Reset();pulse(START);return; }
    if(index!=1) return;
    if(face_ready() && ui.action==WAIT_FACE) {ui.face=0;ui.confirm=1;begin(PLAY_FACE);return;}
    ui.action=IDLE;pulse(CROSS);
}
int GamePointer_Event(const MenuEvent *e) {
    int x,y,hit;
    if(!enabled()) return 0;
    if(e->type==MENU_EVENT_LEAVE) {GamePointer_Reset();ui.inside=0;return 0;}
    if(e->type!=MENU_EVENT_MOTION && e->type!=MENU_EVENT_BUTTON_DOWN && e->type!=MENU_EVENT_BUTTON_UP) return 0;
    ui.mx=e->x;ui.my=e->y;ui.inside=1;
    if(e->type==MENU_EVENT_MOTION) {
        ui.redraw=1;
        if(ui.pressed && (abs(e->x-ui.px)>8 || abs(e->y-ui.py)>8)) ui.drag=1;
        if(!ui.pressed && game_xy(e->x,e->y,&x,&y) && (hit=hand_hit(x,y))>=0 &&
           (ui.action==IDLE || (ui.action==SELECT_HAND && ui.confirm<0)) && selection(0)->field_0E!=hit) {
            ui.slot=hit;ui.confirm=-1;begin(SELECT_HAND);
        }
        return ui.pressed;
    }
    if(e->button!=1) { if(e->button==3) GamePointer_Reset();return 0; }
    if(e->type==MENU_EVENT_BUTTON_DOWN) {
        ui.pressed=1;ui.drag=0;ui.px=e->x;ui.py=e->y;ui.source=-1;ui.ghost=0;
        ui.button=button_hit(e->x,e->y);
        if(game_xy(e->x,e->y,&x,&y)) ui.source=hand_hit(x,y);
        return 1;
    }
    if(!ui.pressed) return 1;
    ui.pressed=0;
    if((hit=button_hit(e->x,e->y))>=0) {
        if(hit==ui.button && ui.source<0) toolbar(hit);
        ui.drag=0;return 1;
    }
    if(ui.button>=0) {ui.drag=0;return 1;}
    if(SaveMenu_Active() || DeckMenu_Active()) {ui.drag=0;return 1;}
    if(!game_xy(e->x,e->y,&x,&y)) {ui.drag=0;return 1;}
    if(ui.source>=0 && hand_ready()) {
        if(ui.drag && (hit=zone_hit(x,y))<0) {ui.drag=0;return 1;}
        ui.slot=ui.source;ui.col=ui.drag?hit:-1;ui.row=-1;ui.confirm=0;
        begin(SELECT_HAND);ui.drag=0;return 1;
    }
    ui.drag=0;
    if(face_ready()) {
        /* These two visible buttons are drawn at the same logical places. */
        if(y>=162 && y<184 && x>=70 && x<250) {
            ui.face=x<160;ui.confirm=1;begin(PLAY_FACE);return 1;
        }
        pulse(CROSS);return 1;
    }
    hit=TitleMenu_Point(x,y);
    if(hit) {if(hit>0)pulse(CROSS);return 1;}
    if(mode()==6 && x>=20 && x<300 && y>=35 && y<192) {
        ui.col=(x-20)/56;ui.row=(y+gGraphics_sViewportY-40)/52;
        if(ui.row>=0 && ui.row<8) begin(FREE_SELECT);
        return 1;
    }
    /* The grid strip is also a mouse navigator on the player's field. */
    if(duel() && D_8009B1D5==0 && phase()==4 && (D_8009B174&15)==4 && (hit=zone_hit(x,y))>=0) {
        ui.col=hit;begin(PLACE);return 1;
    }
    if(duel() && D_8009B1D5==0 && phase()==5 && (hit=zone_hit(x,y))>=0) {
        if((D_8009B174&15)!=3 && (D_8009B174&15)!=6) return 1;
        ui.col=hit;ui.row=(D_8009B174&15)==6?1:2;begin(FIELD_SELECT);return 1;
    }
    if(duel() && (phase()==4 || phase()==5)) return 1;
    ui.click=1;ui.xclick=x;ui.yclick=y;ui.expires=ui.frame+4;
    return 1;
}
static void move_grid(DuelSelectionRecord *cursor,int row,int col) {
    if(cursor->row!=row) pulse(cursor->row<row?DOWN:UP);
    else if(cursor->col!=col) pulse(cursor->col<col?RIGHT:LEFT);
    else { pulse(CROSS);ui.action=IDLE; }
}
void GamePointer_Frame(unsigned frame,int blocked) {
    static unsigned last_state;
    unsigned state=(unsigned)mode() | (duel()?(phase()<<5 | D_8009B1D5<<9 | face_ready()<<10 | hand_ready()<<11 | D_8009B174<<12):0);
    if(state!=last_state) {ui.redraw=1;last_state=state;}
    ui.frame=frame;
    ui.blocked=blocked;
    if(blocked || !enabled()) {GamePointer_Reset();return;}
    if(SaveMenu_Active() || DeckMenu_Active()) {ui.action=IDLE;ui.drag=0;}
    if(ui.bits && frame>=ui.pulse_end) ui.bits=0;
    if(frame>ui.expires) {ui.action=IDLE;ui.click=0;}
    if(ui.click && frame==ui.expires && !ui.bits) {ui.click=0;pulse(CROSS);}
    if(ui.action && (mode()!=ui.mode || (duel()&&D_8009B1D5!=0))) {GamePointer_Reset();return;}
    if(ui.bits || frame<ui.next) return;
    if(ui.action==SELECT_HAND && hand_ready()) {
        int at=selection(0)->field_0E;
        if(at!=ui.slot) pulse(at<ui.slot?RIGHT:LEFT);
        else if(ui.confirm<0) ui.action=IDLE;
        else {pulse(CROSS);ui.action=WAIT_FACE;}
    } else if(ui.action==WAIT_FACE && duel() && phase()==4 && (D_8009B174&15)==4 && ui.col>=0) {
        ui.action=PLACE;
    } else if(ui.action==PLAY_FACE && face_ready()) {
        HandCardObject *o=hand_object(selection(0)->field_0E);
        if(!o) {GamePointer_Reset();return;}
        if((o->face==0)!=ui.face) pulse(RIGHT);
        else {pulse(CROSS);ui.action=ui.col>=0?PLACE:IDLE;}
    } else if(ui.action==PLACE && duel()) {
        if(phase()!=4) {ui.action=IDLE;return;}
        if((D_8009B174&15)==4 && !(D_8009B174&0x40) && !D_8009B162 && !gDuel_bEffectState) {
            /* The game already chose a legal row for this card's type. */
            DuelSelectionRecord *cursor=selection(2);
            if(cursor->col!=ui.col) pulse(cursor->col<ui.col?RIGHT:LEFT);
            else {pulse(CROSS);ui.action=IDLE;}
        }
    } else if(ui.action==FREE_SELECT && mode()==6) {
        if(gFreeDuel_bCursorRow!=ui.row) pulse(gFreeDuel_bCursorRow<ui.row?DOWN:UP);
        else if(gFreeDuel_bCursorColumn!=ui.col) pulse(gFreeDuel_bCursorColumn<ui.col?RIGHT:LEFT);
        else {pulse(CROSS);ui.action=IDLE;}
    } else if(ui.action==FIELD_SELECT && duel() && phase()==5 && !gDuel_bEffectState) {
        if((D_8009B174&15)==(ui.row==1?6:3)) {
            if(!(D_8009B174&0x40) && !D_8009B162) move_grid(selection(ui.row==1?3:2),ui.row,ui.col);
        } else ui.action=IDLE;
    }
}
int GamePointer_Dirty(void) {int changed=ui.redraw;ui.redraw=0;return changed;}
uint16_t GamePointer_Bits(void) {return enabled()?ui.bits:0;}
int GamePointer_WantsCard(void) {return ui.pressed && ui.source>=0 && !ui.ghost;}
void GamePointer_CaptureCard(const uint32_t *pixels,int width,int height) {
    HandCardObject *o=hand_object(ui.source);
    int i,j,x,y;
    if(!o || !pixels || width<=0 || height<=0 || !ui.game_w) return;
    for(j=0;j<60;j++) for(i=0;i<52;i++) {
        x=((s16)o->pos.xy.x+(ui.game_w-320)/2+i)*width/ui.game_w;
        y=((s16)o->pos.xy.y+j)*height/240;
        if(x<0)x=0;if(x>=width)x=width-1;if(y<0)y=0;if(y>=height)y=height-1;
        card_picture[j*52+i]=0xFF000000u|pixels[y*width+x];
    }
    ui.offset_x=ui.px-(int)(ui.x+((s16)o->pos.xy.x+(ui.game_w-320)/2)*ui.w/ui.game_w);
    ui.offset_y=ui.py-(int)(ui.y+(s16)o->pos.xy.y*ui.h/240);
    ui.ghost=1;
}
int GamePointer_Choice(int x,int y,int w,int step,int selected,int count,unsigned allowed) {
    int row;
    if(!ui.click || ui.frame>ui.expires || step<=0) return -1;
    /* A disabled row or the dialog's background never confirms the old
     * selection through the generic click-to-advance fallback. */
    ui.click=0;
    y-=selected*step;
    row=(ui.yclick-y)/step;
    if(ui.xclick<x || ui.xclick>=x+w || ui.yclick<y || row<0 || row>=count || row>=32 || !(allowed&(1u<<row))) return -1;
    pulse(CROSS);return row;
}
static void fill(MenuCanvas *c,int x,int y,int w,int h,uint32_t color) {
    int i,j;
    for(j=y<0?0:y;j<y+h && j<c->height;j++)
        for(i=x<0?0:x;i<x+w && i<c->width;i++) c->pixels[j*c->stride+i]=color;
}
static void rectangle(MenuCanvas *c,int x,int y,int w,int h,uint32_t color) {
    fill(c,x,y,w,2,color);fill(c,x,y+h-2,w,2,color);fill(c,x,y,2,h,color);fill(c,x+w-2,y,2,h,color);
}
static void game_rect(MenuCanvas *c,int x,int y,int w,int h,const char *text,int highlight) {
    int px=(int)(ui.x+(x+(ui.game_w-320)/2)*ui.w/ui.game_w),py=(int)(ui.y+y*ui.h/240);
    int pw=(int)(w*ui.w/ui.game_w),ph=(int)(h*ui.h/240);
    fill(c,px,py,pw,ph,highlight?0xF0473825:0xEA141822);
    rectangle(c,px,py,pw,ph,highlight?0xFFF0D392:0xFF9F8147);
    Menu_DrawTextScaled(c,px+7,py+(ph-16)/2,text,0xFFF1D99F,1);
}
void GamePointer_Draw(MenuCanvas *c) {
    static const char *labels[]={"Voltar","Confirmar","<","^","v",">","Detalhes","Iniciar"};
    int i,bw=ui.win_w/8,x=-1,y=-1;
    if(!enabled() || !ui.win_w) return;
    fill(c,0,ui.win_h-44,ui.win_w,44,0xFC10141D);
    for(i=0;i<8;i++) {
        const char *word=labels[i];int px=i*bw+3,pw=(i==7?ui.win_w-i*bw:bw)-6;
        if(i==6 && hand_ready()) word="Marcar fusao";
        if(i==7 && duel()) word="Fim do turno";
        if(i==1 && face_ready()) word="Jogar fechada";
        if(bw<120 && i==6 && hand_ready()) word="Fusao";
        if(bw<120 && i==7 && duel()) word="Turno";
        if(bw<120 && i==1) word="OK";
        fill(c,px,ui.win_h-38,pw,32,button_hit(ui.mx,ui.my)==i?0xFF423725:0xFF232836);
        rectangle(c,px,ui.win_h-38,pw,32,0xFF6C5C3C);
        Menu_DrawTextScaled(c,px+6,ui.win_h-29,word,0xFFF0D49A,1);
    }
    if(ui.blocked) return;
    if(duel() && D_8009B1D5==0 && ((ui.drag&&ui.source>=0) ||
       (phase()==5 && ((D_8009B174&15)==3 || (D_8009B174&15)==6)) ||
       (phase()==4 && (D_8009B174&15)==4))) {
        game_xy(ui.mx,ui.my,&x,&y);
        for(i=0;i<5;i++) {
            char label[20];
            snprintf(label,sizeof(label),"%s %d",phase()==5?((D_8009B174&15)==6?"Alvo":"Carta"):"Soltar",i+1);
            game_rect(c,15+i*58,phase()==5?182:112,54,phase()==5?22:44,label,zone_hit(x,y)==i);
        }
    }
    if(ui.drag && ui.source>=0) {
        int w=(int)(52*ui.w/ui.game_w),h=(int)(60*ui.h/240),i,j;
        int left=ui.mx-ui.offset_x,top=ui.my-ui.offset_y;
        fill(c,left+5,top+5,w,h,0xC0000000);
        for(j=0;j<h;j++) for(i=0;i<w;i++) {
            int px=left+i,py=top+j;
            if(px>=0 && px<c->width && py>=0 && py<c->height && ui.ghost)
                c->pixels[py*c->stride+px]=card_picture[(j*60/h)*52+i*52/w];
        }
        rectangle(c,left,top,w,h,0xFFE4C178);
    }
    if(face_ready()) {
        game_rect(c,70,162,86,22,"Face para cima",0);
        game_rect(c,164,162,86,22,"Face para baixo",0);
    }
}
#else
int GamePointer_Height(void) {return 0;}
void GamePointer_Viewport(float x,float y,float w,float h,int gw,int ww,int wh) {(void)x;(void)y;(void)w;(void)h;(void)gw;(void)ww;(void)wh;}
int GamePointer_Event(const MenuEvent *e) {(void)e;return 0;}
void GamePointer_Frame(unsigned f,int b) {(void)f;(void)b;}
int GamePointer_Dirty(void) {return 0;}
uint16_t GamePointer_Bits(void) {return 0;}
void GamePointer_Reset(void) {}
void GamePointer_Draw(MenuCanvas *c) {(void)c;}
int GamePointer_WantsCard(void) {return 0;}
void GamePointer_CaptureCard(const uint32_t *p,int w,int h) {(void)p;(void)w;(void)h;}
int GamePointer_Choice(int x,int y,int w,int h,int s,int n,unsigned e) {(void)x;(void)y;(void)w;(void)h;(void)s;(void)n;(void)e;return -1;}
#endif
