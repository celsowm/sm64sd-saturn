/* paintings, doors and Toads; textually included by castle.c. */
#ifdef CASTLE_INTERIOR_PROPS_AVAILABLE
#if CASTLE_RIPPLE_COUNT > 0
/* Proximity ripple (daPicGate_c state row 0). The canvas stays flat until
 * Mario comes close, then a wave starts at his projected position and runs
 * for the WaveParams duration. VDP1 cannot sample per-vertex UVs, so the
 * canvas is a grid of textured tiles and each cell is one quad.
 *
 * The trigger sits well outside the 16-unit painting warp box so the wave
 * starts on the approach; stopping short of the box shows the whole run. */
#define CASTLE_RIPPLE_TRIGGER (12*ONE) /* units in front of the canvas */
typedef struct castle_ripple_state {
    int32_t timer;              /* frames left; 0 draws the flat quad */
    uint16_t phase;             /* running wave phase (16-bit turn) */
    int32_t origin_u, origin_v; /* wave origin in canvas 16.16 units */
    uint8_t armed;              /* Mario has been outside the trigger */
} castle_ripple_state_t;
static castle_ripple_state_t castle_ripples[CASTLE_RIPPLE_COUNT];
static uint8_t castle_ripples_ready;

/* RippleHeight: sine of the wave phase at dist, scaled by the amplitude
 * falloff. Past the wavefront (and after the run) the canvas is flat. */
static int32_t castle_ripple_height(const castle_ripple_wave_t *p,
                                    const castle_ripple_state_t *w,
                                    int32_t dist) {
    const int32_t elapsed=(int32_t)p->duration-w->timer;
    int32_t frames=65535/p->phase_step;
    if (frames<1) frames=1;
    const int32_t speed=p->wavelength/frames;
    if (dist>speed*elapsed) return 0;
    const int32_t phase=(int32_t)(((int64_t)dist*65536)/p->wavelength)-w->phase;
    const int32_t amp=p->amplitude-(p->amplitude/(int32_t)p->duration)*elapsed;
    int32_t fall=amp-(int32_t)(((int64_t)amp*dist)/p->radius);
    if (fall<0) fall=0;
    return sat_fx16_mul(sat_sin16((uint16_t)phase),fall);
}

static int castle_ripple_index(uint32_t painting) {
    for (uint32_t r=0;r<CASTLE_RIPPLE_COUNT;++r)
        if (castle_ripple_paintings[r]==painting) return (int)r;
    return -1;
}

/* Draw one active wave: 7x7 textured cells displaced along the canvas
 * normal. Returns the number of faces submitted. */
static void castle_ripple_draw(uint32_t r,const sat_quad3_t *q) {
    const uint32_t i=castle_ripple_paintings[r];
    const castle_ripple_wave_t *wave=&castle_ripple_waves[r];
    castle_ripple_state_t *st=&castle_ripples[r];
    const sat_vec3_t tl=q->v[0],tr=q->v[1],bl=q->v[3];
    const sat_vec3_t uvec={tr.x-tl.x,tr.y-tl.y,tr.z-tl.z};
    const sat_vec3_t vvec={bl.x-tl.x,bl.y-tl.y,bl.z-tl.z};
    const int32_t uu=sat_fx16_mul(uvec.x,uvec.x)+sat_fx16_mul(uvec.y,uvec.y)+sat_fx16_mul(uvec.z,uvec.z);
    const int32_t vv=sat_fx16_mul(vvec.x,vvec.x)+sat_fx16_mul(vvec.y,vvec.y)+sat_fx16_mul(vvec.z,vvec.z);
    const int32_t width=sat_fx16_sqrt(uu), height=sat_fx16_sqrt(vv);
    sat_vec3_t normal;
    sat_vec3_cross(&normal,&vvec,&uvec);
    sat_vec3_normalize(&normal,&normal);

    sat_vec3_t p[CASTLE_RIPPLE_GRID][CASTLE_RIPPLE_GRID];
    for (uint32_t gy=0;gy<CASTLE_RIPPLE_GRID;++gy) {
        const int32_t vf=(int32_t)(((int64_t)ONE*gy)/(CASTLE_RIPPLE_GRID-1));
        const int32_t v_pos=sat_fx16_mul(height,vf);
        for (uint32_t gx=0;gx<CASTLE_RIPPLE_GRID;++gx) {
            const int32_t uf=(int32_t)(((int64_t)ONE*gx)/(CASTLE_RIPPLE_GRID-1));
            const int32_t u_pos=sat_fx16_mul(width,uf);
            const int32_t dx=u_pos-st->origin_u,dy=v_pos-st->origin_v;
            const int32_t dist=sat_fx16_sqrt(sat_fx16_mul(dx,dx)+sat_fx16_mul(dy,dy));
            const int32_t z=castle_ripple_height(wave,st,dist);
            sat_vec3_t *out=&p[gy][gx];
            out->x=tl.x+sat_fx16_mul(uvec.x,uf)+sat_fx16_mul(vvec.x,vf)+sat_fx16_mul(normal.x,z);
            out->y=tl.y+sat_fx16_mul(uvec.y,uf)+sat_fx16_mul(vvec.y,vf)+sat_fx16_mul(normal.y,z);
            out->z=tl.z+sat_fx16_mul(uvec.z,uf)+sat_fx16_mul(vvec.z,vf)+sat_fx16_mul(normal.z,z);
        }
    }
    for (uint32_t gy=0;gy+1<CASTLE_RIPPLE_GRID;++gy) {
        for (uint32_t gx=0;gx+1<CASTLE_RIPPLE_GRID;++gx) {
            const uint16_t tile=castle_ripple_tiles[r*CASTLE_RIPPLE_CELLS+gy*CASTLE_RIPPLE_GRID+gx];
            const sat_quad3_t quad={.v={
                p[gy][gx],p[gy][gx+1],p[gy+1][gx+1],p[gy+1][gx]}};
            SAT_PANIC_IF_ERROR(sat_scene_submit_quad(&scene,&quad,&painting_materials[tile],SM64DS_ACTOR_PASS));
        }
    }
    /* The decomp advances the wave clock after computing the heights. */
    st->phase=(uint16_t)(st->phase+wave->phase_step);
}
#endif

