/* outdoor tree/sign props and actor kinds; textually included by castle.c. */
#ifdef CASTLE_PROPS_AVAILABLE
static void submit_wanwan_chains(const sat_vec3_t *fwd,const sat_vec3_t *right,
                                 int32_t lx,int32_t lz,int32_t rx,int32_t rz) {
#ifdef CASTLE_ACTOR_KINDS_AVAILABLE
    for (uint32_t k=0;k<CASTLE_ACTOR_KIND_COUNT;++k) {
        sm64ds_actor_kind_t *ch=castle_actor_kinds[k];
        if (ch->behavior!=SM64DS_ACTOR_WANWAN) continue;
        for (uint32_t i=0;i<ch->count;++i) {
            if (ch->st[i]==SM64DS_ACTOR_DEAD) continue;
            /* Chain from the placement's post (positions[i], the anchor) to
             * the live head position, drawn as small camera-facing quads. */
            sat_vec3_t a=ch->positions[i], b=ch->pos[i];
            /* The placement is the post on the ground; the chain hangs from
             * a point above it. */
            a.y+=(int32_t)(24*ONE);
            const int32_t dx=b.x-a.x, dy=b.y-a.y, dz=b.z-a.z;
            const int32_t len2=(int32_t)(((int64_t)dx*dx+(int64_t)dy*dy+(int64_t)dz*dz)/ONE);
            if (len2<4*ONE) continue;
            const int32_t len=sat_isqrt32((uint32_t)len2);
            if (len<6*ONE) continue;
            const int32_t links=(int32_t)(len/(6*ONE));
            for (int32_t s=1;s<links;++s) {
                const int32_t t=s*ONE/links;
                sat_vec3_t p={a.x+sat_fx16_mul(dx,t),a.y+sat_fx16_mul(dy,t),a.z+sat_fx16_mul(dz,t)};
                int32_t ddx=p.x-camera.eye.x, ddz=p.z-camera.eye.z;
                int32_t depth=sat_fx16_mul(ddx,fwd->x)+sat_fx16_mul(ddz,fwd->z);
                if (depth<2*ONE || depth>360*ONE) continue;
                int32_t lat=sat_fx16_mul(ddx,right->x)+sat_fx16_mul(ddz,right->z);
                if (sat_fx16_abs(lat)>depth+8*ONE) continue;
                sat_quad3_t quad={.v={
                    {p.x-lx,p.y-3*ONE,p.z-lz},{p.x+rx,p.y-3*ONE,p.z+rz},
                    {p.x+rx,p.y+3*ONE,p.z+rz},{p.x-lx,p.y+3*ONE,p.z-lz}}};
                SAT_PANIC_IF_ERROR(sat_scene_submit_quad(&scene,&quad,&tree_material,SM64DS_ACTOR_PASS));
            }
        }
    }
#endif
}

static void submit_castle_props(void) {
    hud_trees_drawn=0;hud_signs_drawn=0;
    sat_vec3_t fwd={camera.target.x-camera.eye.x,0,camera.target.z-camera.eye.z};
    sat_vec3_normalize(&fwd,&fwd);
    if (!fwd.x && !fwd.z) return;
    sat_vec3_t right={-fwd.z,0,fwd.x};
    int32_t lx=sat_fx16_mul(right.x,CASTLE_TREE_LEFT),lz=sat_fx16_mul(right.z,CASTLE_TREE_LEFT);
    int32_t rx=sat_fx16_mul(right.x,CASTLE_TREE_RIGHT),rz=sat_fx16_mul(right.z,CASTLE_TREE_RIGHT);
    submit_wanwan_chains(&fwd,&right,lx,lz,rx,rz);
    for (uint32_t i=0;i<CASTLE_TREE_COUNT;++i) {
        const sat_vec3_t pos=castle_tree_positions[i];
        int32_t dx=pos.x-camera.eye.x,dz=pos.z-camera.eye.z;
        int32_t depth=sat_fx16_mul(dx,fwd.x)+sat_fx16_mul(dz,fwd.z);
        if (depth<8*ONE) continue;
        int32_t lat=sat_fx16_mul(dx,right.x)+sat_fx16_mul(dz,right.z);
        if (sat_fx16_abs(lat)>depth+24*ONE) continue;
        sat_quad3_t quad={.v={
            {pos.x+lx,pos.y+CASTLE_TREE_TOP,pos.z+lz},
            {pos.x+rx,pos.y+CASTLE_TREE_TOP,pos.z+rz},
            {pos.x+rx,pos.y+CASTLE_TREE_BOTTOM,pos.z+rz},
            {pos.x+lx,pos.y+CASTLE_TREE_BOTTOM,pos.z+lz}
        }};
        SAT_PANIC_IF_ERROR(sat_scene_submit_quad(&scene,&quad,&tree_material,SM64DS_ACTOR_PASS));
        ++hud_trees_drawn;
    }
    for (uint32_t i=0;i<CASTLE_SIGN_COUNT;++i) {
        const sat_vec3_t pos=castle_sign_positions[i];
        int32_t dx=pos.x-camera.eye.x,dz=pos.z-camera.eye.z;
        int32_t depth=sat_fx16_mul(dx,fwd.x)+sat_fx16_mul(dz,fwd.z);
        if (depth<4*ONE || depth>360*ONE) continue;
        int32_t lat=sat_fx16_mul(dx,right.x)+sat_fx16_mul(dz,right.z);
        if (sat_fx16_abs(lat)>depth+16*ONE) continue;
        sign_prop.world=sign_worlds[i];
        SAT_PANIC_IF_ERROR(sat_scene_submit_instance(&scene,&sign_prop.instance,SAT_SCENE3D_SLOT_INHERIT,sp,sw));
        ++hud_signs_drawn;
    }
#ifdef CASTLE_ACTOR_KINDS_AVAILABLE
    sat_vec3_t view={camera.target.x-camera.eye.x,camera.target.y-camera.eye.y,camera.target.z-camera.eye.z};
    sat_vec3_normalize(&view,&view);
    for (uint32_t k=0;k<CASTLE_ACTOR_KIND_COUNT;++k)
        SAT_PANIC_IF_ERROR(sm64ds_actor_kind_submit(castle_actor_kinds[k],&scene,&camera.eye,&fwd,&right,CAP,
                                                   &player.feet,12u,&view));
#endif
}
#endif
