/* visual-diagnostic depth experiments; textually included by castle.c. */
#if SM64DS_VISUAL_DIAGNOSTICS && SM64DS_DIAG_FAR_DEPTH_COUNT > 0
#if SM64DS_DIAG_GEOMETRIC_DEPTH || SM64DS_DIAG_PAIR_DEPTH
static sm64ds_painter_vertex_t painter_vertex(sat_projected_vertex_t p) {
    return (sm64ds_painter_vertex_t){p.x,p.y,p.w};
}
#endif

#if SM64DS_DIAG_SUPPORT_DEPTH
#if SM64DS_DIAG_SUPPORT_AUTO && !SM64DS_DIAG_SUPPORT_GUARD
#error "Automatic support-depth diagnostics require the scenery guard"
#endif
#if SM64DS_DIAG_SLOPED_SUPPORT && (!SM64DS_DIAG_SUPPORT_AUTO || !defined(CASTLE_SUPPORT_PLANE_LIST_AVAILABLE))
#error "Sloped support diagnostics require auto mode and regenerated support-plane metadata"
#endif
#if SM64DS_DIAG_SUPPORT_GUARD
volatile struct {
    uint32_t count;
    struct { uint16_t face,queue; sat_quad2_t projected; } blockers[8];
    uint32_t mapped,expected;
    uint32_t calls,potential,map_failed,changes,blocked;
    uint32_t profile_calls,profile_ticks_sum,profile_ticks_max,profile_ticks_last;
} g_sm64ds_support_diag;
static int32_t diagnostic_support_cache[CAP];

static int diagnostic_same_support(uint16_t q,int32_t y,uint32_t target_face) {
#if SM64DS_DIAG_SUPPORT_AUTO && defined(CASTLE_FACE_SOURCE_AVAILABLE)
    int face=diagnostic_support_cache[q];
    if(face<0 || castle_face_source[face]!=castle_face_source[target_face]) return 0;
    const uint16_t *is=&ci[(uint32_t)face*4u];
    return cv[is[0]].y==y && cv[is[1]].y==y && cv[is[2]].y==y && cv[is[3]].y==y;
#else
    (void)target_face;
    if(diagnostic_support_cache[q]!=-1) {
        int face=diagnostic_support_cache[q];
        return face>=0 && cv[ci[(uint32_t)face*4u]].y==y;
    }
    const sat_quad2_t *quad=&scene.faces.entries[q].projected;
    for(uint32_t f=SM64DS_DIAG_FAR_DEPTH_FIRST;
        f<(uint32_t)SM64DS_DIAG_FAR_DEPTH_FIRST+SM64DS_DIAG_FAR_DEPTH_COUNT && f<CF;++f) {
        const uint16_t *is=&ci[f*4u];
        int32_t fy=cv[is[0]].y;
        if(cv[is[1]].y!=fy || cv[is[2]].y!=fy || cv[is[3]].y!=fy) continue;
        unsigned k;
        for(k=0;k<4;++k) if(quad->x[k]!=cp[is[k]].x || quad->y[k]!=cp[is[k]].y) break;
        if(k==4) { diagnostic_support_cache[q]=(int32_t)f;return fy==y; }
    }
    diagnostic_support_cache[q]=-2;
    return 0;
#endif
}

#if SM64DS_DIAG_SUPPORT_AUTO && defined(CASTLE_FACE_SOURCE_AVAILABLE)
static uint16_t diagnostic_support_face_queue[CF];
/* Instance submission preserves face order. Associate each queued entry with
 * its source face only when both its four coordinates and its original
 * painter key agree; reject the entire experiment if any entry is unmapped. */
static int diagnostic_map_castle(uint16_t first,uint16_t end) {
    uint16_t cursor=first;
    for(uint32_t face=0;face<CF;++face) diagnostic_support_face_queue[face]=0xffffu;
    for(uint32_t face=0;face<CF && cursor<end;++face) {
        const uint16_t *is=&ci[face*4u];
        sat_scene3d_face_t *entry=&scene.faces.entries[cursor];
        int64_t sum=0;
        unsigned k;
        for(k=0;k<4;++k) {
            if(entry->projected.x[k]!=cp[is[k]].x || entry->projected.y[k]!=cp[is[k]].y) break;
            sum+=cp[is[k]].w;
        }
        if(k!=4) continue;
        int64_t depth=sum>0?sum>>6:0;
        if(depth>0xfffffe) depth=0xfffffe;
        uint32_t key=((255u-castle.instance.pass)<<24)|(uint32_t)depth;
        if(scene.faces.keys[cursor]!=key) continue;
        diagnostic_support_cache[cursor]=(int32_t)face;
        diagnostic_support_face_queue[face]=cursor++;
    }
    g_sm64ds_support_diag.mapped=cursor-first;
    g_sm64ds_support_diag.expected=end-first;
    return cursor==end;
}
#endif

