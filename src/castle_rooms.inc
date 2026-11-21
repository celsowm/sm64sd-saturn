/* 1F room visibility; textually included by castle.c. */
#ifdef CASTLE_ROOM_CULLING
static void update_visible_rooms(void) {
    const int32_t px=player.feet.x,py=player.feet.y+6*ONE,pz=player.feet.z;
    const int32_t pad=4*ONE;
    int best=-1;
    int64_t best_vol=INT64_MAX;
    /* In Castle 1F, the basement corridor (r4) passes directly underneath the
     * main lobby (r0) with a smaller AABB. Keep r0 active whenever Mario is on
     * or above the lobby floor inside r0's bounds. */
    int in_r0=(px>=castle_room_min[0].x && px<=castle_room_max[0].x &&
               py>=castle_room_min[0].y && py<=castle_room_max[0].y &&
               pz>=castle_room_min[0].z && pz<=castle_room_max[0].z);
    if (in_r0 && player.feet.y>=-6*ONE && (pz>=-66*ONE || player.feet.y>=24*ONE)) {
        best=0;
    } else {
        for (uint8_t r=0;r<CASTLE_ROOM_COUNT;++r) {
            if (px>=castle_room_min[r].x && px<=castle_room_max[r].x &&
                py>=castle_room_min[r].y && py<=castle_room_max[r].y &&
                pz>=castle_room_min[r].z && pz<=castle_room_max[r].z) {
                int64_t dx=(int64_t)(castle_room_max[r].x-castle_room_min[r].x)>>12;
                int64_t dy=(int64_t)(castle_room_max[r].y-castle_room_min[r].y)>>12;
                int64_t dz=(int64_t)(castle_room_max[r].z-castle_room_min[r].z)>>12;
                int64_t vol=dx*dy*dz;
                if (vol<best_vol) { best_vol=vol;best=(int)r; }
            }
        }
    }
    if (best>=0) {
        current_room=(uint8_t)best;
    } else if (current_room>=CASTLE_ROOM_COUNT ||
               px<castle_room_min[current_room].x-pad || px>castle_room_max[current_room].x+pad ||
               py<castle_room_min[current_room].y-pad || py>castle_room_max[current_room].y+pad ||
               pz<castle_room_min[current_room].z-pad || pz>castle_room_max[current_room].z+pad) {
        /* Fallback to nearest room AABB when standing in an archway gap. */
        int64_t best_d2=INT64_MAX;
        for (uint8_t r=0;r<CASTLE_ROOM_COUNT;++r) {
            int32_t cx=px<castle_room_min[r].x?castle_room_min[r].x:(px>castle_room_max[r].x?castle_room_max[r].x:px);
            int32_t cy=py<castle_room_min[r].y?castle_room_min[r].y:(py>castle_room_max[r].y?castle_room_max[r].y:py);
            int32_t cz=pz<castle_room_min[r].z?castle_room_min[r].z:(pz>castle_room_max[r].z?castle_room_max[r].z:pz);
            int64_t dx=(px-cx)>>8,dy=(py-cy)>>8,dz=(pz-cz)>>8;
            int64_t d2=dx*dx+dy*dy+dz*dz;
            if (d2<best_d2) { best_d2=d2;current_room=r; }
        }
    }

    uint8_t mask=(uint8_t)(1u<<current_room);
    sat_vec3_t fwd={camera.target.x-camera.eye.x,0,camera.target.z-camera.eye.z};
    sat_vec3_normalize(&fwd,&fwd);
    sat_vec3_t right={-fwd.z,0,fwd.x};
    uint8_t drawn=1u;
#if defined(CASTLE_PORTAL_COUNT) && CASTLE_PORTAL_COUNT > 0
    /* Open an adjacent room only through an actual doorway portal connecting it
     * to current_room when Mario is near the doorway and looking toward it. */
    const int32_t max_reach=(current_room==0u)?(56*ONE):(96*ONE);
    const int32_t portal_py=player.feet.y+8*ONE;
    const int32_t max_pdy=player.grounded?(10*ONE):(18*ONE);
    for (uint32_t p=0;p<CASTLE_PORTAL_COUNT;++p) {
        uint8_t ra=castle_portal_room_a[p],rb=castle_portal_room_b[p];
        uint8_t other;
        if (ra==current_room) other=rb;
        else if (rb==current_room) other=ra;
        else continue;
        if (other>=CASTLE_ROOM_COUNT || (mask&(1u<<other))) continue;
        const sat_vec3_t pos=castle_portal_pos[p];
        int32_t pdx=sat_fx16_abs(px-pos.x);
        int32_t pdy=sat_fx16_abs(portal_py-pos.y);
        int32_t pdz=sat_fx16_abs(pz-pos.z);
        if (pdy>max_pdy) continue;
        int open=0;
        if (pdx<=24*ONE && pdz<=24*ONE) {
            /* Always keep the adjacent room live while straddling its doorway. */
            open=1;
        } else if (pdx<=max_reach && pdz<=max_reach) {
            int32_t dx=pos.x-camera.eye.x,dz=pos.z-camera.eye.z;
            int32_t depth=sat_fx16_mul(dx,fwd.x)+sat_fx16_mul(dz,fwd.z);
            int32_t lat=sat_fx16_mul(dx,right.x)+sat_fx16_mul(dz,right.z);
            int32_t cone=(depth>0?(depth*7)/8:0)+22*ONE;
            if (depth>-12*ONE && sat_fx16_abs(lat)<=cone) open=1;
        }
        if (open) {
            mask|=(uint8_t)(1u<<other);
            ++drawn;
        }
    }
#else
    uint8_t adj=castle_room_adj[current_room];
    for (uint8_t r=0;r<CASTLE_ROOM_COUNT;++r) {
        if (r==current_room || !(adj&(1u<<r))) continue;
        int32_t cx=px<castle_room_min[r].x?castle_room_min[r].x:(px>castle_room_max[r].x?castle_room_max[r].x:px);
        int32_t cy=py<castle_room_min[r].y?castle_room_min[r].y:(py>castle_room_max[r].y?castle_room_max[r].y:py);
        int32_t cz=pz<castle_room_min[r].z?castle_room_min[r].z:(pz>castle_room_max[r].z?castle_room_max[r].z:pz);
        int32_t pdx=sat_fx16_abs(px-cx),pdy=sat_fx16_abs(py-cy),pdz=sat_fx16_abs(pz-cz);
        if (pdx>112*ONE || pdy>64*ONE || pdz>112*ONE) continue;
        int32_t max_depth=INT32_MIN;
        int32_t min_lat=INT32_MAX,max_lat=INT32_MIN;
        const int32_t xs[2]={castle_room_min[r].x,castle_room_max[r].x};
        const int32_t zs[2]={castle_room_min[r].z,castle_room_max[r].z};
        for (int ix=0;ix<2;++ix) for (int iz=0;iz<2;++iz) {
            int32_t dx=xs[ix]-camera.eye.x,dz=zs[iz]-camera.eye.z;
            int32_t depth=sat_fx16_mul(dx,fwd.x)+sat_fx16_mul(dz,fwd.z);
            int32_t lat=sat_fx16_mul(dx,right.x)+sat_fx16_mul(dz,right.z);
            if (depth>max_depth) max_depth=depth;
            if (lat<min_lat) min_lat=lat;
            if (lat>max_lat) max_lat=lat;
        }
        if (max_depth<0) continue;
        int32_t cone=(max_depth*3)/4+24*ONE;
        if (max_lat<-cone || min_lat>cone) continue;
        mask|=(uint8_t)(1u<<r);
        ++drawn;
    }
#endif
    visible_room_mask=mask;
    hud_rooms_drawn=drawn;
}
#endif
