#include "sm64ds_play.h"
#include <limits.h>

#define ONE 65536
#define RADIUS (3*ONE)
#define HEIGHT (12*ONE)
#define STEP (2*ONE)
static int32_t mul(int32_t a,int32_t b) { return (int32_t)(((int64_t)a*b)/ONE); }
static int32_t dot(sat_vec3_t a,sat_vec3_t b) {
    return (int32_t)(((int64_t)a.x*b.x+(int64_t)a.y*b.y+(int64_t)a.z*b.z)/ONE);
}
static sat_vec3_t sub(sat_vec3_t a,sat_vec3_t b) {
    return (sat_vec3_t){a.x-b.x,a.y-b.y,a.z-b.z};
}
static int inside(const sm64ds_prism_t *p,sat_vec3_t point,int32_t margin) {
    sat_vec3_t r=sub(point,p->origin);
    return dot(r,p->edges[0])<=margin && dot(r,p->edges[1])<=margin &&
           dot(r,p->edges[2])<=p->extent+margin && dot(r,p->edges[2])>=-margin;
}
static int cell(const sm64ds_collision_t *w,int32_t x,int32_t z) {
    int32_t a=x-w->origin_x,b=z-w->origin_z;
    if(a<0||b<0)return -1;
    a/=32*ONE;b/=32*ONE;
    return a<w->nx&&b<w->nz ? b*w->nx+a : -1;
}
/* CLPS traction=3 slopes (>~20 deg, ny < 0.94) and steep cliffs (>~49.5 deg,
 * ny < 0.65) cannot be climbed; 45 deg stairs (ny ~ 0.68-0.71, traction != 3)
 * remain freely walkable. */
#define SLIPPERY_NORMAL_Y 61600
#define STEEP_NORMAL_Y 42598
/* Terrace climbing. CLIMB_MAX is the tallest lip and CLIMB_SPEED is the rise
 * per simulation step. */
#define CLIMB_MAX (88*ONE)
#define CLIMB_SPEED (4*ONE)
#define CLIMB_REACH (1*ONE)          /* wall probe distance past the body */
#define CLIMB_COOLDOWN 30
#define CLIMB_TIMEOUT 90
/* Water: a CLPS with the water bit (word0 & 0x20) is the water surface, never
 * solid ground; under it the player swims (the DS St_Swim_Init/Main).
 * Distances are DS units at the KCL scale (0.064). Speeds keep the walk/run
 * proportions here (32 DS units per 30 Hz frame is the 1.5 run): a DS speed
 * in 20.12 is 3/4 of it in 16.16 per step, and a DS acceleration 3/8. */
#define SWIM_FLOAT (ONE*512/100)      /* 80: the feet under the surface when floating */
#define SWIM_EXIT (ONE*64/10)         /* 100: a surface this far under the feet ends it */
#define SWIM_DEEP (ONE*384/100)       /* 60 under the float: holding breath */
#define SWIM_DRIFT_DEPTH (32*ONE)     /* 500 under the float: rising turns to sinking */
#define SWIM_GROUND_EXIT (ONE*64/100) /* 10: standing this far over the float walks out */
#define SWIM_RISE 0x1200              /* 0x1800: drift toward the surface */
#define SWIM_SINK 0x1800              /* 0x2000: drift down, deep */
#define SWIM_STROKE 0xc000            /* 0x10000: stroke speed */
#define SWIM_HOLD 0x9000              /* 0xc000: speed while the stroke is held */
#define SWIM_ENTRY_MAX (ONE*3/2)      /* fastest dive into the water */
#define SWIM_AIR_STEPS 480u           /* 240 frames deep per health point */
#define SWIM_HEAL_STEPS 30u           /* 15 frames at the surface per health point */
/* sin over a quarter turn of the DS 0x10000-per-turn angle, in 16.16. */
static const int32_t quarter_sin[65]={
    0,1608,3216,4821,6424,8022,9616,11204,12785,
    14359,15924,17479,19024,20557,22078,23586,25080,26558,
    28020,29466,30893,32303,33692,35062,36410,37736,39040,
    40320,41576,42806,44011,45190,46341,47464,48559,49624,
    50660,51665,52639,53581,54491,55368,56212,57022,57798,
    58538,59244,59914,60547,61145,61705,62228,62714,63162,
    63572,63944,64277,64571,64827,65043,65220,65358,65457,
    65516,65536};