static int diagnostic_not_near_clipped(const sat_scene3d_face_t *face) {
    if(!face->projected_safe) {
        for(unsigned k=0;k<4;++k) {
            sat_fx16_t depth;
            if(sat_scene3d_faces_depth(&scene.faces,&face->world.v[k],&depth)!=SAT_OK ||
               depth<scene.faces.near_depth+ONE/256) return 0;
        }
    }
    return 1;
}

static int diagnostic_separate_triangles(const sat_scene3d_face_t *a,
                                         const sat_scene3d_face_t *b) {
    const sat_quad2_t *qa=&a->projected,*qb=&b->projected;
    if(qa->x[2]!=qa->x[3] || qa->y[2]!=qa->y[3] ||
       qb->x[2]!=qb->x[3] || qb->y[2]!=qb->y[3]) return 0;
    sm64ds_painter_vertex_t ta[3],tb[3];
    for(unsigned k=0;k<3;++k) {
        ta[k]=(sm64ds_painter_vertex_t){qa->x[k],qa->y[k],ONE};
        tb[k]=(sm64ds_painter_vertex_t){qb->x[k],qb->y[k],ONE};
    }
    return sm64ds_painter_triangles_separated(ta,tb,2);
}

static int diagnostic_quad_outside(const sat_quad2_t *quad,
                                   int x0,int x1,int y0,int y1) {
    int lx=quad->x[0],hx=lx,ly=quad->y[0],hy=ly;
    for(unsigned k=1;k<4;++k) {
        if(quad->x[k]<lx)lx=quad->x[k];
        if(quad->x[k]>hx)hx=quad->x[k];
        if(quad->y[k]<ly)ly=quad->y[k];
        if(quad->y[k]>hy)hy=quad->y[k];
    }
    return hx<x0-2 || lx>x1+2 || hy<y0-2 || ly>y1+2;
}

/* Match the SDK's near-clipped fallback before rejecting a depth change.
 * Project the original too: a textured face can be drawn whole if its
 * corners clear the near plane. Any error remains a conservative blocker. */
static int diagnostic_clipped_outside(const sat_scene3d_face_t *face,
                                      int x0,int x1,int y0,int y1) {
    sat_quad2_t projected;
    sat_result_t result=sat_project_quad(&scene.faces.view_proj,&face->world,&projected);
    if(result==SAT_OK && !diagnostic_quad_outside(&projected,x0,x1,y0,y1)) return 0;
    if(result!=SAT_OK && result!=SAT_ERR_UNSUPPORTED) return 0;
    sat_quad3_t pieces[4];uint8_t count=0;
    if(sat_clip_quad_near(&face->world,&scene.faces.eye,&scene.faces.forward,
                          scene.faces.near_depth,pieces,&count)!=SAT_OK) return 0;
    for(uint8_t i=0;i<count;++i) {
        result=sat_project_quad(&scene.faces.view_proj,&pieces[i],&projected);
        if(result==SAT_ERR_UNSUPPORTED) continue; /* SDK skips this piece. */
        if(result!=SAT_OK || !diagnostic_quad_outside(&projected,x0,x1,y0,y1)) return 0;
    }
    return 1;
}


#endif
/* Diagnostic proof for a flat plane: when the camera and every actor
 * vertex are above the plane, a ray to the actor cannot hit that plane
 * first. This does not establish the ground's order against other scenery. */
#if SM64DS_DIAG_SLOPED_SUPPORT
#define SUPPORT_FACE_COUNT CASTLE_SUPPORT_PLANE_COUNT
#define SUPPORT_FACE_AT(i) ((uint32_t)castle_support_faces[i])
#elif SM64DS_DIAG_SUPPORT_AUTO && defined(CASTLE_FLAT_FACE_LIST_AVAILABLE)
#define SUPPORT_FACE_COUNT CASTLE_FLAT_FACE_COUNT
#define SUPPORT_FACE_AT(i) ((uint32_t)castle_flat_faces[i])
#else
#define SUPPORT_FACE_COUNT SM64DS_DIAG_FAR_DEPTH_COUNT
#define SUPPORT_FACE_AT(i) ((uint32_t)SM64DS_DIAG_FAR_DEPTH_FIRST+(i))
#endif
#if SM64DS_DIAG_SLOPED_SUPPORT
/* The minimum actor dot product depends on the normal, not the plane's
 * position. Many split faces share a normal, so reuse that exact value for
 * the duration of this call. Hash collisions simply recompute it. */
static struct {
    sat_vec3_t normal;
    int64_t minimum;
    uint8_t valid;
} support_normal_cache[64];
static sat_vec3_t support_actor_min,support_actor_max;

static int diagnostic_same_sloped_support(uint16_t q,uint32_t scan,uint32_t target) {
    int other=diagnostic_support_cache[q];
    if(other<0 || castle_face_source[other]!=castle_face_source[target]) return 0;
    const sat_vec3_t n=castle_support_normals[scan],p=cv[ci[target*4u]];
    const uint16_t *is=&ci[(uint32_t)other*4u];
    for(unsigned k=0;k<4;++k) {
        sat_vec3_t v=cv[is[k]];
        int64_t side=((int64_t)v.x-p.x)*n.x+((int64_t)v.y-p.y)*n.y+
                     ((int64_t)v.z-p.z)*n.z;
        if(side < -((int64_t)ONE*ONE/256) || side > ((int64_t)ONE*ONE/256)) return 0;
    }
    return 1;
}

