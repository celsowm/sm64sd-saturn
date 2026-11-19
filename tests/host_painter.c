#include <assert.h>
#include "sm64ds_painter.h"

#define V(x,y,z) {(x),(y),(z)*65536}
int main(void) {
    const sm64ds_painter_vertex_t back[3]={V(0,0,20),V(20,0,20),V(0,20,20)};
    const sm64ds_painter_vertex_t front[3]={V(0,0,10),V(20,0,10),V(0,20,10)};
    const sm64ds_painter_vertex_t reverse[3]={V(0,20,10),V(20,0,10),V(0,0,10)};
    const sm64ds_painter_vertex_t distant[3]={V(50,50,10),V(70,50,10),V(50,70,10)};
    const sm64ds_painter_vertex_t crossing[3]={V(0,0,5),V(20,0,30),V(0,20,30)};
    const sm64ds_painter_vertex_t degenerate[3]={V(0,0,10),V(1,1,10),V(2,2,10)};
    const sm64ds_painter_vertex_t thin[3]={V(22,5,34),V(23,-19,108),V(17,94,26)};
    const sm64ds_painter_vertex_t thin_crossing[3]={V(-73,61,130),V(88,56,22),V(52,-36,96)};
    const sm64ds_painter_vertex_t extreme[3]={V(-1024,-1024,1),V(1023,-1024,1000),V(-1024,1023,1000)};
    const sm64ds_painter_vertex_t path[3]={V(6,24,64),V(72,47,56),V(32,92,44)};
    const sm64ds_painter_vertex_t adjacent[3]={V(42,-41,116),V(257,-12,86),V(935,794,10)};
    const sm64ds_painter_vertex_t edge[3]={V(20,0,10),V(20,20,10),V(0,20,10)};
    assert(sm64ds_painter_compare_triangles(back,front)==SM64DS_PAINTER_A_BEHIND);
    assert(sm64ds_painter_compare_triangles(front,back)==SM64DS_PAINTER_A_IN_FRONT);
    assert(sm64ds_painter_compare_triangles(back,reverse)==SM64DS_PAINTER_A_BEHIND);
    assert(sm64ds_painter_compare_triangles(back,distant)==SM64DS_PAINTER_DISJOINT);
    assert(sm64ds_painter_compare_triangles(back,crossing)==SM64DS_PAINTER_AMBIGUOUS);
    assert(sm64ds_painter_compare_triangles(back,back)==SM64DS_PAINTER_AMBIGUOUS);
    assert(sm64ds_painter_compare_triangles(back,degenerate)==SM64DS_PAINTER_AMBIGUOUS);
    assert(sm64ds_painter_compare_triangles(thin,thin_crossing)==SM64DS_PAINTER_AMBIGUOUS);
    (void)sm64ds_painter_compare_triangles(extreme,back);
    assert(sm64ds_painter_triangles_separated(path,adjacent,2));
    assert(!sm64ds_painter_triangles_separated(back,edge,2));
    assert(!sm64ds_painter_triangles_separated(back,degenerate,2));
    const uint32_t keys[]={0x01000000u,0x01001000u,0x02000032u,UINT32_MAX};
    sm64ds_painter_bucket_plan_t plan;
    assert(sm64ds_painter_bucket_plan(keys,4,1,&plan));
    assert(plan.low==0 && plan.high==4096 && plan.shift==3);
    assert(sm64ds_painter_bucket_plan(keys,2,1,&plan) && plan.shift==3);
    assert(!sm64ds_painter_bucket_plan(keys,4,3,&plan));
    assert(sm64ds_painter_compare_triangles(0,front)==SM64DS_PAINTER_AMBIGUOUS);
    return 0;
}