static int32_t angle_sin(uint16_t a) {
    uint16_t q=(uint16_t)(a&0x3fffu);
    if(a&0x4000u) q=(uint16_t)(0x4000u-q);
    uint32_t i=q>>8u,f=q&0xffu;
    int32_t v=quarter_sin[i];
    if(i<64u) v+=(int32_t)(((int64_t)(quarter_sin[i+1u]-v)*(int32_t)f)>>8);
    return (a&0x8000u)?-v:v;
}
static int32_t angle_cos(uint16_t a) { return angle_sin((uint16_t)(a+0x4000u)); }
static int32_t approach(int32_t v,int32_t target,int32_t step) {
    if(v<target) { v+=step; if(v>target) v=target; }
    else if(v>target) { v-=step; if(v<target) v=target; }
    return v;
}
static int is_slippery_floor(const sm64ds_collision_t *w,const sm64ds_prism_t *p) {
    if (p->normal.y<STEEP_NORMAL_Y) return 1;
    if (p->attribute<32u && (w->slippery_attrs&(1u<<p->attribute)) &&
        p->normal.y<SLIPPERY_NORMAL_Y) return 1;
    return 0;
}
static int is_water_floor(const sm64ds_collision_t *w,const sm64ds_prism_t *p) {
    return p->attribute<32u && (w->water_attrs&(1u<<p->attribute))!=0u;
}
static int32_t plane_y(const sm64ds_prism_t *p,int32_t x,int32_t z) {
    return p->origin.y-(int32_t)(((int64_t)(x-p->origin.x)*p->normal.x+
                (int64_t)(z-p->origin.z)*p->normal.z)/p->normal.y);
}
/* The highest floor under `ceiling`. A solid query passes the water surface. */
static int floor_query(const sm64ds_collision_t *w,int32_t x,int32_t z,
                       int32_t ceiling,int32_t *height,sat_vec3_t *normal,
                       uint8_t *slippery,uint8_t *water,uint8_t solid) {
    int bin=cell(w,x,z),found=0;
    int32_t best=INT32_MIN;
    uint8_t best_slippery=0,best_water=0;
    if(bin<0)return 0;
    for(uint32_t k=w->offsets[bin];k<w->offsets[bin+1];++k) {
        const sm64ds_prism_t *p=&w->prisms[w->indices[k]];
        if(p->normal.y<ONE/2||x<p->min.x||x>p->max.x||z<p->min.z||z>p->max.z)continue;
        if(solid&&is_water_floor(w,p))continue;
        int32_t y=plane_y(p,x,z);
        if(y>ceiling||y<=best)continue;
        if(inside(p,(sat_vec3_t){x,y,z},ONE/32)) {
            best=y;found=1;
            if(normal)*normal=p->normal;
            best_slippery=(uint8_t)is_slippery_floor(w,p);
            best_water=(uint8_t)is_water_floor(w,p);
        }
    }
    if(found) {
        *height=best;
        if(slippery)*slippery=best_slippery;
        if(water)*water=best_water;
    }
    return found;
}
int sm64ds_floor(const sm64ds_collision_t *w,int32_t x,int32_t z,
                 int32_t ceiling,int32_t *height) {
    return floor_query(w,x,z,ceiling,height,0,0,0,0);
}
int sm64ds_floor_normal(const sm64ds_collision_t *w,int32_t x,int32_t z,
                        int32_t ceiling,int32_t *height,sat_vec3_t *normal) {
    uint8_t slippery=0,water=0;
    if(!normal) return 0;
    if(!floor_query(w,x,z,ceiling,height,normal,&slippery,&water,0)) return 0;
    return water?0:1;   /* a water surface has no usable walk normal */
}
int sm64ds_water_surface(const sm64ds_collision_t *w,int32_t x,int32_t z,
                         int32_t from,int32_t *height) {
    int bin=cell(w,x,z),found=0;
    int32_t best=INT32_MAX;
    if(bin<0||!height)return 0;
    for(uint32_t k=w->offsets[bin];k<w->offsets[bin+1];++k) {
        const sm64ds_prism_t *p=&w->prisms[w->indices[k]];
        if(p->normal.y<ONE/2||!is_water_floor(w,p)||
           x<p->min.x||x>p->max.x||z<p->min.z||z>p->max.z)continue;
        int32_t y=plane_y(p,x,z);
        if(y<from||y>=best)continue;
        if(inside(p,(sat_vec3_t){x,y,z},ONE/32)) {best=y;found=1;}
    }
    if(found)*height=best;
    return found;
}
int32_t sm64ds_ground_pose_lift(const sat_vec3_t *vertices,uint16_t count,
                                const sat_mat4_t *world,const sat_vec3_t *point,
                                const sat_vec3_t *normal) {
    if(!vertices || !world || !point || !normal || normal->y<=0) return 0;
    int64_t lowest=0;
    for(uint16_t i=0;i<count;++i) {
        const sat_vec3_t *v=&vertices[i];
        int64_t x=((int64_t)world->m[0]*v->x+(int64_t)world->m[1]*v->y+(int64_t)world->m[2]*v->z)/ONE+world->m[3];
        int64_t y=((int64_t)world->m[4]*v->x+(int64_t)world->m[5]*v->y+(int64_t)world->m[6]*v->z)/ONE+world->m[7];
        int64_t z=((int64_t)world->m[8]*v->x+(int64_t)world->m[9]*v->y+(int64_t)world->m[10]*v->z)/ONE+world->m[11];
        int64_t signed_height=(x-point->x)*normal->x+(y-point->y)*normal->y+(z-point->z)*normal->z;
        if(signed_height<lowest) lowest=signed_height;
    }
    if(!lowest) return 0;
    int64_t lift=(-lowest+normal->y-1)/normal->y+ONE/32;
    return lift>INT32_MAX?INT32_MAX:(int32_t)lift;
}
static void swim_leave(sm64ds_player_t *p) {
    p->swimming=0;p->swim_speed=0;p->pitch=0;p->yaw_speed=0;
    p->velocity_y=0;p->air_ticks=0;p->heal_ticks=0;
}
void sm64ds_player_reset(sm64ds_player_t *p) {
    p->feet=p->spawn;p->velocity_y=0;p->knock_x=p->knock_z=0;p->grounded=0;p->moving=0;p->running=0;
    swim_leave(p);
    p->climbing=0;p->climb_cooldown=0;p->climb_top=(sat_vec3_t){0,0,0};p->climb_steps=0;
    if(!p->max_health)p->max_health=SM64DS_PLAYER_MAX_HEALTH;
    p->health=p->max_health;p->invuln=0;p->dead=0;p->death_timer=0;
    p->held_yaw=0;
    ++p->resets;
}
void sm64ds_player_hurt(sm64ds_player_t *p,uint8_t damage,
                        int32_t push_x,int32_t push_z) {
    if(p->dead||p->invuln)return;
    if(!p->max_health)p->max_health=SM64DS_PLAYER_MAX_HEALTH;
    if(damage>=p->health)p->health=0;
    else p->health=(uint8_t)(p->health-damage);
    p->knock_x=push_x;p->knock_z=push_z;
    if(p->climbing) {p->climbing=0;p->climb_cooldown=CLIMB_COOLDOWN;}
    if(p->swimming) p->swim_speed=0;   /* a hit stops the stroke, not the swim */
    else {p->velocity_y=3*ONE;p->grounded=0;}
    if(!p->health) {
        p->dead=1;p->death_timer=90;p->invuln=0;
    } else p->invuln=45;
}
void sm64ds_player_heal(sm64ds_player_t *p,uint8_t amount) {
    if(p->dead)return;
    uint16_t total=(uint16_t)p->health+amount;
    p->health=(uint8_t)(total>p->max_health?p->max_health:total);
}
void sm64ds_player_add_coins(sm64ds_player_t *p,uint16_t amount) {
    uint16_t before=p->coins;
    p->coins=(uint16_t)(before+amount);
    if(p->coins/50u>before/50u)sm64ds_player_heal(p,1);
}
/* Push the body capsule out of walls and ceilings; returns the wall contacts. */
static uint32_t push_walls(sm64ds_player_t *p,const sm64ds_collision_t *w) {
    uint32_t hits=0;
    for(int iteration=0;iteration<3;++iteration) {
        int bin=cell(w,p->feet.x,p->feet.z);
        if(bin<0)break;
        for(uint32_t k=w->offsets[bin];k<w->offsets[bin+1];++k) {
            const sm64ds_prism_t *t=&w->prisms[w->indices[k]];
            if(t->normal.y>=ONE/2)continue;
            if(p->feet.x<t->min.x-RADIUS||p->feet.x>t->max.x+RADIUS||
               p->feet.z<t->min.z-RADIUS||p->feet.z>t->max.z+RADIUS||
               p->feet.y>t->max.y+RADIUS||p->feet.y+HEIGHT<t->min.y)continue;
            for(int s=0;s<2;++s) {
                sat_vec3_t center={p->feet.x,p->feet.y+(s?HEIGHT-RADIUS:RADIUS),p->feet.z};
                int32_t d=dot(sub(center,t->origin),t->normal);
                if(d< -RADIUS||d>=RADIUS)continue;
                sat_vec3_t point={center.x-mul(d,t->normal.x),center.y-mul(d,t->normal.y),center.z-mul(d,t->normal.z)};
                if(!inside(t,point,RADIUS/2))continue;
                int32_t push=RADIUS-d+ONE/64;
                p->feet.x+=mul(push,t->normal.x);p->feet.z+=mul(push,t->normal.z);
                if(t->normal.y< -ONE/2) {
                    p->feet.y+=mul(push,t->normal.y);
                    if(p->velocity_y>0)p->velocity_y=0;
                } else {++p->wall_hits;++hits;}
            }
        }
    }
    return hits;
}
static void swim_enter(sm64ds_player_t *p,int32_t surface) {
    /* St_Swim_Init: the fall carries on as a dive that the water slows. */
    p->swimming=1;p->water_y=surface;
    p->swim_speed=p->velocity_y<-SWIM_ENTRY_MAX?-SWIM_ENTRY_MAX:
                  (p->velocity_y>0?0:p->velocity_y);
    p->swim_phase=0;p->swim_timer=0;p->swim_released=0;
    p->pitch=0;p->yaw_speed=0;p->velocity_y=0;p->grounded=0;
    p->air_ticks=0;p->heal_ticks=0;
}
/* func_ov002_020ce324: at the surface, a jump with the pad held back or a
 * wall ahead leaves the water. */
