/* Castle chunk preparation on both SH-2s; textually included by castle.c.
 *
 * The Master culls every chunk against the view frustum itself, then hands
 * the visible chunks farthest from the camera (about three quarters of the
 * visible faces) to the Slave as one lib-saturn prepare batch, which writes straight
 * into a span reserved in the scene queue. The Master submits the nearer
 * chunks and the water meanwhile, then merges. The batch reports each item's
 * face count, so every chunk still has its exact chunk_qfirst/qend run in the
 * queue for the support-plane ordering. Without a Slave, or if the batch
 * fails, the Master submits those chunks itself: a frame never loses faces.
 *
 * The chunk test replaces the per-instance bounds test in submit_instance
 * (the instances carry no bounds in this mode): it rejects a box only when
 * it lies wholly outside one clip plane, which is the library's "all eight
 * corners outside the same plane" rule evaluated on the plane directly. */
/* The split pays only with a source plan per chunk: without one the per-frame
 * source walk costs more than the Slave saves (JRB: 44 -> 79 ms/draw). Plans
 * take ~100 B a chunk, which a 150-chunk stage (JRB) has no WRAM left for. */
#if defined(CASTLE_CHUNK_CULLING) && !SM64DS_VISUAL_DIAGNOSTICS && !defined(SM64DS_NO_SLAVE) && \
    CASTLE_CHUNK_COUNT <= 96u
#include <saturn/parallel.h>
#define CASTLE_SLAVE_CHUNKS 1
#define SLAVE_TIMEOUT_TICKS 60000u

static sat_scene3d_prepare_item_t slave_items[CASTLE_CHUNK_COUNT] __attribute__((section(".wram_l"),aligned(4)));
static uint16_t slave_item_faces[CASTLE_CHUNK_COUNT] __attribute__((section(".wram_l"),aligned(4)));
/* The Slave takes the farthest SLAVE_SHARE_NUM/SLAVE_SHARE_DEN of the visible
 * faces: the Master also builds the water and the props meanwhile, so an even
 * split leaves the Slave idle at the merge. */
#ifndef SLAVE_SHARE_NUM
#define SLAVE_SHARE_NUM 1u
#endif
#ifndef SLAVE_SHARE_DEN
#define SLAVE_SHARE_DEN 2u
#endif
#define SLAVE_FACE_CAP (CAP*SLAVE_SHARE_NUM/SLAVE_SHARE_DEN)
static uint32_t slave_keys[SLAVE_FACE_CAP] __attribute__((section(".wram_l"),aligned(4)));
static sat_scene3d_prepare_batch_t slave_batch __attribute__((section(".wram_l"),aligned(4)));
static uint8_t slave_chunk_ids[CASTLE_CHUNK_COUNT] __attribute__((section(".wram_l"),aligned(4)));
static uint8_t chunk_visible[CASTLE_CHUNK_COUNT] __attribute__((section(".wram_l"),aligned(4)));
static uint8_t chunk_on_slave[CASTLE_CHUNK_COUNT] __attribute__((section(".wram_l"),aligned(4)));
static uint8_t chunk_rank[CASTLE_CHUNK_COUNT] __attribute__((section(".wram_l"),aligned(4)));
static uint32_t chunk_dist[CASTLE_CHUNK_COUNT] __attribute__((section(".wram_l"),aligned(4)));
static uint8_t slave_ready;
/* Direct batch spans index the projected queue; High WRAM has the room. */
static uint16_t projected_order[CAP];
/* The chunk meshes, material tables and textures never change after
 * setup, so each chunk carries a source plan: its ranges are published once
 * here instead of being re-walked and re-synced on every frame. */
#define SLAVE_PLAN_RANGES 8u
static sat_scene3d_source_plan_t chunk_plans[CASTLE_CHUNK_COUNT] __attribute__((section(".wram_l"),aligned(4)));
static sat_scene3d_source_range_t chunk_plan_ranges[CASTLE_CHUNK_COUNT*SLAVE_PLAN_RANGES] __attribute__((section(".wram_l"),aligned(4)));
static uint8_t chunk_plan_ready[CASTLE_CHUNK_COUNT];

