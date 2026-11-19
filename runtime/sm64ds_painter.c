#include "sm64ds_painter.h"
#include <stddef.h>

/* Q8 screen coordinates keep clipping intermediates within signed 64 bits
 * for the SDK's drawable coordinate range. */
typedef struct { int32_t x,y; } point_t;
typedef struct { point_t p[3]; int32_t inverse[3]; int64_t area; } triangle_t;

int sm64ds_painter_bucket_plan(const uint32_t *keys,uint16_t count,uint8_t group,
                               sm64ds_painter_bucket_plan_t *out) {
    struct group { uint32_t low,high,count;uint8_t id; } groups[8];
    unsigned n=0;uint32_t live=0;
    if(!keys || !out) return 0;
    for(uint16_t i=0;i<count;++i) {
        uint32_t key=keys[i];
        if(key==UINT32_MAX) continue;
        uint8_t id=(uint8_t)(key>>24);uint32_t depth=key&0xffffffu;
        unsigned g=0;while(g<n && groups[g].id!=id) ++g;
        if(g==n) {
            if(n==8) return 0;
            groups[n++]=(struct group){depth,depth,0,id};
        }
        if(depth<groups[g].low)groups[g].low=depth;
        if(depth>groups[g].high)groups[g].high=depth;
        ++groups[g].count;++live;
    }
    for(unsigned g=0;g<n;++g) if(groups[g].id==group) {
        uint32_t buckets=n==1?1024u:1u+((1024u-n)*groups[g].count)/live;
        uint32_t span=groups[g].high-groups[g].low;uint8_t shift=0;
        while((span>>shift)>=buckets) ++shift;
        *out=(sm64ds_painter_bucket_plan_t){groups[g].low,groups[g].high,shift};
        return 1;
    }
    return 0;
}

static int64_t side(point_t a,point_t b,point_t p) {
    return (int64_t)(b.x-a.x)*(p.y-a.y)-(int64_t)(b.y-a.y)*(p.x-a.x);
}

static int screen_edges_separate(const sm64ds_painter_vertex_t a[3],
                                 const sm64ds_painter_vertex_t b[3],uint16_t padding) {
    int64_t area=(int64_t)(a[1].x-a[0].x)*(a[2].y-a[0].y)-
                 (int64_t)(a[1].y-a[0].y)*(a[2].x-a[0].x);
    if(!area) return 0;
    int sign=area>0?1:-1;
    for(unsigned i=0;i<3;++i) {
        const sm64ds_painter_vertex_t *p=&a[i],*q=&a[(i+1)%3];
        int32_t dx=(int32_t)q->x-p->x,dy=(int32_t)q->y-p->y;
        int64_t margin=(int64_t)((dx<0?-dx:dx)+(dy<0?-dy:dy))*padding;
        int separated=1;
        for(unsigned j=0;j<3;++j) {
            int64_t s=((int64_t)dx*(b[j].y-p->y)-(int64_t)dy*(b[j].x-p->x))*sign;
            if(s>=-margin) { separated=0;break; }
        }
        if(separated) return 1;
    }
    return 0;
}

int sm64ds_painter_triangles_separated(const sm64ds_painter_vertex_t a[3],
                                       const sm64ds_painter_vertex_t b[3],
                                       uint16_t padding) {
    if(!a || !b) return 0;
    int64_t area_a=(int64_t)(a[1].x-a[0].x)*(a[2].y-a[0].y)-
                   (int64_t)(a[1].y-a[0].y)*(a[2].x-a[0].x);
    int64_t area_b=(int64_t)(b[1].x-b[0].x)*(b[2].y-b[0].y)-
                   (int64_t)(b[1].y-b[0].y)*(b[2].x-b[0].x);
    if(!area_a || !area_b) return 0;
    return screen_edges_separate(a,b,padding) || screen_edges_separate(b,a,padding);
}

static int triangle_init(triangle_t *out,const sm64ds_painter_vertex_t in[3]) {
    for(unsigned i=0;i<3;++i) {
        if(in[i].x < -1024 || in[i].x > 1023 || in[i].y < -1024 || in[i].y > 1023 ||
           in[i].depth < 65536 || in[i].depth > 0x3fffffff) return 0;
        out->p[i]=(point_t){(int32_t)in[i].x*256,(int32_t)in[i].y*256};
        out->inverse[i]=(int32_t)(((int64_t)1<<36)/in[i].depth);
    }
    out->area=side(out->p[0],out->p[1],out->p[2]);
    return out->area!=0;
}