static int swim_jump_out(sm64ds_player_t *p,uint8_t jump,int32_t float_y) {
    if(!jump||p->feet.y+SWIM_DEEP<=float_y)return 0;
    if(p->swim_pitch<=0&&!p->swim_wall)return 0;
    swim_leave(p);
    p->velocity_y=3*ONE;p->grounded=0;++p->jumps;
    return 1;
}
static void swim_step(sm64ds_player_t *p,const sm64ds_collision_t *w,uint8_t jump) {
    int32_t surface=0;
    if(!sm64ds_water_surface(w,p->feet.x,p->feet.z,p->feet.y-SWIM_EXIT,&surface)) {
        swim_leave(p);   /* out of the water's reach: fall or walk */
        return;
    }
    p->water_y=surface;
    const int32_t float_y=surface-SWIM_FLOAT;
    /* func_ov002_020cec2c: deep water drains health, the surface restores it. */
    if(p->feet.y+SWIM_DEEP<=float_y) {
        p->heal_ticks=0;
        if(++p->air_ticks>=SWIM_AIR_STEPS) {
            p->air_ticks=0;
            if(p->health<=1) {p->health=0;p->dead=1;p->death_timer=90;return;}
            --p->health;
        }
    } else {
        p->air_ticks=0;
        if(++p->heal_ticks>=SWIM_HEAL_STEPS) {p->heal_ticks=0;sm64ds_player_heal(p,1);}
    }
    if(p->swim_timer)--p->swim_timer;
    /* func_ov002_020cd71c: the d-pad turns, faster while not stroking. */
    {
        const int still=p->swim_speed==0;
        const int32_t target=-p->swim_turn*(still?0x190:0x120);
        const int32_t accel=still?0x10:0x8;
        int32_t s=p->yaw_speed;
        if(target>0&&s<0) {s+=0x10;if(s>0x40)s=0x40;}
        else if(target<0&&s>0) {s-=0x10;if(s<-0x40)s=-0x40;}
        else s=approach(s,target,target?accel:0x10);
        p->yaw_speed=(int16_t)s;
        p->yaw=(uint16_t)(p->yaw+s);
    }
    /* func_ov002_020cd550: the pad pitches the nose; back rises. */
    if(p->swim_phase>0) {
        int32_t pitch=approach(p->pitch,-p->swim_pitch*0x3f00,p->pitch>0?0x80:0x100);
        if(p->grounded&&pitch>0) pitch=approach(pitch,0,0x100);
        p->pitch=(int16_t)pitch;
    }
    const uint8_t held=p->swim_stroke_held;
    switch(p->swim_phase) {
    case 0:   /* the dive slows down */
        p->swim_speed=approach(p->swim_speed,0,0x1e00);
        if(!p->swim_speed) {p->swim_phase=1;p->swim_timer=60;}
        break;
    case 1:   /* floating */
        p->swim_speed=approach(p->swim_speed,0,p->swim_timer?0xc0:0x300);
        if(swim_jump_out(p,jump,float_y))return;
        if(held) {p->swim_phase=2;p->swim_timer=30;p->swim_released=0;}
        break;
    case 2: { /* a stroke */
        const int32_t accel=p->swim_timer>=20?0x300:p->swim_timer<=8?0x900:0;
        p->swim_speed=approach(p->swim_speed,SWIM_STROKE,accel);
        if(p->swim_timer<20&&!held)p->swim_released=1;
        if(!p->swim_timer) {
            if(p->swim_released) {p->swim_phase=4;p->swim_timer=14;}
            else p->swim_phase=3;
        }
        break; }
    case 3:   /* the stroke held */
        p->swim_speed=approach(p->swim_speed,SWIM_HOLD,0xc0);
        if(swim_jump_out(p,jump,float_y))return;
        if(!held) {p->swim_phase=4;p->swim_timer=14;}
        break;
    default:  /* gliding out of a stroke */
        p->swim_speed=approach(p->swim_speed,0,0x180);
        if(swim_jump_out(p,jump,float_y))return;
        if(!p->swim_timer) {
            if(held) {p->swim_phase=2;p->swim_timer=30;p->swim_released=0;}
            else p->swim_phase=1;
        }
        break;
    }
    /* func_ov002_020cd218 and 020ceaf4: the speed along the pitch, plus a
     * drift up near the surface and down in deep water. */
    int32_t horizontal,vertical;
    if(!p->swim_phase) {horizontal=0;vertical=p->swim_speed;}
    else {
        horizontal=mul(p->swim_speed,angle_cos((uint16_t)p->pitch));
        vertical=-mul(p->swim_speed,angle_sin((uint16_t)p->pitch));
    }
    vertical+=float_y-p->feet.y<SWIM_DRIFT_DEPTH?SWIM_RISE:-SWIM_SINK;
    int32_t dx=mul(horizontal,angle_sin(p->yaw)),dz=mul(horizontal,angle_cos(p->yaw));
    if(p->knock_x||p->knock_z) {
        dx+=p->knock_x/2;dz+=p->knock_z/2;
        p->knock_x-=p->knock_x/8;p->knock_z-=p->knock_z/8;
    }
    p->velocity_y=vertical;
    p->moving=p->swim_speed!=0;p->running=0;
    uint32_t walls=0;
    for(int step=0;step<4;++step) {
        p->feet.x+=dx/4;p->feet.z+=dz/4;p->feet.y+=vertical/4;
        walls+=push_walls(p,w);
        int32_t floor=0;
        /* Touching ground within a sixteenth; the drift may still lift off it. */
        if(floor_query(w,p->feet.x,p->feet.z,p->feet.y+STEP,&floor,0,0,0,1)&&
           p->feet.y<=floor+ONE/16) {
            if(p->feet.y<floor) p->feet.y=floor;
            p->grounded=1;
            if(p->velocity_y<0)p->velocity_y=0;
        } else p->grounded=0;
    }
    p->swim_wall=walls!=0;
    /* func_ov002_020ce5f8: the float caps a rise; ground above it walks out. */
    if(p->feet.y>=float_y) {
        if(!p->grounded) {
            if(vertical>=0) {p->feet.y=float_y;p->velocity_y=0;}
        } else if(p->feet.y>float_y+SWIM_GROUND_EXIT) {
            int32_t floor=0;
            swim_leave(p);
            if(floor_query(w,p->feet.x,p->feet.z,p->feet.y+STEP,&floor,0,0,0,1)) p->feet.y=floor;
        }
    }
}
/* Find the wall still touching the capsule after the movement substeps. */
static const sm64ds_prism_t *climb_contact(const sm64ds_collision_t *w,
                                          const sat_vec3_t *feet,sat_vec3_t input) {
    const int bin=cell(w,feet->x,feet->z);
    if(bin<0) return 0;
    const sm64ds_prism_t *wall=0;
    int32_t best=0;
    for(uint32_t k=w->offsets[bin];k<w->offsets[bin+1];++k) {
        const sm64ds_prism_t *t=&w->prisms[w->indices[k]];
        if(t->normal.y< -ONE/2 || t->normal.y>=ONE/2 ||
           t->max.y<=feet->y+STEP || t->min.y>feet->y+HEIGHT || is_water_floor(w,t)) continue;
        const int32_t into=dot(input,t->normal);
        if(into>=best) continue;
        for(int s=0;s<2;++s) {
            const sat_vec3_t center={feet->x,feet->y+(s?HEIGHT-RADIUS:RADIUS),feet->z};
            const int32_t distance=dot(sub(center,t->origin),t->normal);
            /* Wall response adds 1/64 unit of separation. */
            if(distance< -RADIUS || distance>RADIUS+ONE/8) continue;
            const sat_vec3_t point={center.x-mul(distance,t->normal.x),
                                    center.y-mul(distance,t->normal.y),
                                    center.z-mul(distance,t->normal.z)};
            if(inside(t,point,RADIUS/2)) {
                wall=t;
                best=into;
                break;
            }
        }
    }
    return wall;
}

