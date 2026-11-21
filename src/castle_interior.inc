/* paintings, doors and Toads; textually included by castle.c. */
#ifdef CASTLE_INTERIOR_PROPS_AVAILABLE
static void submit_interior_props(void) {
    hud_paintings_drawn=0;hud_doors_drawn=0;hud_toads_drawn=0;
    sat_vec3_t fwd={camera.target.x-camera.eye.x,0,camera.target.z-camera.eye.z};
    sat_vec3_normalize(&fwd,&fwd);
    if (!fwd.x && !fwd.z) return;
    sat_vec3_t right={-fwd.z,0,fwd.x};

    for (uint32_t i=0;i<CASTLE_PAINTING_COUNT;++i) {
#ifdef CASTLE_ROOM_CULLING
        if (!(visible_room_mask&(1u<<castle_painting_rooms[i]))) continue;
#endif
        const sat_quad3_t *q=&castle_painting_quads[i];
        int32_t cx=(q->v[0].x+q->v[2].x)>>1,cz=(q->v[0].z+q->v[2].z)>>1;
        int32_t dx=cx-camera.eye.x,dz=cz-camera.eye.z;
        int32_t depth=sat_fx16_mul(dx,fwd.x)+sat_fx16_mul(dz,fwd.z);
        if (depth<-24*ONE) continue;
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
