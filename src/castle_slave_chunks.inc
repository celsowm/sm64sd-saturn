/* Castle chunk preparation on both SH-2s; textually included by castle.c.
 *
 * The Master culls every chunk against the view frustum itself, then hands
 * the visible chunks farthest from the camera (about half of the visible
 * faces) to the Slave as one lib-saturn prepare batch, which writes straight
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
/* The Slave takes at most half the visible faces. */
#define SLAVE_FACE_CAP (CAP/2u)
static uint32_t slave_keys[SLAVE_FACE_CAP] __attribute__((section(".wram_l"),aligned(4)));
static sat_scene3d_prepare_batch_t slave_batch __attribute__((section(".wram_l"),aligned(4)));
static uint8_t slave_chunk_ids[CASTLE_CHUNK_COUNT];
static uint8_t chunk_visible[CASTLE_CHUNK_COUNT],chunk_on_slave[CASTLE_CHUNK_COUNT];
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

static int chunk_in_frustum(const sat_mat4_t *vp,const sat_aabb3_t *b) {
    const int32_t *m=vp->m;
    for (unsigned p=0;p<6u;++p) {
        const unsigned k=4u*(p>>1);
        const int64_t s=(p&1u)?-1:1;
        const int64_t n64[4]={m[12]+s*m[k],m[13]+s*m[k+1],m[14]+s*m[k+2],m[15]+s*m[k+3]};
        int32_t n[4];
        for (unsigned i=0;i<4u;++i) {
            if (n64[i]<INT32_MIN || n64[i]>INT32_MAX) return 1;  /* keep: conservative */
            n[i]=(int32_t)n64[i];
        }
        /* 32.32 plane value at the centre, and its largest gain over the box. */
        const int64_t centre=(int64_t)n[0]*b->center.x+(int64_t)n[1]*b->center.y+
                             (int64_t)n[2]*b->center.z+((int64_t)n[3]<<16);
        const int64_t reach=(int64_t)(n[0]<0?-n[0]:n[0])*b->half.x+
                            (int64_t)(n[1]<0?-n[1]:n[1])*b->half.y+
                            (int64_t)(n[2]<0?-n[2]:n[2])*b->half.z;
        /* The margin covers the library's per-term 16.16 truncation. */
        if (centre+reach < -((int64_t)64<<16)) return 0;
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
    for (uint8_t c=0;c<CASTLE_CHUNK_COUNT;++c) {
        chunk_on_slave[c]=0;
        chunk_visible[c]=!exp_chunk_far(c) &&
            chunk_in_frustum(&scene.faces.view_proj,&castle_chunk_bounds[c]);
        if (chunk_visible[c]) {visible_faces+=castle_chunk_count[c];++visible_count;}
    }
    if (!slave_ready || visible_count<2u) return 0;
    /* The reservation holds the Slave's worst case until the next frame, so
     * only split when every visible face would fit anyway; a fuller frame
     * keeps the Master-only path and its far-chunk drop behaviour. */
    if (scene.faces.count+scene.faces.projected_gap+visible_faces>terrain_cap) {
        ++g_sm64ds_slave_stats.skipped;
        return 0;
    }
    /* Farthest first until half the visible faces: the near chunks under
     * Mario stay on the Master. */
    uint32_t slave_faces=0;
    while (slave_faces*2u<visible_faces) {
        uint8_t best=0xffu;uint32_t best_d=0;
        for (uint8_t c=0;c<CASTLE_CHUNK_COUNT;++c) {
            if (!chunk_visible[c] || chunk_on_slave[c]) continue;
            uint32_t d=chunk_distance2(c);
            if (best==0xffu || d>best_d) {best=c;best_d=d;}
        }
        if (best==0xffu || slave_faces+castle_chunk_count[best]>SLAVE_FACE_CAP) break;
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