static void climb_start(sm64ds_player_t *p,const sm64ds_collision_t *w,sat_vec3_t input) {
    const sm64ds_prism_t *wall=climb_contact(w,&p->feet,input);
    if(!wall) return;
    const int32_t reach=RADIUS+CLIMB_REACH;
    const int32_t x=p->feet.x-mul(reach,wall->normal.x);
    const int32_t z=p->feet.z-mul(reach,wall->normal.z);
    int32_t top;
    uint8_t slippery;
    if(!floor_query(w,x,z,p->feet.y+CLIMB_MAX,&top,0,&slippery,0,1) ||
       slippery || top<=p->feet.y+STEP || top<wall->max.y-STEP) return;
    p->climb_top=(sat_vec3_t){x,top,z};
    p->climbing=1;
    p->climb_steps=0;
    p->velocity_y=0;
    p->grounded=0;
    ++p->climb_count;
}

static void climb_step(sm64ds_player_t *p,const sm64ds_collision_t *w,uint8_t jump) {
    if(jump || ++p->climb_steps>CLIMB_TIMEOUT) {
        p->climbing=0;
        p->climb_cooldown=CLIMB_COOLDOWN;
        if(jump) {
            p->velocity_y=3*ONE;
            ++p->jumps;
        }
        return;
    }
    p->feet.y+=CLIMB_SPEED;
    push_walls(p,w);
    if(p->feet.y>=p->climb_top.y) {
        p->feet=p->climb_top;
        push_walls(p,w);
        p->grounded=1;
        p->climbing=0;
        p->climb_cooldown=CLIMB_COOLDOWN;
    }
}