static int diagnostic_above_sloped_plane(uint32_t scan,uint32_t f) {
    const sat_vec3_t n=castle_support_normals[scan],p=cv[ci[f*4u]];
    const sat_vec3_t eye=camera.eye;
    int64_t plane=(int64_t)p.x*n.x+(int64_t)p.y*n.y+(int64_t)p.z*n.z;
    int64_t side=(int64_t)eye.x*n.x+(int64_t)eye.y*n.y+(int64_t)eye.z*n.z-plane;
    if(side<=((int64_t)ONE*ONE/256)) return 0;
    /* The minimum over the actor's bounding box is a conservative lower
     * bound for every vertex. Only scan vertices when it cannot prove the
     * entire box lies above the support plane. */
    int64_t bound=(int64_t)(n.x>=0?support_actor_min.x:support_actor_max.x)*n.x+
                  (int64_t)(n.y>=0?support_actor_min.y:support_actor_max.y)*n.y+
                  (int64_t)(n.z>=0?support_actor_min.z:support_actor_max.z)*n.z;
    if(bound-plane>=((int64_t)ONE*ONE/1024)) return 1;
    unsigned slot=((uint32_t)n.x*17u+(uint32_t)n.y*31u+(uint32_t)n.z*47u)&63u;
    if(support_normal_cache[slot].valid &&
       support_normal_cache[slot].normal.x==n.x &&
       support_normal_cache[slot].normal.y==n.y &&
       support_normal_cache[slot].normal.z==n.z)
        return support_normal_cache[slot].minimum-plane>=((int64_t)ONE*ONE/1024);
    int64_t minimum=INT64_MAX;
    for(unsigned group=0;group<2;++group) {
        if(!(SM64DS_DIAG_OBJECTS&(group?8:4))) continue;
        const sat_vec3_t *vertices=group?hw:world_vertices;
        unsigned count=group?HN:N;
        for(unsigned v=0;v<count;++v) {
            side=(int64_t)vertices[v].x*n.x+(int64_t)vertices[v].y*n.y+
                 (int64_t)vertices[v].z*n.z;
            if(side<minimum) minimum=side;
        }
    }
    support_normal_cache[slot].normal=n;
    support_normal_cache[slot].minimum=minimum;
    support_normal_cache[slot].valid=1;
    return minimum-plane>=((int64_t)ONE*ONE/1024);
}

