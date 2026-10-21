#include "pc/platform/pointer_targets.h"
#include <assert.h>
#include <stdio.h>

int main(void)
{
    PointerTargets targets={0};
    MenuEvent down={.type=MENU_EVENT_BUTTON_DOWN,.button=1,.x=40,.y=65};
    MenuEvent up=down;up.type=MENU_EVENT_BUTTON_UP;
    PointerTargets_Begin(&targets,1);
    PointerTargets_Add(&targets,3,20,50,160,30);
    assert(PointerTargets_Event(&targets,&up,1)==-1); /* release alone */
    assert(PointerTargets_Event(&targets,&down,1)==-1);
    assert(PointerTargets_Event(&targets,&up,1)==3);
    PointerTargets_Event(&targets,&down,1);
    up.x=200;
    assert(PointerTargets_Event(&targets,&up,1)==-1); /* dragged outside */
    up=down;up.type=MENU_EVENT_BUTTON_UP;
    PointerTargets_Event(&targets,&down,1);
    PointerTargets_Begin(&targets,2); /* overwrite prompt replaces list */
    PointerTargets_Add(&targets,100,20,50,160,30);
    assert(PointerTargets_Event(&targets,&up,2)==-1);
    PointerTargets_Event(&targets,&down,2);
    PointerTargets_Begin(&targets,2); /* repaint preserves a real click */
    PointerTargets_Add(&targets,100,20,50,160,30);
    assert(PointerTargets_Event(&targets,&up,2)==100);
    PointerTargets_Event(&targets,&down,2);
    {MenuEvent key={.type=MENU_EVENT_KEY_DOWN};PointerTargets_Event(&targets,&key,2);}
    assert(PointerTargets_Event(&targets,&up,2)==-1); /* keyboard cancels a held click */
    down.button=3;up.button=3;
    PointerTargets_Event(&targets,&down,2);
    assert(PointerTargets_Event(&targets,&up,2)==-1);
    puts("Mouse targets: scaling geometry, cancelled drags and dialog ownership passed");
    return 0;
}