void sm64ds_player_step(sm64ds_player_t *p,const sm64ds_collision_t *w,
                        int32_t dx,int32_t dz,uint8_t jump,uint8_t run) {
    if(p->invuln)--p->invuln;
    if(p->dead) {
        if(--p->death_timer==0)sm64ds_player_reset(p);
        return;
    }
    ++p->ticks;
    if (jump) p->held_yaw=0;   /* unused; kept for ABI stability */
    if(p->swimming) {
        swim_step(p,w,jump);
        if(p->feet.y< -160*ONE)sm64ds_player_reset(p);
        return;
    }
    const sat_vec3_t movement={dx,0,dz};
    if(p->knock_x||p->knock_z) {
        dx+=p->knock_x;dz+=p->knock_z;
        p->knock_x-=p->knock_x/8;p->knock_z-=p->knock_z/8;
    }
    p->moving=dx!=0||dz!=0;p->running=p->moving&&run;
    if(p->climb_cooldown)--p->climb_cooldown;
    if(p->climbing) { climb_step(p,w,jump); return; }
    if(p->grounded) {
        int32_t cur_floor=0;sat_vec3_t cur_normal={0,ONE,0};uint8_t cur_slip=0;
        if(floor_query(w,p->feet.x,p->feet.z,p->feet.y+STEP,&cur_floor,&cur_normal,&cur_slip,0,1) &&
           cur_slip && p->feet.y<=cur_floor+STEP) {
            jump=0;
            int64_t hsq=((int64_t)cur_normal.x*cur_normal.x+
                         (int64_t)cur_normal.z*cur_normal.z)/ONE;
            if(hsq>ONE/256) {
                int64_t along=((int64_t)dx*cur_normal.x+(int64_t)dz*cur_normal.z)/ONE;
                if(along<0) {
                    dx-=(int32_t)(along*cur_normal.x/hsq);
                    dz-=(int32_t)(along*cur_normal.z/hsq);
                }
            }
            /* Smooth downhill slide along the slope's horizontal normal. */
            const int32_t slide=(ONE*5)/2;
            dx+=mul(slide,cur_normal.x);
            dz+=mul(slide,cur_normal.z);
        }
    }
    if(jump&&p->grounded) {p->velocity_y=3*ONE;p->grounded=0;++p->jumps;}
    int32_t old_y=p->feet.y;
    p->velocity_y-=ONE/8;
    if(p->velocity_y< -6*ONE)p->velocity_y=-6*ONE;
    const uint32_t wall_hits_before=p->wall_hits;
    /* Substeps keep every movement shorter than the collision radius. */
    for(int step=0;step<4;++step) {
        p->feet.x+=dx/4;p->feet.z+=dz/4;p->feet.y+=p->velocity_y/4;
        push_walls(p,w);
        int32_t floor=0;sat_vec3_t fnorm={0,ONE,0};uint8_t fslip=0;
        int32_t limit=old_y+(p->grounded?STEP:ONE/4);
        if(p->velocity_y<=0&&floor_query(w,p->feet.x,p->feet.z,limit,&floor,&fnorm,&fslip,0,1)&&
           p->feet.y<=floor+(p->grounded?STEP:ONE/8)) {
            if(!p->grounded) {
                ++p->landings;
                if(fslip) {
                    p->feet.x+=mul(ONE/2,fnorm.x);
                    p->feet.z+=mul(ONE/2,fnorm.z);
                }
            }
            p->feet.y=floor;p->velocity_y=0;p->grounded=1;
        } else p->grounded=0;
    }
    /* Deeper than the float under a water surface: swim. Shallower water is
     * waded through on its floor. */
    {
        int32_t surface=0;
        if(sm64ds_water_surface(w,p->feet.x,p->feet.z,p->feet.y,&surface)&&
           p->feet.y<surface-SWIM_FLOAT) swim_enter(p,surface);
        else if(w->climb_enabled && p->grounded && !p->climb_cooldown &&
                p->wall_hits!=wall_hits_before && (movement.x||movement.z)) {
            climb_start(p,w,movement);
        }
    }
    if(p->feet.y< -160*ONE)sm64ds_player_reset(p);
}
int32_t sm64ds_camera_fraction(const sm64ds_collision_t *w,
                               const sat_vec3_t *from,const sat_vec3_t *to) {
    int32_t best=ONE;
    sat_vec3_t delta=sub(*to,*from);
    for(uint16_t i=0;i<w->count;++i) {
        const sm64ds_prism_t *p=&w->prisms[i];
        if(is_water_floor(w,p))continue;   /* the camera sees through water */
        if((from->x<p->min.x&&to->x<p->min.x)||(from->x>p->max.x&&to->x>p->max.x)||
           (from->y<p->min.y&&to->y<p->min.y)||(from->y>p->max.y&&to->y>p->max.y)||
           (from->z<p->min.z&&to->z<p->min.z)||(from->z>p->max.z&&to->z>p->max.z))continue;
        int32_t a=dot(sub(*from,p->origin),p->normal),b=dot(sub(*to,p->origin),p->normal);
        if((a>=0&&b>=0)||(a<=0&&b<=0)||a==b)continue;
        int32_t t=(int32_t)((int64_t)a*ONE/(a-b));
        sat_vec3_t hit={from->x+mul(delta.x,t),from->y+mul(delta.y,t),from->z+mul(delta.z,t)};
        if(t<best&&inside(p,hit,ONE/16))best=t;
    }
    return best<ONE?(best>ONE/16?best-ONE/16:ONE/32):ONE;
}

uint8_t sm64ds_camera_select(const int32_t *clearance,uint8_t count,
                             uint8_t previous,int32_t minimum,int32_t restore) {
    if (!clearance || !count) return 0;
    if (clearance[0]>=restore) return 0;
    if (previous>0 && previous<count && clearance[previous]>=minimum) return previous;
    uint8_t best=0;
    for (uint8_t i=1;i<count;++i) {
        if (clearance[i]>=minimum) return i;
        if (clearance[i]>clearance[best]) best=i;
    }
    return best;
}