#endif
static void diagnostic_support_depth(uint16_t first,uint16_t end,
                                     uint16_t actor_first,uint16_t actor_end) {
#if SM64DS_DIAG_SUPPORT_GUARD
    /* Retain the first blockers across calls: WRAM captures can occur between
     * frames, after a per-call counter would already have been cleared. */
    g_sm64ds_support_diag.mapped=0;g_sm64ds_support_diag.expected=0;
    ++g_sm64ds_support_diag.calls;
#endif
    if(scene.faces.projected_entries || actor_first==actor_end) return;
#if SM64DS_DIAG_SLOPED_SUPPORT
    for(unsigned i=0;i<64;++i) support_normal_cache[i].valid=0;
#endif
    uint8_t group=(uint8_t)(255u-castle.instance.pass);
    uint32_t actor_max=0;int has_actor=0;
    int ax0=32767,ax1=-32768,ay0=32767,ay1=-32768;
    for(uint16_t a=actor_first;a<actor_end;++a) {
        sat_scene3d_face_t *entry=&scene.faces.entries[a];
        if(!entry->projected_safe) return;
        uint32_t key=scene.faces.keys[a];
        if((key>>24)==group) {
            uint32_t depth=key&0xffffffu;
            if(depth>actor_max)actor_max=depth;
            has_actor=1;
        }
        for(unsigned k=0;k<4;++k) {
            if(entry->projected.x[k]<ax0)ax0=entry->projected.x[k];
            if(entry->projected.x[k]>ax1)ax1=entry->projected.x[k];
            if(entry->projected.y[k]<ay0)ay0=entry->projected.y[k];
            if(entry->projected.y[k]>ay1)ay1=entry->projected.y[k];
        }
    }
    if(!has_actor) return;
    int32_t actor_lowest=INT32_MAX;
#if SM64DS_DIAG_SLOPED_SUPPORT
    support_actor_min=(sat_vec3_t){INT32_MAX,INT32_MAX,INT32_MAX};
    support_actor_max=(sat_vec3_t){INT32_MIN,INT32_MIN,INT32_MIN};
    for(unsigned group_index=0;group_index<2;++group_index) {
        if(!(SM64DS_DIAG_OBJECTS&(group_index?8:4))) continue;
        const sat_vec3_t *vertices=group_index?hw:world_vertices;
        unsigned count=group_index?HN:N;
        for(unsigned v=0;v<count;++v) {
            sat_vec3_t p=vertices[v];
            if(p.x<support_actor_min.x)support_actor_min.x=p.x;
            if(p.y<support_actor_min.y)support_actor_min.y=p.y;
            if(p.z<support_actor_min.z)support_actor_min.z=p.z;
            if(p.x>support_actor_max.x)support_actor_max.x=p.x;
            if(p.y>support_actor_max.y)support_actor_max.y=p.y;
            if(p.z>support_actor_max.z)support_actor_max.z=p.z;
        }
    }
    actor_lowest=support_actor_min.y;
#else
    if(SM64DS_DIAG_OBJECTS&4) for(unsigned v=0;v<N;++v)
        if(world_vertices[v].y<actor_lowest) actor_lowest=world_vertices[v].y;
    if(SM64DS_DIAG_OBJECTS&8) for(unsigned v=0;v<HN;++v)
        if(hw[v].y<actor_lowest) actor_lowest=hw[v].y;
#endif

    /* Avoid mapping the entire castle queue if no flat projected face can
     * both overlap the actor and sort after it. */
    int possible=0;
    for(uint32_t scan=0;scan<SUPPORT_FACE_COUNT;++scan) {
        uint32_t f=SUPPORT_FACE_AT(scan);if(f>=CF) continue;
        const uint16_t *is=&ci[f*4u];int32_t y=cv[is[0]].y;
        int flat=cv[is[1]].y==y && cv[is[2]].y==y && cv[is[3]].y==y;
        if(flat && (camera.eye.y<=y || actor_lowest<y)) continue;
#if !SM64DS_DIAG_SLOPED_SUPPORT
        if(!flat) continue;
#endif
        int x0=cp[is[0]].x,x1=x0,y0=cp[is[0]].y,y1=y0;int64_t sum=0;
        for(unsigned k=0;k<4;++k) {
            if(cp[is[k]].x<x0)x0=cp[is[k]].x;
            if(cp[is[k]].x>x1)x1=cp[is[k]].x;
            if(cp[is[k]].y<y0)y0=cp[is[k]].y;
            if(cp[is[k]].y>y1)y1=cp[is[k]].y;
            sum+=cp[is[k]].w;
        }
        if(x1<ax0-1 || x0>ax1+1 || y1<ay0-1 || y0>ay1+1) continue;
        if(sum<0 || (uint64_t)(sum/64)<actor_max) {
#if SM64DS_DIAG_SLOPED_SUPPORT
            if(!flat && !diagnostic_above_sloped_plane(scan,f)) continue;
#endif
            possible=1;break;
        }
    }
    if(!possible) return;
#if SM64DS_DIAG_SUPPORT_GUARD
    ++g_sm64ds_support_diag.potential;
    for(uint16_t q=0;q<actor_first;++q) {
        diagnostic_support_cache[q]=-1;
    }
#if SM64DS_DIAG_SUPPORT_AUTO && defined(CASTLE_FACE_SOURCE_AVAILABLE)
    if(!diagnostic_map_castle(first,end)) { ++g_sm64ds_support_diag.map_failed;return; }
#elif SM64DS_DIAG_SUPPORT_AUTO
    return; /* Regenerate castle_scene with source metadata first. */
#endif
    sm64ds_painter_bucket_plan_t bucket;
    if(!sm64ds_painter_bucket_plan(scene.faces.keys,scene.faces.count,group,&bucket)) return;
#endif
    for(uint32_t scan=0;scan<SUPPORT_FACE_COUNT;++scan) {
        uint32_t f=SUPPORT_FACE_AT(scan);if(f>=CF) continue;
#if SM64DS_DIAG_SUPPORT_AUTO && defined(CASTLE_FACE_SOURCE_AVAILABLE)
        /* This face cannot need a key change if it is absent from the queue
         * or already sorts at least as far away as every actor face. */
        uint16_t mapped=diagnostic_support_face_queue[f];
        if(mapped==0xffffu || (scene.faces.keys[mapped]&0xffffffu)>=actor_max) continue;
#endif
        const uint16_t *is=&ci[f*4u];
        int32_t y=cv[is[0]].y;
        int flat=cv[is[1]].y==y && cv[is[2]].y==y && cv[is[3]].y==y;
        if(flat && camera.eye.y<=y) continue;
#if !SM64DS_DIAG_SLOPED_SUPPORT
        if(!flat) continue;
#endif
        int x0=cp[is[0]].x,x1=x0,y0=cp[is[0]].y,y1=y0;
        for(unsigned k=1;k<4;++k) {
            if(cp[is[k]].x<x0)x0=cp[is[k]].x;
            if(cp[is[k]].x>x1)x1=cp[is[k]].x;
            if(cp[is[k]].y<y0)y0=cp[is[k]].y;
            if(cp[is[k]].y>y1)y1=cp[is[k]].y;
        }
        if(x1<ax0-1 || x0>ax1+1 || y1<ay0-1 || y0>ay1+1) continue;
        int above=flat && actor_lowest>=y;
#if SM64DS_DIAG_SLOPED_SUPPORT
        if(!flat) above=diagnostic_above_sloped_plane(scan,f);
#endif
        if(!above) continue;
#if SM64DS_DIAG_SUPPORT_AUTO && defined(CASTLE_FACE_SOURCE_AVAILABLE)
        for(uint16_t q=mapped;q<(uint16_t)(mapped+1u);++q) {
#else
        for(uint16_t q=first;q<end;++q) {
#endif
            sat_scene3d_face_t *entry=&scene.faces.entries[q];
#if SM64DS_DIAG_SLOPED_SUPPORT
            if(!entry->projected_safe && !diagnostic_not_near_clipped(entry)) continue;
#else
            if(!entry->projected_safe) continue;
#endif
            unsigned k;
            for(k=0;k<4;++k)
                if(entry->projected.x[k]!=cp[is[k]].x || entry->projected.y[k]!=cp[is[k]].y) break;
            if(k!=4) continue;
            uint32_t old=scene.faces.keys[q],depth=old&0xffffffu;
            /* Castle is submitted before the actor, and the SDK preserves
             * submission order within a bucket. */
            if(actor_max>depth) depth=actor_max;
#if SM64DS_DIAG_SUPPORT_GUARD
            if(above && depth>(old&0xffffffu)) {
                /* Keep the original group minimum and maximum in place, so
                 * the SDK computes the same bucket boundaries at flush. */
                uint32_t old_depth=old&0xffffffu;
                if(old_depth==bucket.low || depth>bucket.high) break;
                uint32_t old_bucket=(old_depth-bucket.low)>>bucket.shift;
                uint32_t new_bucket=(depth-bucket.low)>>bucket.shift;
                int x0=entry->projected.x[0],x1=x0,y0=entry->projected.y[0],y1=y0;
                for(k=1;k<4;++k) {
                    if(entry->projected.x[k]<x0)x0=entry->projected.x[k];
                    if(entry->projected.x[k]>x1)x1=entry->projected.x[k];
                    if(entry->projected.y[k]<y0)y0=entry->projected.y[k];
                    if(entry->projected.y[k]>y1)y1=entry->projected.y[k];
                }
                /* Only intersections in the framebuffer can change pixels.
                 * Keep a two-pixel margin for rasterization at the edge. */
                if(x0< -2)x0=-2;
                if(x1>321)x1=321;
                if(y0< -2)y0=-2;
                if(y1>225)y1=225;
                for(uint16_t other=0;other<actor_first;++other) {
                    if(other==q || (scene.faces.keys[other]>>24)!=(old>>24)) continue;
                    uint32_t od=scene.faces.keys[other]&0xffffffu;
                    uint32_t ob=(od-bucket.low)>>bucket.shift;
                    int before_old=old_bucket>ob || (old_bucket==ob && q<other);
                    int before_new=new_bucket>ob || (new_bucket==ob && q<other);
                    if(before_old==before_new) continue;
                    if(flat && other>=first && other<end && diagnostic_same_support(other,y,f)) continue;
#if SM64DS_DIAG_SLOPED_SUPPORT
                    if(!flat && other>=first && other<end && diagnostic_same_sloped_support(other,scan,f)) continue;
#endif
                    sat_scene3d_face_t *other_face=&scene.faces.entries[other];
                    if(!diagnostic_not_near_clipped(other_face)) {
                        if(diagnostic_clipped_outside(other_face,x0,x1,y0,y1)) continue;
                        if(g_sm64ds_support_diag.count<8) {
                            uint32_t i=g_sm64ds_support_diag.count++;
                            g_sm64ds_support_diag.blockers[i].face=(uint16_t)f;
                            g_sm64ds_support_diag.blockers[i].queue=other;
                            g_sm64ds_support_diag.blockers[i].projected=other_face->projected;
                        }
                        ++g_sm64ds_support_diag.blocked;above=0;break;
                    }
                    sat_quad2_t *quad=&other_face->projected;
                    int ox0=quad->x[0],ox1=ox0,oy0=quad->y[0],oy1=oy0;
                    for(k=1;k<4;++k) {
                        if(quad->x[k]<ox0)ox0=quad->x[k];
                        if(quad->x[k]>ox1)ox1=quad->x[k];
                        if(quad->y[k]<oy0)oy0=quad->y[k];
                        if(quad->y[k]>oy1)oy1=quad->y[k];
                    }
                    if(ox1<x0-1 || ox0>x1+1 || oy1<y0-1 || oy0>y1+1) continue;
                    if(diagnostic_separate_triangles(entry,other_face)) continue;
                    if(g_sm64ds_support_diag.count<8) {
                        uint32_t i=g_sm64ds_support_diag.count++;
                        g_sm64ds_support_diag.blockers[i].face=(uint16_t)f;
                        g_sm64ds_support_diag.blockers[i].queue=other;
                        g_sm64ds_support_diag.blockers[i].projected=*quad;
                    }
                    ++g_sm64ds_support_diag.blocked;above=0;break;
                }
            }
#endif
            if(above) {
#if SM64DS_DIAG_SUPPORT_GUARD
                if(depth!=(old&0xffffffu)) ++g_sm64ds_support_diag.changes;
#endif
                scene.faces.keys[q]=(old&0xff000000u)|depth;
            }
            break;
        }
    }
}
#elif SM64DS_DIAG_PAIR_DEPTH
static int diagnostic_quads_overlap(const sat_quad2_t *a,const sat_quad2_t *b) {
    /* VDP1 can cover the same pixel on shared or immediately adjacent
     * projected vertices even when the ideal triangles have zero area in
     * common. Preserve their existing ordering as well. */
    for(unsigned i=0;i<4;++i) for(unsigned j=0;j<4;++j) {
        int dx=a->x[i]-b->x[j],dy=a->y[i]-b->y[j];
        if(dx>=-1 && dx<=1 && dy>=-1 && dy<=1) return 1;
    }
    for(unsigned i=0;i<2;++i) {
        unsigned ac[3]={0,i?2:1,i?3:2};
        sm64ds_painter_vertex_t at[3];
        for(unsigned k=0;k<3;++k) at[k]=(sm64ds_painter_vertex_t){a->x[ac[k]],a->y[ac[k]],ONE};
        int64_t area=(int64_t)(at[1].x-at[0].x)*(at[2].y-at[0].y)-
            (int64_t)(at[1].y-at[0].y)*(at[2].x-at[0].x);
        if(!area) continue;
        for(unsigned j=0;j<2;++j) {
            unsigned bc[3]={0,j?2:1,j?3:2};
            sm64ds_painter_vertex_t bt[3];
            for(unsigned k=0;k<3;++k) bt[k]=(sm64ds_painter_vertex_t){b->x[bc[k]],b->y[bc[k]],ONE};
            area=(int64_t)(bt[1].x-bt[0].x)*(bt[2].y-bt[0].y)-
                (int64_t)(bt[1].y-bt[0].y)*(bt[2].x-bt[0].x);
            if(!area) continue;
            if(sm64ds_painter_compare_triangles(at,bt)!=SM64DS_PAINTER_DISJOINT) return 1;
        }
    }
    return 0;
}

/* Test pairwise body/ground ordering without claiming correctness against
 * walls or other actor faces. Only selected ground triangles are examined. */
static void diagnostic_pair_depth(uint16_t ground_first,uint16_t ground_end,
                                  uint16_t actor_first,uint16_t actor_end,uint16_t actor_head_end) {
    if(scene.faces.projected_entries) return;
    /* The experiment is bounded so it does not allocate a variable-size
     * stack array from a user-supplied diagnostic setting. */
    if(SM64DS_DIAG_FAR_DEPTH_COUNT>32) return;
    struct candidate { sm64ds_painter_vertex_t p[3];uint16_t queue;int x0,x1,y0,y1; } ground[32];
    unsigned ground_count=0;
    for(uint32_t g=SM64DS_DIAG_FAR_DEPTH_FIRST;
        g<(uint32_t)SM64DS_DIAG_FAR_DEPTH_FIRST+SM64DS_DIAG_FAR_DEPTH_COUNT && g<CF;++g) {
        const uint16_t *gi=&ci[g*4u];
        if(gi[2]!=gi[3]) continue;
        for(uint16_t q=ground_first;q<ground_end;++q) {
            sat_scene3d_face_t *entry=&scene.faces.entries[q];
            if(!entry->projected_safe) continue;
            unsigned k;
            for(k=0;k<4;++k)
                if(entry->projected.x[k]!=cp[gi[k]].x || entry->projected.y[k]!=cp[gi[k]].y) break;
            if(k!=4) continue;
            struct candidate *c=&ground[ground_count++];c->queue=q;
            for(k=0;k<3;++k) c->p[k]=painter_vertex(cp[gi[k]]);
            c->x0=c->x1=c->p[0].x;c->y0=c->y1=c->p[0].y;
            for(k=1;k<3;++k) {
                if(c->p[k].x<c->x0)c->x0=c->p[k].x;
                if(c->p[k].x>c->x1)c->x1=c->p[k].x;
                if(c->p[k].y<c->y0)c->y0=c->p[k].y;
                if(c->p[k].y>c->y1)c->y1=c->p[k].y;
            }
            break;
        }
    }
    uint16_t cursor=actor_first;
    for(uint16_t f=0;f<F;++f) {
        if(cursor==actor_end) break;
        const uint16_t *ai=&indices[(uint32_t)f*4];
        sat_scene3d_face_t *entry=&scene.faces.entries[cursor];
        unsigned k;
        for(k=0;k<4;++k)
            if(entry->projected.x[k]!=projected[ai[k]].x || entry->projected.y[k]!=projected[ai[k]].y) break;
        if(k!=4) continue;
        uint16_t aq=cursor++;
        if(!entry->projected_safe) continue;
        uint32_t proposed=scene.faces.keys[aq]&0xffffffu;
        int valid=1,changed=0;
        for(unsigned g=0;g<ground_count && valid;++g) {
            struct candidate *c=&ground[g];uint16_t gq=c->queue;
            if((scene.faces.keys[gq]>>24)!=(scene.faces.keys[aq]>>24)) continue;
            uint32_t ground_depth=scene.faces.keys[gq]&0xffffffu;
            uint32_t actor_depth=scene.faces.keys[aq]&0xffffffu;
            /* This actor face already sorts sufficiently after this ground;
             * moving it even nearer cannot cross this ground's key. */
            if(actor_depth<ground_depth && ground_depth-actor_depth>=16384u) continue;
            for(unsigned tri=0;tri<2;++tri) {
                unsigned corners[3]={0,tri?2:1,tri?3:2};
                sm64ds_painter_vertex_t body[3];
                for(unsigned k=0;k<3;++k) body[k]=painter_vertex(projected[ai[corners[k]]]);
                int x0=body[0].x,x1=x0,y0=body[0].y,y1=y0;
                for(unsigned k=1;k<3;++k) {
                    if(body[k].x<x0)x0=body[k].x;
                    if(body[k].x>x1)x1=body[k].x;
                    if(body[k].y<y0)y0=body[k].y;
                    if(body[k].y>y1)y1=body[k].y;
                }
                if(x1<c->x0 || x0>c->x1 || y1<c->y0 || y0>c->y1) continue;
                int64_t area=(int64_t)(body[1].x-body[0].x)*(body[2].y-body[0].y)-
                    (int64_t)(body[1].y-body[0].y)*(body[2].x-body[0].x);
                if(!area) continue;
                sm64ds_painter_relation_t relation=sm64ds_painter_compare_triangles(c->p,body);
                if(relation==SM64DS_PAINTER_DISJOINT) continue;
                if(relation!=SM64DS_PAINTER_A_BEHIND) { valid=0;break; }
                /* Wider than the painter's typical depth bucket; this is a
                 * diagnostic bias, not a proof about intervening geometry. */
                uint32_t target=ground_depth>16384u?ground_depth-16384u:0;
                if(target<proposed) { proposed=target;changed=1; }
            }
        }
        if(valid && changed) {
            /* Preserve the existing ordering against overlapping body/head
             * queue entries. Bounding boxes are deliberately conservative. */
            int x0=entry->projected.x[0],x1=x0,y0=entry->projected.y[0],y1=y0;
            for(unsigned j=1;j<4;++j) {
                if(entry->projected.x[j]<x0)x0=entry->projected.x[j];
                if(entry->projected.x[j]>x1)x1=entry->projected.x[j];
                if(entry->projected.y[j]<y0)y0=entry->projected.y[j];
                if(entry->projected.y[j]>y1)y1=entry->projected.y[j];
            }
            uint32_t old=scene.faces.keys[aq]&0xffffffu;
            for(uint16_t q=actor_first;q<actor_head_end;++q) {
                if(q==aq || (scene.faces.keys[q]>>24)!=(scene.faces.keys[aq]>>24)) continue;
                uint32_t other=scene.faces.keys[q]&0xffffffu;
                /* The SDK's bucket sort can reorder keys that are close
                 * without the exact keys crossing. Include a conservative
                 * margin while this experiment lacks its bucket metadata. */
                uint32_t lower=proposed>32768u?proposed-32768u:0;
                uint32_t upper=old<0xfffffeu-32768u?old+32768u:0xfffffeu;
                if(other<lower || other>upper) continue;
                sat_quad2_t *quad=&scene.faces.entries[q].projected;
                int ox0=quad->x[0],ox1=ox0,oy0=quad->y[0],oy1=oy0;
                for(unsigned j=1;j<4;++j) {
                    if(quad->x[j]<ox0)ox0=quad->x[j];
                    if(quad->x[j]>ox1)ox1=quad->x[j];
                    if(quad->y[j]<oy0)oy0=quad->y[j];
                    if(quad->y[j]>oy1)oy1=quad->y[j];
                }
                if(ox1>=x0-1 && ox0<=x1+1 && oy1>=y0-1 && oy0<=y1+1 &&
                   diagnostic_quads_overlap(&entry->projected,quad)) { valid=0;break; }
            }
            if(valid) scene.faces.keys[aq]=(scene.faces.keys[aq]&0xff000000u)|proposed;
        }
    }
}
#elif SM64DS_DIAG_GEOMETRIC_DEPTH
/* Conservative diagnostic prototype: compare the ground triangle against
 * both triangles of every actor face whose screen bounds overlap it.  Using
 * even back-facing actor triangles may reject a safe adjustment. */
static int diagnostic_actor_depth(const sm64ds_painter_vertex_t ground[3],
        const sat_projected_vertex_t *p,const uint16_t *idx,uint16_t count,
        uint32_t *required_depth,int *overlap) {
    int gx0=ground[0].x,gx1=gx0,gy0=ground[0].y,gy1=gy0;
    for(unsigned k=1;k<3;++k) {
        if(ground[k].x<gx0) gx0=ground[k].x;
        if(ground[k].x>gx1) gx1=ground[k].x;
        if(ground[k].y<gy0) gy0=ground[k].y;
        if(ground[k].y>gy1) gy1=ground[k].y;
    }
    for(uint16_t f=0;f<count;++f) {
        const uint16_t *is=&idx[(uint32_t)f*4];
        int64_t sum=0;
        for(unsigned k=0;k<4;++k) sum+=p[is[k]].w;
        if(sum<=0) continue;
        for(unsigned tri=0;tri<2;++tri) {
            unsigned corners[3]={0,tri?2:1,tri?3:2};
            sm64ds_painter_vertex_t b[3];
            for(unsigned k=0;k<3;++k) b[k]=painter_vertex(p[is[corners[k]]]);
            int minx=b[0].x,maxx=minx,miny=b[0].y,maxy=miny;
            for(unsigned k=1;k<3;++k) {
                if(b[k].x<minx) minx=b[k].x;
                if(b[k].x>maxx) maxx=b[k].x;
                if(b[k].y<miny) miny=b[k].y;
                if(b[k].y>maxy) maxy=b[k].y;
            }
            if(maxx<gx0 || minx>gx1 || maxy<gy0 || miny>gy1) continue;
            int64_t area=(int64_t)(b[1].x-b[0].x)*(b[2].y-b[0].y)-
                         (int64_t)(b[1].y-b[0].y)*(b[2].x-b[0].x);
            if(!area) continue;
            sm64ds_painter_relation_t relation=sm64ds_painter_compare_triangles(ground,b);
            if(relation==SM64DS_PAINTER_DISJOINT) continue;
            if(relation!=SM64DS_PAINTER_A_BEHIND) return 0;
            *overlap=1;
            uint32_t depth=(uint32_t)(sum/64);
            if(depth>=0xfffffeu) return 0;
            if(depth+1>*required_depth) *required_depth=depth+1;
        }
    }
    return 1;
}

static void diagnostic_geometric_depth(uint16_t first,uint16_t end) {
    if(scene.faces.projected_entries) return;
    for(uint32_t face=SM64DS_DIAG_FAR_DEPTH_FIRST;
        face<(uint32_t)SM64DS_DIAG_FAR_DEPTH_FIRST+SM64DS_DIAG_FAR_DEPTH_COUNT && face<CF;
        ++face) {
        const uint16_t *is=&ci[face*4u];
        if(is[2]!=is[3]) continue;
        sm64ds_painter_vertex_t ground[3];
        for(unsigned k=0;k<3;++k) ground[k]=painter_vertex(cp[is[k]]);
        uint32_t depth=0;int overlap=0;
        if((SM64DS_DIAG_OBJECTS&4) && !diagnostic_actor_depth(ground,projected,indices,F,&depth,&overlap)) continue;
        if((SM64DS_DIAG_OBJECTS&8) && !diagnostic_actor_depth(ground,hp,hi,HF,&depth,&overlap)) continue;
        if(!overlap) continue;
        for(uint16_t q=first;q<end;++q) {
            sat_scene3d_face_t *entry=&scene.faces.entries[q];
            if(!entry->projected_safe) continue;
            unsigned k;
            for(k=0;k<4;++k)
                if(entry->projected.x[k]!=cp[is[k]].x || entry->projected.y[k]!=cp[is[k]].y) break;
            if(k==4) {
                if((scene.faces.keys[q]&0xffffffu)<depth)
                    scene.faces.keys[q]=(scene.faces.keys[q]&0xff000000u)|depth;
                break;
            }
        }
    }
}
#else
/* Experiment only: use the farthest corner as a face's painter depth.  It
 * is intentionally restricted to selected render-face IDs; this does not
 * establish that a face is behind an actor over their screen intersection. */
static void diagnostic_far_depth(uint16_t first,uint16_t end) {
    if(scene.faces.projected_entries) return;
    for(uint32_t face=SM64DS_DIAG_FAR_DEPTH_FIRST;
        face<(uint32_t)SM64DS_DIAG_FAR_DEPTH_FIRST+SM64DS_DIAG_FAR_DEPTH_COUNT && face<CF;
        ++face) {
        const uint16_t *index=&ci[face*4u];
        int32_t depth=0;
        for(unsigned c=0;c<4;++c) if(cp[index[c]].w>depth) depth=cp[index[c]].w;
        uint32_t key_depth=(uint32_t)depth/16u;
        if(key_depth>0xfffffeu) key_depth=0xfffffeu;
        for(uint16_t q=first;q<end;++q) {
            sat_scene3d_face_t *entry=&scene.faces.entries[q];
            if(!entry->projected_safe) continue;
            unsigned c;
            for(c=0;c<4;++c)
                if(entry->projected.x[c]!=cp[index[c]].x || entry->projected.y[c]!=cp[index[c]].y) break;
            if(c==4) {
                scene.faces.keys[q]=(scene.faces.keys[q]&0xff000000u)|key_depth;
                break;
            }
        }
    }
}
#endif
#endif