/* Read from the WRAM dump by tools/profile_castle_frames.py. */
struct sm64ds_slave_stats {
    uint32_t magic;
    uint32_t backend;      /* 1: the Slave SH-2 runs the batches */
    uint32_t frames;       /* frames with a batch */
    uint32_t fallbacks;    /* batches the Master had to redo */
    uint32_t skipped;      /* frames too full to reserve the Slave's worst case */
    uint32_t items;        /* chunks prepared by the Slave */
    uint32_t reserved;     /* worst-case faces reserved */
    uint32_t prepared;     /* faces the Slave produced */
    uint32_t wait_ticks;   /* FRT ticks the Master waited at the merge */
    uint32_t declined;     /* batches the runtime refused to reserve or start */
    uint32_t plans;        /* chunks with a source plan */
} g_sm64ds_slave_stats={.magic=0x534c4156};

/* Once, between frames, after the scene's projected storage is bound. */
static void slave_chunks_setup(void) {
    for (uint8_t c=0;c<CASTLE_CHUNK_COUNT;++c) chunk_instances[c].bounds=0;
    SAT_PANIC_IF_ERROR(sat_scene3d_faces_use_projected_indices(&scene.faces,projected_order,CAP));
    /* A chunk whose plan does not fit keeps the conservative per-frame walk. */
    for (uint8_t c=0;c<CASTLE_CHUNK_COUNT;++c)
        chunk_plan_ready[c]=sat_scene3d_source_plan_init(&chunk_plans[c],&chunk_instances[c],
            &chunk_plan_ranges[c*SLAVE_PLAN_RANGES],SLAVE_PLAN_RANGES)==SAT_OK;
    for (uint8_t c=0;c<CASTLE_CHUNK_COUNT;++c) g_sm64ds_slave_stats.plans+=chunk_plan_ready[c];
}

static void slave_chunks_init(void) {
    const sat_parallel_config_t config={SAT_PARALLEL_AUTO,0,0u,0u,SLAVE_TIMEOUT_TICKS};
    slave_ready=sat_scene3d_prepare_parallel_register()==SAT_OK &&
                sat_parallel_init(&config)==SAT_OK &&
                sat_parallel_slave_available();
    g_sm64ds_slave_stats.backend=slave_ready;
}

/* The Slave runs from this program's WRAM; stop it before sat_exec loads
 * another program over it, and restart it if the load fails. */
static void slave_chunks_stop(void) {
    (void)sat_parallel_shutdown(SLAVE_TIMEOUT_TICKS);
    slave_ready=0;
}

/* The six clip planes, built once per frame from the view-projection rows.
 * A plane that does not fit 32 bits is left out (conservative: keep).
 *
 * Each plane also gets a 32-bit form for the per-chunk test: its normal
 * scaled down below 2^13 and taken relative to the camera, so the test is
 * nine 32-bit multiplies instead of six 64-bit ones and their spills. Every
 * rounding is bounded and added back as slack, so the fast test only ever
 * keeps a chunk the exact 64-bit test would keep too (it never culls more). */
typedef struct {
    int32_t n[4];          /* exact plane, for the 64-bit test */
    int32_t fn[3],fa[3];   /* floor(n/2^s) and |floor(n/2^s)|+1 */
    int32_t base,slack;    /* floor(plane(eye)/2^(s+16)); rounding bound */
    uint8_t fast;
} frustum_plane_t;
static frustum_plane_t frustum_planes[6] __attribute__((section(".wram_l"),aligned(4)));
static uint8_t frustum_plane_count;
static sat_vec3_t frustum_eye;

