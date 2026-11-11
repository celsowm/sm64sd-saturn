#include "sm64ds_play.h"
#include <assert.h>
#include <stdio.h>
#define O 65536
static const sm64ds_prism_t prisms[]={
    {.origin={0,0,0},.normal={0,O,0},.edges={{-O,0,0},{0,0,-O},{O,0,O}},
     .min={0,0,0},.max={100*O,0,100*O},.extent=100*O},
    {.origin={30*O,0,0},.normal={-O,0,0},.edges={{0,-O,0},{0,0,-O},{0,O,O}},
     .min={30*O,0,0},.max={30*O,100*O,100*O},.extent=100*O},
    {.origin={0,18*O,0},.normal={0,-O,0},.edges={{-O,0,0},{0,0,-O},{O,0,O}},
     .min={0,18*O,0},.max={100*O,18*O,100*O},.extent=100*O}
};
int main(void) {
    uint32_t offsets[17];uint16_t indices[48];
    for(int i=0;i<17;++i)offsets[i]=i*3;
    for(int i=0;i<48;++i)indices[i]=i%3;
    sm64ds_collision_t w={prisms,offsets,indices,3,4,4,0,0};
    int32_t y;
    assert(sm64ds_floor(&w,10*O,10*O,O,&y)&&y==0);
    assert(!sm64ds_floor(&w,-O,10*O,O,&y));
    assert(!sm64ds_floor(&w,90*O,90*O,O,&y));
    sm64ds_player_t p={.spawn={10*O,0,10*O}};
    sm64ds_player_reset(&p);
    sm64ds_player_step(&p,&w,0,0,0,0);assert(p.grounded);
    for(int i=0;i<90;++i)sm64ds_player_step(&p,&w,O,0,0,1);
    assert(p.wall_hits>0&&p.feet.x<28*O&&p.feet.x>26*O);
    sm64ds_player_reset(&p);sm64ds_player_step(&p,&w,0,0,0,0);
    int32_t peak=0;
    for(int i=0;i<90;++i) {
        sm64ds_player_step(&p,&w,0,0,i==0,0);
        if(p.feet.y>peak)peak=p.feet.y;
    }
    assert(p.jumps==1&&p.grounded&&p.feet.y==0&&p.landings>=2);
    assert(peak>0&&peak<=7*O); /* ceiling stops the head */
    sat_vec3_t from={10*O,8*O,10*O},to={50*O,8*O,10*O};
    int32_t fraction=sm64ds_camera_fraction(&w,&from,&to);
    assert(fraction>0&&fraction<O/2);
    p.feet=(sat_vec3_t){200*O,-161*O,200*O};
    sm64ds_player_step(&p,&w,0,0,0,0);
    assert(p.feet.x==p.spawn.x&&p.feet.y==p.spawn.y&&p.feet.z==p.spawn.z);
    puts("floor, ledge, wall, jump, ceiling, landing, camera and void reset passed");
    return 0;
}
