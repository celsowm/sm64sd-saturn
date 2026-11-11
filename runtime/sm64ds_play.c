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
int sm64ds_floor(const sm64ds_collision_t *w,int32_t x,int32_t z,
                 int32_t ceiling,int32_t *height) {
    int bin=cell(w,x,z),found=0;
    int32_t best=INT32_MIN;
    if(bin<0)return 0;
    for(uint32_t k=w->offsets[bin];k<w->offsets[bin+1];++k) {
        const sm64ds_prism_t *p=&w->prisms[w->indices[k]];
        if(p->normal.y<ONE/2||x<p->min.x||x>p->max.x||z<p->min.z||z>p->max.z)continue;
        int32_t y=p->origin.y-(int32_t)(((int64_t)(x-p->origin.x)*p->normal.x+
                    (int64_t)(z-p->origin.z)*p->normal.z)/p->normal.y);
        if(y>ceiling||y<=best)continue;
        if(inside(p,(sat_vec3_t){x,y,z},ONE/32)) {best=y;found=1;}
    }
    if(found)*height=best;
    return found;
}
void sm64ds_player_reset(sm64ds_player_t *p) {
    p->feet=p->spawn;p->velocity_y=0;p->grounded=0;p->moving=0;p->running=0;++p->resets;
}
void sm64ds_player_step(sm64ds_player_t *p,const sm64ds_collision_t *w,
                        int32_t dx,int32_t dz,uint8_t jump,uint8_t run) {
    ++p->ticks;
    p->moving=dx!=0||dz!=0;p->running=p->moving&&run;
    if(jump&&p->grounded) {p->velocity_y=3*ONE;p->grounded=0;++p->jumps;}
    int32_t old_y=p->feet.y;
    p->velocity_y-=ONE/8;
    if(p->velocity_y< -6*ONE)p->velocity_y=-6*ONE;
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
        int32_t floor;
        int32_t limit=old_y+(p->grounded?STEP:ONE/4);
        if(p->velocity_y<=0&&sm64ds_floor(w,p->feet.x,p->feet.z,limit,&floor)&&
           p->feet.y<=floor+(p->grounded?STEP:ONE/8)) {
            if(!p->grounded)++p->landings;
            p->feet.y=floor;p->velocity_y=0;p->grounded=1;
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
