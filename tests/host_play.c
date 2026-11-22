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
    sm64ds_collision_t w={prisms,offsets,indices,3,4,4,0,0,0,0u,0};
    int32_t y;
    assert(sm64ds_floor(&w,10*O,10*O,O,&y)&&y==0);
    sat_vec3_t normal={0};
    assert(sm64ds_floor_normal(&w,10*O,10*O,O,&y,&normal)&&normal.y==O);
    assert(!sm64ds_floor_normal(&w,10*O,10*O,O,&y,0));
    sat_mat4_t identity={.m={O,0,0,0, 0,O,0,0, 0,0,O,0, 0,0,0,O}};
    sat_vec3_t slope={O/4,O,0},origin={0,0,0},foot={-4*O,0,0};
    assert(sm64ds_ground_pose_lift(&foot,1,&identity,&origin,&slope)==O+O/32);
    foot.x=4*O;
    assert(sm64ds_ground_pose_lift(&foot,1,&identity,&origin,&slope)==0);
    assert(!sm64ds_floor(&w,-O,10*O,O,&y));
    assert(!sm64ds_floor(&w,90*O,90*O,O,&y));
    sm64ds_player_t p={.spawn={10*O,0,10*O}};
    sm64ds_player_reset(&p);
    sm64ds_player_step(&p,&w,0,0,0,0);assert(p.grounded);
    for(int i=0;i<90;++i)sm64ds_player_step(&p,&w,O,0,0,1);
    assert(p.wall_hits>0&&p.feet.x<28*O&&p.feet.x>26*O);
    assert(p.climb_count==0);
    sm64ds_player_reset(&p);sm64ds_player_step(&p,&w,0,0,0,0);
    int32_t peak=0;
    for(int i=0;i<90;++i) {
        sm64ds_player_step(&p,&w,0,0,i==0,0);
        if(p.feet.y>peak)peak=p.feet.y;
    }
    assert(p.jumps==1&&p.grounded&&p.feet.y==0&&p.landings>=2);
    assert(peak>0&&peak<=7*O); /* ceiling stops the head */
    /* A real wall contact is required to mantle onto a raised floor. */
    {
        const sm64ds_prism_t ledge_prisms[]={
            prisms[0],
            {.origin={30*O,0,0},.normal={-O,0,0},.edges={{0,-O,0},{0,0,-O},{0,O,O}},
             .min={30*O,0,0},.max={30*O,48*O,48*O},.extent=48*O},
            {.origin={30*O,48*O,0},.normal={0,O,0},.edges={{-O,0,0},{0,0,-O},{O,0,O}},
             .min={30*O,48*O,0},.max={78*O,48*O,48*O},.extent=48*O}
        };
        sm64ds_collision_t ledge=w;
        ledge.prisms=ledge_prisms;
        ledge.climb_enabled=1;
        sm64ds_player_t climber={.spawn={24*O,0,10*O}};
        sm64ds_player_reset(&climber);
        for(int i=0;i<6 && !climber.climbing;++i)sm64ds_player_step(&climber,&ledge,O*3/2,0,0,1);
        assert(climber.climbing&&climber.climb_count==1&&climber.climb_top.y==48*O);
        for(int i=0;i<4;++i)sm64ds_player_step(&climber,&ledge,0,0,0,0);
        assert(climber.climbing&&climber.feet.x<30*O&&climber.feet.y>0);
        for(int i=0;i<12;++i)sm64ds_player_step(&climber,&ledge,0,0,0,0);
        assert(!climber.climbing&&climber.grounded&&climber.feet.x>30*O&&climber.feet.y==48*O);

        sm64ds_player_reset(&climber);
        for(int i=0;i<6 && !climber.climbing;++i)sm64ds_player_step(&climber,&ledge,O*3/2,0,0,1);
        assert(climber.climbing);
        sm64ds_player_hurt(&climber,1,-O,0);
        assert(!climber.climbing&&climber.velocity_y==3*O);

        sm64ds_player_reset(&climber);
        for(int i=0;i<6;++i)sm64ds_player_step(&climber,&ledge,0,O,0,1);
        assert(!climber.climbing&&climber.climb_count==2);

        ledge.climb_enabled=0;
        for(int i=0;i<10;++i)sm64ds_player_step(&climber,&ledge,O*3/2,0,0,1);
        assert(!climber.climbing&&climber.climb_count==2);
    }
    sat_vec3_t from={10*O,8*O,10*O},to={50*O,8*O,10*O};
    int32_t fraction=sm64ds_camera_fraction(&w,&from,&to);
    assert(fraction>0&&fraction<O/2);
    int32_t clearance[]={2*O,12*O,24*O,28*O};
    assert(sm64ds_camera_select(clearance,4,0,20*O,25*O)==2);
    /* Keep the chosen side while it remains usable, even if an earlier
     * candidate becomes available; restore the request with more space. */
    clearance[1]=21*O;
    assert(sm64ds_camera_select(clearance,4,2,20*O,25*O)==2);
    clearance[0]=25*O;
    assert(sm64ds_camera_select(clearance,4,2,20*O,25*O)==0);
    clearance[0]=2*O;clearance[1]=3*O;clearance[2]=4*O;clearance[3]=9*O;
    assert(sm64ds_camera_select(clearance,4,2,20*O,25*O)==3);
    p.feet=(sat_vec3_t){200*O,-161*O,200*O};
    sm64ds_player_step(&p,&w,0,0,0,0);
    assert(p.feet.x==p.spawn.x&&p.feet.y==p.spawn.y&&p.feet.z==p.spawn.z);
    /* Health, hurt i-frames, healing and death/respawn at the spawn. */
    sm64ds_player_t hp={.spawn={10*O,0,10*O}};
    sm64ds_player_reset(&hp);
    sm64ds_player_step(&hp,&w,0,0,0,0);
    assert(hp.health==SM64DS_PLAYER_MAX_HEALTH&&hp.max_health==SM64DS_PLAYER_MAX_HEALTH);
    assert(!hp.invuln&&!hp.dead);
    sm64ds_player_hurt(&hp,1,2*O,0);
    assert(hp.health==SM64DS_PLAYER_MAX_HEALTH-1&&hp.invuln==45&&!hp.dead);
    assert(hp.knock_x==2*O&&hp.knock_z==0);          /* pushed away from the hit */
    sm64ds_player_hurt(&hp,1,2*O,0);
    assert(hp.health==SM64DS_PLAYER_MAX_HEALTH-1);   /* ignored during i-frames */
    sm64ds_player_heal(&hp,5);
    assert(hp.health==SM64DS_PLAYER_MAX_HEALTH);     /* clamped */
    /* Coins persist and every 50 restores one health point. */
    sm64ds_player_t cp={.spawn={10*O,0,10*O}};
    sm64ds_player_reset(&cp);
    sm64ds_player_hurt(&cp,1,0,0);
    assert(cp.health==SM64DS_PLAYER_MAX_HEALTH-1&&cp.coins==0);
    sm64ds_player_add_coins(&cp,49);
    assert(cp.coins==49&&cp.health==SM64DS_PLAYER_MAX_HEALTH-1);
    sm64ds_player_add_coins(&cp,1);
    assert(cp.coins==50&&cp.health==SM64DS_PLAYER_MAX_HEALTH);
    uint32_t resets_before=hp.resets;
    for(int i=0;i<SM64DS_PLAYER_MAX_HEALTH;++i){hp.invuln=0;sm64ds_player_hurt(&hp,1,0,0);}
    assert(hp.health==0&&hp.dead&&hp.death_timer==90&&hp.invuln==0);
    sm64ds_player_hurt(&hp,1,0,0);
    assert(hp.health==0);                            /* no damage while down */
    hp.feet=(sat_vec3_t){90*O,0,90*O};
    for(int i=0;i<89;++i)sm64ds_player_step(&hp,&w,0,0,0,0);
    assert(hp.dead&&hp.death_timer==1);
    sm64ds_player_step(&hp,&w,0,0,0,0);
    assert(!hp.dead&&hp.health==SM64DS_PLAYER_MAX_HEALTH);
    assert(hp.feet.x==hp.spawn.x&&hp.feet.y==hp.spawn.y&&hp.feet.z==hp.spawn.z);
    assert(hp.resets==resets_before+1);
    /* Slippery CLPS traction=3 slope (normal ~ (-0.6, 0.8, 0), attr 13) prevents
     * climbing/jumping uphill and slides Mario downhill (-X). */
    const sm64ds_prism_t slope_prisms[]={
        {.origin={0,0,0},.normal={-39322,52429,0},
         .edges={{-52429,-39322,0},{0,0,-O},{52429,39322,O}},
         .min={0,0,0},.max={100*O,80*O,100*O},.extent=125*O,.attribute=13}
    };
    uint32_t soffsets[17];uint16_t sindices[16];
    for(int i=0;i<17;++i)soffsets[i]=i;
    for(int i=0;i<16;++i)sindices[i]=0;
    sm64ds_collision_t sw={slope_prisms,soffsets,sindices,1,4,4,0,0,(1u<<13),0u,0};
    int32_t sy=0;
    assert(sm64ds_floor(&sw,40*O,20*O,100*O,&sy));
    sm64ds_player_t sp={.spawn={40*O,sy,20*O}};
    sm64ds_player_reset(&sp);
    sm64ds_player_step(&sp,&sw,0,0,0,0);
    assert(sp.grounded);
    uint32_t jumps_before=sp.jumps;
    int32_t x_before=sp.feet.x;
    for(int i=0;i<15;++i)sm64ds_player_step(&sp,&sw,O*3/2,0,1,1);
    assert(sp.jumps==jumps_before);
    assert(sp.feet.x<x_before-5*O);
    /* Same slope without slippery bit (45-deg walkable stairs/ramp) is climbable. */
    sw.slippery_attrs=0;
    sm64ds_player_reset(&sp);
    sm64ds_player_step(&sp,&sw,0,0,0,0);
    x_before=sp.feet.x;
    for(int i=0;i<15;++i)sm64ds_player_step(&sp,&sw,O,0,0,1);
    assert(sp.feet.x>x_before+5*O);
    /* Water: a bay surface at y=0 whose CLPS index carries the water bit, over
     * a beach at y=2, a seabed at y=-20 and a shallow shelf at y=-4 out to x=90. Walking
     * off the beach dives in, strokes swim along the facing, the swimmer rises
     * to float with the feet 80 DS units (5.12) under the surface, and the
     * shelf is shallow enough to wade out onto. */
    {
        const sm64ds_prism_t water_prisms[]={
            {.origin={0,0,0},.normal={0,O,0},.edges={{-O,0,0},{0,0,-O},{O,0,O}},
             .min={0,0,0},.max={90*O,0,40*O},.extent=200*O,.attribute=2},
            {.origin={0,2*O,0},.normal={0,O,0},.edges={{-O,0,0},{0,0,-O},{O,0,O}},
             .min={0,2*O,0},.max={20*O,2*O,40*O},.extent=40*O,.attribute=1},
            {.origin={20*O,-20*O,0},.normal={0,O,0},.edges={{-O,0,0},{0,0,-O},{O,0,O}},
             .min={20*O,-20*O,0},.max={40*O,-20*O,40*O},.extent=100*O,.attribute=4},
            {.origin={40*O,-4*O,0},.normal={0,O,0},.edges={{-O,0,0},{0,0,-O},{O,0,O}},
             .min={40*O,-4*O,0},.max={90*O,-4*O,40*O},.extent=200*O,.attribute=3}
        };
        const int32_t float_y=-(O*512/100);
        /* Three 32-unit cells along x, each listing every prism. */
        uint32_t woff[4]={0,4,8,12};uint16_t windex[12]={0,1,2,3,0,1,2,3,0,1,2,3};
        sm64ds_collision_t ww={water_prisms,woff,windex,4,3,1,0,0,0u,(1u<<2),0};
        int32_t surface=0;
        assert(sm64ds_water_surface(&ww,30*O,10*O,-20*O,&surface)&&surface==0);
        assert(!sm64ds_water_surface(&ww,30*O,10*O,O,&surface));
        sm64ds_player_t wp={.spawn={5*O,2*O,10*O}};
        sm64ds_player_reset(&wp);
        sm64ds_player_step(&wp,&ww,0,0,0,0);
        assert(wp.grounded&&!wp.swimming&&wp.feet.y==2*O);
        wp.yaw=0x4000;   /* the caller's facing: +x */
        int32_t swim_steps=0,lowest=0;
        for(int i=0;i<400&&(wp.swimming||!swim_steps);++i) {
            wp.swim_stroke_held=(uint8_t)(swim_steps>0);
            sm64ds_player_step(&wp,&ww,O,0,0,1);
            if(wp.swimming) {
                ++swim_steps;
                assert(wp.feet.y>=-20*O&&wp.feet.y<=float_y);   /* in the water */
                if(wp.feet.y<lowest)lowest=wp.feet.y;
            }
        }
        assert(swim_steps>20);                    /* time spent in the bay */
        assert(lowest<float_y-O);                 /* the fall carried under the float */
        assert(!wp.swimming&&wp.grounded&&wp.feet.y==-4*O&&wp.feet.x>=40*O); /* waded out */
        assert(wp.resets==1&&!wp.dead);
        /* Idle in the bay: the drift lifts the swimmer to the float, and the
         * surface restores health. */
        sm64ds_player_reset(&wp);
        wp.feet=(sat_vec3_t){30*O,-12*O,10*O};wp.health=4;
        sm64ds_player_step(&wp,&ww,0,0,0,0);
        assert(wp.swimming);
        wp.swim_stroke_held=0;
        for(int i=0;i<600;++i)sm64ds_player_step(&wp,&ww,0,0,0,0);
        assert(wp.swimming&&wp.feet.y==float_y&&wp.feet.x==30*O);
        assert(wp.health==wp.max_health);
        /* The d-pad turns the swimmer. */
        uint16_t yaw_before=wp.yaw;
        wp.swim_turn=1;
        for(int i=0;i<30;++i)sm64ds_player_step(&wp,&ww,0,0,0,0);
        wp.swim_turn=0;
        assert((int16_t)(wp.yaw-yaw_before)<-0x800);   /* right turns clockwise */
        /* A jump at the float with the pad held back leaves the water. */
        uint32_t jumps=wp.jumps;
        wp.swim_pitch=1;
        sm64ds_player_step(&wp,&ww,0,0,1,0);
        assert(!wp.swimming&&wp.jumps==jumps+1&&wp.velocity_y>0);
        wp.swim_pitch=0;
    }
    puts("floor, ledge, wall, jump, ceiling, landing, camera, slope, void reset and water swimming passed");
    return 0;
}