static void frustum_build(const sat_mat4_t *vp,const sat_vec3_t *eye) {
    const int32_t *m=vp->m;
    frustum_plane_count=0;
    frustum_eye=*eye;
    for (unsigned p=0;p<6u;++p) {
        const unsigned k=4u*(p>>1);
        const int64_t s=(p&1u)?-1:1;
        const int64_t n64[4]={m[12]+s*m[k],m[13]+s*m[k+1],m[14]+s*m[k+2],m[15]+s*m[k+3]};
        int fits=1;
        for (unsigned i=0;i<4u;++i)
            if (n64[i]<INT32_MIN || n64[i]>INT32_MAX) fits=0;
        if (!fits) continue;
        frustum_plane_t *fp=&frustum_planes[frustum_plane_count++];
        for (unsigned i=0;i<4u;++i) fp->n[i]=(int32_t)n64[i];
        int64_t maxn=0;
        for (unsigned i=0;i<3u;++i) {
            const int64_t a=fp->n[i]<0?-(int64_t)fp->n[i]:fp->n[i];
            if (a>maxn) maxn=a;
        }
        unsigned shift=0;
        while (shift<31u && (maxn>>shift)>=(1<<13)) ++shift;
        int32_t sum_abs=0;
        for (unsigned i=0;i<3u;++i) {
            fp->fn[i]=fp->n[i]>>shift;
            const int32_t a=fp->fn[i]<0?-fp->fn[i]:fp->fn[i];
            fp->fa[i]=a+1;
            sum_abs+=a;
        }
        const int64_t at_eye=(int64_t)fp->n[0]*eye->x+(int64_t)fp->n[1]*eye->y+
                             (int64_t)fp->n[2]*eye->z+(int64_t)fp->n[3]*65536;
        const int64_t base=at_eye>>(shift+16u);
        /* |n'd| and |n'|h stay below 3*2^28 each, so the sum fits int32. */
        fp->fast=base>-(1<<28) && base<(1<<28);
        fp->base=fp->fast?(int32_t)base:0;
        /* n*d rounding (sum|n'|+sum|d'|+3), the eye term (1), and the exact
         * test's 64<<16 truncation margin in these units. */
        fp->slack=sum_abs+4+((shift<6u?(64>>shift):0)+1);
    }
}

static int plane_keeps_exact(const frustum_plane_t *fp,const sat_aabb3_t *b) {
    const int32_t *n=fp->n;
    /* 32.32 plane value at the centre, and its largest gain over the box. */
    const int64_t centre=(int64_t)n[0]*b->center.x+(int64_t)n[1]*b->center.y+
                         (int64_t)n[2]*b->center.z+(int64_t)n[3]*65536;
    const int64_t reach=(int64_t)(n[0]<0?-n[0]:n[0])*b->half.x+
                        (int64_t)(n[1]<0?-n[1]:n[1])*b->half.y+
                        (int64_t)(n[2]<0?-n[2]:n[2])*b->half.z;
    /* The margin covers the library's per-term 16.16 truncation. */
    return centre+reach >= -((int64_t)64<<16);
}

static int chunk_in_frustum(const sat_aabb3_t *b) {
    /* Whole units from the eye (floor) and half extents rounded up; outside
     * +-2^15 units the exact test runs instead. */
    int32_t d[3],h[3];
    const int32_t c[3]={b->center.x,b->center.y,b->center.z};
    const int32_t e[3]={frustum_eye.x,frustum_eye.y,frustum_eye.z};
    const int32_t hh[3]={b->half.x,b->half.y,b->half.z};
    int32_t sum_d=0;
    int fast=1;
    for (unsigned i=0;i<3u;++i) {
        const int64_t delta=((int64_t)c[i]-e[i])>>16;
        if (delta<=-(1<<15) || delta>=(1<<15) || hh[i]<0) {fast=0;break;}
        d[i]=(int32_t)delta;
        h[i]=(hh[i]>>16)+1;
        sum_d+=d[i]<0?-d[i]:d[i];
    }
    for (unsigned p=0;p<frustum_plane_count;++p) {
        const frustum_plane_t *fp=&frustum_planes[p];
        if (fast && fp->fast) {
            const int32_t v=fp->base+fp->slack+sum_d+
                fp->fn[0]*d[0]+fp->fn[1]*d[1]+fp->fn[2]*d[2]+
                fp->fa[0]*h[0]+fp->fa[1]*h[1]+fp->fa[2]*h[2];
            if (v<0) return 0;
        } else if (!plane_keeps_exact(fp,b)) return 0;
    }
    return 1;
}