static point_t intersect(point_t a,point_t b,int64_t da,int64_t db) {
    int64_t denominator=da-db;
    return (point_t){a.x+(int32_t)((int64_t)(b.x-a.x)*da/denominator),
                     a.y+(int32_t)((int64_t)(b.y-a.y)*da/denominator)};
}

static int push(point_t *out,unsigned *count,point_t p) {
    if(*count && out[*count-1].x==p.x && out[*count-1].y==p.y) return 1;
    if(*count==8) return 0;
    out[(*count)++]=p;
    return 1;
}

static unsigned clip(const point_t *in,unsigned count,point_t *out,point_t a,point_t b,int sign) {
    if(!count) return 0;
    unsigned n=0;
    point_t prev=in[count-1];int64_t dp=side(a,b,prev)*sign;
    for(unsigned i=0;i<count;++i) {
        point_t next=in[i];int64_t dn=side(a,b,next)*sign;
        if((dp>=0)!=(dn>=0) && !push(out,&n,intersect(prev,next,dp,dn))) return 9;
        if(dn>=0 && !push(out,&n,next)) return 9;
        prev=next;dp=dn;
    }
    if(n>1 && out[0].x==out[n-1].x && out[0].y==out[n-1].y) --n;
    return n;
}

static int32_t inverse_at(const triangle_t *t,point_t p) {
    int64_t u=side(t->p[1],t->p[2],p);
    int64_t v=side(t->p[2],t->p[0],p);
    int64_t w=t->area-u-v;
    return (int32_t)((u*t->inverse[0]+v*t->inverse[1]+w*t->inverse[2])/t->area);
}

static int64_t absolute(int64_t x) { return x<0?-x:x; }

/* Bound depth-plane movement under a conservative 1/16-pixel clipping
 * position error. Thin projected triangles can have very steep depth planes;
 * a fixed relative-depth tolerance alone is not sufficient for them. */
static int64_t rounding_margin(const triangle_t *t) {
    int64_t gx=(int64_t)t->inverse[0]*(t->p[1].y-t->p[2].y)+
               (int64_t)t->inverse[1]*(t->p[2].y-t->p[0].y)+
               (int64_t)t->inverse[2]*(t->p[0].y-t->p[1].y);
    int64_t gy=(int64_t)t->inverse[0]*(t->p[2].x-t->p[1].x)+
               (int64_t)t->inverse[1]*(t->p[0].x-t->p[2].x)+
               (int64_t)t->inverse[2]*(t->p[1].x-t->p[0].x);
    return 16*(absolute(gx)+absolute(gy))/absolute(t->area)+3;
}

sm64ds_painter_relation_t sm64ds_painter_compare_triangles(
    const sm64ds_painter_vertex_t a[3],const sm64ds_painter_vertex_t b[3]) {
    if(!a || !b) return SM64DS_PAINTER_AMBIGUOUS;
    triangle_t ta,tb;
    if(!triangle_init(&ta,a) || !triangle_init(&tb,b)) return SM64DS_PAINTER_AMBIGUOUS;
    point_t buffers[2][8];
    for(unsigned i=0;i<3;++i) buffers[0][i]=ta.p[i];
    unsigned n=3,which=0;
    int sign=tb.area>0?1:-1;
    for(unsigned edge=0;edge<3;++edge) {
        n=clip(buffers[which],n,buffers[which^1],tb.p[edge],tb.p[(edge+1)%3],sign);
        if(n>8) return SM64DS_PAINTER_AMBIGUOUS;
        which^=1;
    }
    if(n<3) return SM64DS_PAINTER_DISJOINT;
    int behind=0,in_front=0;
    int64_t rounding=rounding_margin(&ta)+rounding_margin(&tb);
    for(unsigned i=0;i<n;++i) {
        int32_t ai=inverse_at(&ta,buffers[which][i]);
        int32_t bi=inverse_at(&tb,buffers[which][i]);
        int64_t margin=(ai+bi)/1024+rounding;
        if(bi-ai>margin) behind=1;
        else if(ai-bi>margin) in_front=1;
        else return SM64DS_PAINTER_AMBIGUOUS;
        if(behind && in_front) return SM64DS_PAINTER_AMBIGUOUS;
    }
    return behind?SM64DS_PAINTER_A_BEHIND:SM64DS_PAINTER_A_IN_FRONT;
}