static void submit_interior_props(void) {
    hud_paintings_drawn=0;hud_doors_drawn=0;hud_toads_drawn=0;
    sat_vec3_t fwd={camera.target.x-camera.eye.x,0,camera.target.z-camera.eye.z};
    sat_vec3_normalize(&fwd,&fwd);
    if (!fwd.x && !fwd.z) return;
    sat_vec3_t right={-fwd.z,0,fwd.x};

#if CASTLE_RIPPLE_COUNT > 0
    if (!castle_ripples_ready) {
        for (uint32_t r=0;r<CASTLE_RIPPLE_COUNT;++r) castle_ripples[r].armed=1u;
        castle_ripples_ready=1u;
    }
    /* Trigger and advance every proximity wave before drawing the canvases. */
    const sat_vec3_t probe={player.feet.x,player.feet.y+6*ONE,player.feet.z};
    for (uint32_t r=0;r<CASTLE_RIPPLE_COUNT;++r) {
        const uint32_t i=castle_ripple_paintings[r];
        const sat_quad3_t *q=&castle_painting_quads[i];
        const sat_vec3_t tl=q->v[0],tr=q->v[1],bl=q->v[3];
        const sat_vec3_t uvec={tr.x-tl.x,tr.y-tl.y,tr.z-tl.z};
        const sat_vec3_t vvec={bl.x-tl.x,bl.y-tl.y,bl.z-tl.z};
        const sat_vec3_t delta={probe.x-tl.x,probe.y-tl.y,probe.z-tl.z};
        const int32_t uu=sat_fx16_mul(uvec.x,uvec.x)+sat_fx16_mul(uvec.y,uvec.y)+sat_fx16_mul(uvec.z,uvec.z);
        const int32_t vv=sat_fx16_mul(vvec.x,vvec.x)+sat_fx16_mul(vvec.y,vvec.y)+sat_fx16_mul(vvec.z,vvec.z);
        if (uu<=0 || vv<=0) continue;
        const int32_t u_norm=sat_fx16_div(sat_fx16_mul(delta.x,uvec.x)+sat_fx16_mul(delta.y,uvec.y)+sat_fx16_mul(delta.z,uvec.z),uu);
        const int32_t v_norm=sat_fx16_div(sat_fx16_mul(delta.x,vvec.x)+sat_fx16_mul(delta.y,vvec.y)+sat_fx16_mul(delta.z,vvec.z),vv);
        sat_vec3_t normal;
        sat_vec3_cross(&normal,&vvec,&uvec);
        sat_vec3_normalize(&normal,&normal);
        const int32_t w=sat_fx16_mul(delta.x,normal.x)+sat_fx16_mul(delta.y,normal.y)+sat_fx16_mul(delta.z,normal.z);
        const int32_t margin=ONE/4;
        const int in_bounds=u_norm>=-margin && u_norm<=ONE+margin &&
                             v_norm>=-margin && v_norm<=ONE+margin;
        const int near=in_bounds && w>-ONE && w<CASTLE_RIPPLE_TRIGGER;
        castle_ripple_state_t *st=&castle_ripples[r];
        if (!near) st->armed=1u;
        else if (st->armed && st->timer==0) {
            const int32_t cu=u_norm<0?0:(u_norm>ONE?ONE:u_norm);
            const int32_t cv=v_norm<0?0:(v_norm>ONE?ONE:v_norm);
            st->origin_u=sat_fx16_mul(cu,sat_fx16_sqrt(uu));
            st->origin_v=sat_fx16_mul(cv,sat_fx16_sqrt(vv));
            st->phase=0;
            st->timer=castle_ripple_waves[r].duration;
            st->armed=0u;
        }
        if (st->timer>0) --st->timer;
    }
#endif

    for (uint32_t i=0;i<CASTLE_PAINTING_COUNT;++i) {
#ifdef CASTLE_ROOM_CULLING
        if (!(visible_room_mask&(1u<<castle_painting_rooms[i]))) continue;
#endif
        const sat_quad3_t *q=&castle_painting_quads[i];
        int32_t cx=(q->v[0].x+q->v[2].x)>>1,cz=(q->v[0].z+q->v[2].z)>>1;
        int32_t dx=cx-camera.eye.x,dz=cz-camera.eye.z;
        int32_t depth=sat_fx16_mul(dx,fwd.x)+sat_fx16_mul(dz,fwd.z);
        if (depth<-24*ONE) continue;
#if CASTLE_RIPPLE_COUNT > 0
        const int ripple=castle_ripple_index(i);
        if (ripple>=0 && castle_ripples[ripple].timer>0) {
            castle_ripple_draw((uint32_t)ripple,q);
            ++hud_paintings_drawn;
            continue;
        }
#endif
        uint8_t ti_idx=castle_painting_tex_indices[i];
        SAT_PANIC_IF_ERROR(sat_scene_submit_quad(&scene,q,&painting_materials[ti_idx],SM64DS_ACTOR_PASS));
        ++hud_paintings_drawn;
    }
    for (uint32_t i=0;i<CASTLE_DOOR_COUNT;++i) {
#ifdef CASTLE_ROOM_CULLING
        if (!(visible_room_mask&(1u<<castle_door_rooms[i]))) continue;
#endif
        const sat_vec3_t pos=castle_door_positions[i];
        int32_t dx=pos.x-camera.eye.x,dz=pos.z-camera.eye.z;
        int32_t depth=sat_fx16_mul(dx,fwd.x)+sat_fx16_mul(dz,fwd.z);
        if (depth<-12*ONE || depth>360*ONE) continue;
        int32_t lat=sat_fx16_mul(dx,right.x)+sat_fx16_mul(dz,right.z);
        if (sat_fx16_abs(lat)>(depth>0?depth:0)+32*ONE) continue;
        door_prop.world=door_worlds[i];
        SAT_PANIC_IF_ERROR(sat_scene_submit_instance(&scene,&door_prop.instance,SAT_SCENE3D_SLOT_INHERIT,dp,dw));
        ++hud_doors_drawn;
    }
    for (uint32_t i=0;i<CASTLE_TOAD_COUNT;++i) {
#ifdef CASTLE_ROOM_CULLING
        if (!(visible_room_mask&(1u<<castle_toad_rooms[i]))) continue;
#endif
        const sat_vec3_t pos=castle_toad_positions[i];
        int32_t dx=pos.x-camera.eye.x,dz=pos.z-camera.eye.z;
        int32_t depth=sat_fx16_mul(dx,fwd.x)+sat_fx16_mul(dz,fwd.z);
        if (depth<2*ONE || depth>280*ONE) continue;
        int32_t lat=sat_fx16_mul(dx,right.x)+sat_fx16_mul(dz,right.z);
        if (sat_fx16_abs(lat)>depth+16*ONE) continue;
        toad_prop.world=toad_worlds[i];
        SAT_PANIC_IF_ERROR(sat_scene_submit_instance(&scene,&toad_prop.instance,SAT_SCENE3D_SLOT_INHERIT,tp,tw));
        ++hud_toads_drawn;
    }
}
#endif