static uint32_t chunk_distance2(uint8_t c) {
    const sat_aabb3_t *b=&castle_chunk_bounds[c];
    int32_t dx=(camera.eye.x>b->center.x?camera.eye.x-b->center.x:b->center.x-camera.eye.x)-b->half.x;
    int32_t dz=(camera.eye.z>b->center.z?camera.eye.z-b->center.z:b->center.z-camera.eye.z)-b->half.z;
    if (dx<0) dx=0;
    if (dz<0) dz=0;
    dx>>=16; dz>>=16;
    return (uint32_t)(dx*dx+dz*dz);
}

static void submit_chunk(uint8_t c) {
    SAT_PANIC_IF_ERROR(sat_scene_submit_instance(
        &scene,&chunk_instances[c],SAT_SCENE3D_SLOT_INHERIT,&cp[castle_chunk_vfirst[c]],0));
}

/* Cull, split and start the Slave batch. Returns 1 when a batch is pending. */
static int slave_chunks_begin(uint16_t terrain_cap) {
    uint32_t visible_faces=0;
    uint8_t visible_count=0;
    frustum_build(&scene.faces.view_proj,&camera.eye);
    for (uint8_t c=0;c<CASTLE_CHUNK_COUNT;++c) {
        chunk_on_slave[c]=0;
        chunk_visible[c]=!exp_chunk_far(c) && chunk_in_frustum(&castle_chunk_bounds[c]);
        if (chunk_visible[c]) {
            chunk_dist[visible_count]=chunk_distance2(c);
            chunk_rank[visible_count]=c;
            visible_faces+=castle_chunk_count[c];++visible_count;
        }
    }
    if (!slave_ready || visible_count<2u) return 0;
    /* The reservation holds the Slave's worst case until the next frame, so
     * only split when every visible face would fit anyway; a fuller frame
     * keeps the Master-only path and its far-chunk drop behaviour. */
    if (scene.faces.count+scene.faces.projected_gap+visible_faces>terrain_cap) {
        ++g_sm64ds_slave_stats.skipped;
        return 0;
    }
    /* Farthest first until the Slave's share of the visible faces: the near
     * chunks under Mario stay on the Master. */
    /* Insertion sort of the visible chunks, farthest first (ties keep the
     * lower chunk id first, as the old repeated max scan did). */
    for (uint8_t i=1;i<visible_count;++i) {
        const uint32_t d=chunk_dist[i];const uint8_t c=chunk_rank[i];
        uint8_t j=i;
        while (j>0u && chunk_dist[j-1u]<d) {
            chunk_dist[j]=chunk_dist[j-1u];chunk_rank[j]=chunk_rank[j-1u];--j;
        }
        chunk_dist[j]=d;chunk_rank[j]=c;
    }
    uint32_t slave_faces=0;
    for (uint8_t i=0;i<visible_count && slave_faces*SLAVE_SHARE_DEN<visible_faces*SLAVE_SHARE_NUM;++i) {
        const uint8_t best=chunk_rank[i];
        if (slave_faces+castle_chunk_count[best]>SLAVE_FACE_CAP) break;
        chunk_on_slave[best]=1;
        slave_faces+=castle_chunk_count[best];
    }
    uint16_t n=0;
    for (uint8_t c=0;c<CASTLE_CHUNK_COUNT;++c) {
        if (!chunk_on_slave[c]) continue;
        slave_chunk_ids[n]=c;
        slave_items[n]=(sat_scene3d_prepare_item_t){
            .instance=&chunk_instances[c],.screen_scratch=&cp[castle_chunk_vfirst[c]],
            .world_scratch=0,.color_calc_slot=SAT_SCENE3D_SLOT_INHERIT,
.source_plan=chunk_plan_ready[c]?&chunk_plans[c]:0};
        ++n;
    }
    if (n==0u || n==visible_count ||
        sat_scene3d_prepare_batch_init(&slave_batch,slave_items,n,faces,slave_keys,
                                       (uint16_t)slave_faces)!=SAT_OK) {
        for (uint8_t c=0;c<CASTLE_CHUNK_COUNT;++c) chunk_on_slave[c]=0;
        return 0;
    }
    slave_batch.item_faces=slave_item_faces;
    slave_batch.dispatch=SAT_SCENE3D_PREPARE_DISPATCH_RUNTIME;
    sat_parallel_handle_t handle=0;
    if (sat_scene3d_faces_reserve_batch(&scene.faces,&slave_batch)!=SAT_OK) {
        ++g_sm64ds_slave_stats.declined;
        for (uint8_t c=0;c<CASTLE_CHUNK_COUNT;++c) chunk_on_slave[c]=0;
        return 0;
    }
    if (sat_scene_prepare_batch_async(&scene,&slave_batch,&handle)!=SAT_OK) {
        (void)sat_scene3d_faces_cancel_batch(&scene.faces,&slave_batch);
        ++g_sm64ds_slave_stats.declined;
        for (uint8_t c=0;c<CASTLE_CHUNK_COUNT;++c) chunk_on_slave[c]=0;
        return 0;
    }
    g_sm64ds_slave_stats.reserved+=slave_faces;
    g_sm64ds_slave_stats.items+=n;
    return 1;
}

