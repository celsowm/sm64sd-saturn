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
/* Water: a CLPS with the water bit (word0 & 0x20). The DS player treats such a
 * floor as the water surface (St_Swim_Main), never as solid ground. */
#define WATER_SURFACE_PROBE (2*ONE)   /* vertical reach that keeps contact */
#define WATER_STEP_UP (8*ONE)         /* ledge a swimmer can climb out of */
#define WATER_SPEED (ONE/2)           /* swimming is half the walk speed */
static int is_slippery_floor(const sm64ds_collision_t *w,const sm64ds_prism_t *p) {
    if (p->normal.y<STEEP_NORMAL_Y) return 1;
    if (p->attribute<32u && (w->slippery_attrs&(1u<<p->attribute)) &&
        p->normal.y<SLIPPERY_NORMAL_Y) return 1;
    return 0;
}
static int is_water_floor(const sm64ds_collision_t *w,const sm64ds_prism_t *p) {
    return p->attribute<32u && (w->water_attrs&(1u<<p->attribute))!=0u;
}
static int floor_query(const sm64ds_collision_t *w,int32_t x,int32_t z,
                       int32_t ceiling,int32_t *height,sat_vec3_t *normal,
                       uint8_t *slippery,uint8_t *water) {
    int bin=cell(w,x,z),found=0;
    int32_t best=INT32_MIN;
    uint8_t best_slippery=0,best_water=0;
    if(bin<0)return 0;
    for(uint32_t k=w->offsets[bin];k<w->offsets[bin+1];++k) {
        const sm64ds_prism_t *p=&w->prisms[w->indices[k]];
        if(p->normal.y<ONE/2||x<p->min.x||x>p->max.x||z<p->min.z||z>p->max.z)continue;
        int32_t y=p->origin.y-(int32_t)(((int64_t)(x-p->origin.x)*p->normal.x+
                    (int64_t)(z-p->origin.z)*p->normal.z)/p->normal.y);
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
    return floor_query(w,x,z,ceiling,height,0,0,0);
}
int sm64ds_floor_normal(const sm64ds_collision_t *w,int32_t x,int32_t z,
                        int32_t ceiling,int32_t *height,sat_vec3_t *normal) {
    uint8_t slippery=0,water=0;
    if(!normal) return 0;
    if(!floor_query(w,x,z,ceiling,height,normal,&slippery,&water)) return 0;
    return water?0:1;   /* a water surface has no usable walk normal */
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
void sm64ds_player_reset(sm64ds_player_t *p) {
    p->feet=p->spawn;p->velocity_y=0;p->knock_x=p->knock_z=0;p->grounded=0;p->moving=0;p->running=0;
    p->swimming=0;
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
    p->velocity_y=3*ONE;p->grounded=0;
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
void sm64ds_player_step(sm64ds_player_t *p,const sm64ds_collision_t *w,
                        int32_t dx,int32_t dz,uint8_t jump,uint8_t run) {
    if(p->invuln)--p->invuln;
    if(p->dead) {
        if(--p->death_timer==0)sm64ds_player_reset(p);
        return;
    }
    ++p->ticks;
    if (jump) p->held_yaw=0;   /* unused; kept for ABI stability */
    if(p->knock_x||p->knock_z) {
        dx+=p->knock_x;dz+=p->knock_z;
        p->knock_x-=p->knock_x/8;p->knock_z-=p->knock_z/8;
    }
    p->moving=dx!=0||dz!=0;p->running=p->moving&&run;
    /* Water contact: the DS keeps the player at the water surface height while
     * swimming, so a CLPS with the water bit floats instead of being stood on.
     * The probe uses the ordinary STEP so a stroke above the surface leaves
     * the water instead of snapping back into it. */
    {
        int32_t surface=0;uint8_t water=0;
        if(floor_query(w,p->feet.x,p->feet.z,p->feet.y+STEP,&surface,0,0,&water) &&
           water && p->feet.y<=surface+STEP) {
            p->swimming=1;
            p->feet.y=surface;
            p->velocity_y=0;
            p->grounded=1;
        } else if(!water) p->swimming=0;
    }
    if(p->swimming) {
        dx=mul(dx,WATER_SPEED);dz=mul(dz,WATER_SPEED);
    }
    if(p->grounded && !p->swimming) {
        int32_t cur_floor=0;sat_vec3_t cur_normal={0,ONE,0};uint8_t cur_slip=0;
        if(floor_query(w,p->feet.x,p->feet.z,p->feet.y+STEP,&cur_floor,&cur_normal,&cur_slip,0) &&
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
    /* Swimming floats at the surface: no fall gravity is applied, and the
     * step-up room is larger so a shore can be climbed out of. */
    int32_t step_up=(p->swimming?WATER_STEP_UP:STEP);
    if(!p->swimming) {
        p->velocity_y-=ONE/8;
        if(p->velocity_y< -6*ONE)p->velocity_y=-6*ONE;
    }
    /* Substeps keep every movement shorter than the collision radius. */
    for(int step=0;step<4;++step) {
        p->feet.x+=dx/4;p->feet.z+=dz/4;p->feet.y+=p->velocity_y/4;
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
                    } else ++p->wall_hits;
                }
            }
        }
        int32_t floor=0;sat_vec3_t fnorm={0,ONE,0};uint8_t fslip=0,fwater=0;
        int32_t limit=old_y+(p->grounded?step_up:ONE/4);
        if(p->velocity_y<=0&&floor_query(w,p->feet.x,p->feet.z,limit,&floor,&fnorm,&fslip,&fwater)&&
           p->feet.y<=floor+(p->grounded?step_up:ONE/8)) {
            if(!p->grounded) {
                ++p->landings;
                if(fslip) {
                    p->feet.x+=mul(ONE/2,fnorm.x);
                    p->feet.z+=mul(ONE/2,fnorm.z);
                }
            }
            p->feet.y=floor;p->velocity_y=0;p->grounded=1;
            p->swimming=(uint8_t)(fwater?1:0);
        } else p->grounded=0;
    }
    if(p->feet.y< -160*ONE)sm64ds_player_reset(p);
}
int32_t sm64ds_camera_fraction(const sm64ds_collision_t *w,
                               const sat_vec3_t *from,const sat_vec3_t *to) {
    int32_t best=ONE;
    sat_vec3_t delta=sub(*to,*from);
    for(uint16_t i=0;i<w->count;++i) {
        const sm64ds_prism_t *p=&w->prisms[i];
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