/* Wait for and merge the batch, then give each Slave chunk its queue run. */
static void slave_chunks_finish(void) {
    const sat_parallel_handle_t handle=slave_batch.handle;
    const uint64_t start=sat_time_ticks();
    sat_result_t st=sat_parallel_wait(handle,SLAVE_TIMEOUT_TICKS);
    if (st==SAT_OK) st=sat_parallel_result(handle,0);
    if (sat_parallel_state(handle)==SAT_PARALLEL_RUNNING) {
        (void)sat_parallel_abort(handle,SLAVE_TIMEOUT_TICKS);
        st=SAT_ERR_TIMEOUT;
    }
    uint16_t base=scene.faces.count;
    if (st==SAT_OK) st=sat_scene_merge_prepared_batch(&scene,&slave_batch,handle);
    g_sm64ds_slave_stats.wait_ticks+=(uint32_t)(sat_time_ticks()-start);
    (void)sat_scene_prepare_batch_release(&scene,&slave_batch,handle);
    ++g_sm64ds_slave_stats.frames;
    if (st==SAT_OK) {
        g_sm64ds_slave_stats.prepared+=slave_batch.metrics.prepared_faces;
        for (uint16_t i=0;i<slave_batch.item_count;++i) {
            const uint8_t c=slave_chunk_ids[i];
            chunk_qfirst[c]=base;
            base=(uint16_t)(base+slave_item_faces[i]);
            chunk_qend[c]=base;
        }
        /* The Slave wrote these projected vertices; the support ordering
         * reads them, so drop any stale line from this CPU's cache. */
        (void)sat_parallel_cache_sync_range(cp,sizeof(cp));
        return;
    }
    ++g_sm64ds_slave_stats.fallbacks;
    for (uint16_t i=0;i<slave_batch.item_count;++i) {
        const uint8_t c=slave_chunk_ids[i];
        chunk_qfirst[c]=scene.faces.count;
        submit_chunk(c);
        chunk_qend[c]=scene.faces.count;
    }
}
#endif
