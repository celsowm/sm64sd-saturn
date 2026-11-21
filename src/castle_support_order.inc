/* support-plane painter ordering; textually included by castle.c. */
#if !SM64DS_VISUAL_DIAGNOSTICS && defined(CASTLE_SUPPORT_PLANE_LIST_AVAILABLE)
/* Push walkable terrain planes that lie strictly beneath Mario and the camera
 * behind Mario's farthest painter depth so sloped hills cannot sort over him. */
static void order_support_behind_actor(uint16_t castle_first,uint16_t castle_end,
                                       uint16_t shadow_first,uint16_t actor_first,
                                       uint16_t actor_end) {
    hud_support_pushed=0;
    if (actor_first>=actor_end) return;
    const uint8_t group=(uint8_t)(255u-castle.instance.pass);
    uint32_t actor_max=0;
    int has_actor=0;
    for (uint16_t q=actor_first;q<actor_end;++q) {
        uint32_t key=scene.faces.keys[q];
        if ((key>>24)==group) {
            uint32_t d=key&0xffffffu;
            if (d>actor_max) actor_max=d;
            has_actor=1;
        }
    }
    if (!has_actor) return;

    /* Ensure Mario's grounded contact shadow draws behind Mario's feet while
     * staying in front of any support ground face pushed to actor_max. */
    if (shadow_first<actor_first) {
        uint32_t skey=scene.faces.keys[shadow_first];
        if ((skey>>24)==group && (skey&0xffffffu)<actor_max)
            scene.faces.keys[shadow_first]=(skey&0xff000000u)|actor_max;
    }

    int ax0=32767,ax1=-32768,ay0=32767,ay1=-32768;
    for (unsigned v=0;v<N;++v) {
        if (projected[v].w>0) {
            if (projected[v].x<ax0) ax0=projected[v].x;
            if (projected[v].x>ax1) ax1=projected[v].x;
            if (projected[v].y<ay0) ay0=projected[v].y;
            if (projected[v].y>ay1) ay1=projected[v].y;
        }
    }
    for (unsigned v=0;v<HN;++v) {
        if (hp[v].w>0) {
            if (hp[v].x<ax0) ax0=hp[v].x;
            if (hp[v].x>ax1) ax1=hp[v].x;
            if (hp[v].y<ay0) ay0=hp[v].y;
            if (hp[v].y>ay1) ay1=hp[v].y;
        }
    }
    if (ax0>ax1 || ay0>ay1) return;

    for (uint32_t scan=0;scan<CASTLE_SUPPORT_PLANE_COUNT;++scan) {
#ifdef CASTLE_ROOM_CULLING
        uint8_t sroom=castle_support_rooms[scan];
        uint16_t qfirst=room_qfirst[sroom],qend=room_qend[sroom];
        if (qfirst>=qend) continue;
        uint16_t vbase=castle_room_vfirst[sroom];
#elif defined(CASTLE_CHUNK_CULLING)
        uint8_t schunk=castle_support_chunks[scan];
        uint16_t qfirst=chunk_qfirst[schunk],qend=chunk_qend[schunk];
        if (qfirst>=qend) continue;
        uint16_t vbase=castle_chunk_vfirst[schunk];
#else
        const uint16_t qfirst=castle_first,qend=castle_end;
        const uint16_t vbase=0u;
#endif
        uint32_t f=castle_support_faces[scan];
        if (f>=CF) continue;
        const uint16_t *is=&ci[f*4u];
        const uint16_t i0=(uint16_t)(vbase+is[0]),i1=(uint16_t)(vbase+is[1]),
                       i2=(uint16_t)(vbase+is[2]),i3=(uint16_t)(vbase+is[3]);
        if (cp[i0].w<=0 || cp[i1].w<=0 || cp[i2].w<=0 || cp[i3].w<=0) continue;
        const uint16_t idx[4]={i0,i1,i2,i3};
        int x0=cp[i0].x,x1=x0,y0=cp[i0].y,y1=y0;
        int64_t sum=cp[i0].w;
        for (unsigned k=1;k<4;++k) {
            int px=cp[idx[k]].x,py=cp[idx[k]].y;
            if (px<x0) x0=px;
            if (px>x1) x1=px;
            if (py<y0) y0=py;
            if (py>y1) y1=py;
            sum+=cp[idx[k]].w;
        }
        if (x1<ax0-2 || x0>ax1+2 || y1<ay0-2 || y0>ay1+2) continue;
        int64_t depth=sum>0?(sum>>6):0;
        if (depth>0xfffffe) depth=0xfffffe;
        if ((uint32_t)depth>=actor_max) continue;

        const sat_vec3_t n=castle_support_normals[scan];
        const sat_vec3_t p=cv[i0];
        int64_t plane=(int64_t)p.x*n.x+(int64_t)p.y*n.y+(int64_t)p.z*n.z;
        int64_t cam_side=(int64_t)camera.eye.x*n.x+(int64_t)camera.eye.y*n.y+
                         (int64_t)camera.eye.z*n.z-plane;
        if (cam_side<=((int64_t)ONE*ONE/256)) continue;
        int64_t foot_side=(int64_t)player.feet.x*n.x+(int64_t)player.feet.y*n.y+
                          (int64_t)player.feet.z*n.z-plane;
        if (foot_side<-((int64_t)ONE*ONE*3/4)) continue;
        int64_t torso_side=foot_side+(int64_t)(4*ONE)*n.y;
        if (torso_side<=0) continue;

        uint32_t expected_key=((uint32_t)group<<24)|(uint32_t)depth;
        for (uint16_t q=qfirst;q<qend;++q) {
            if (scene.faces.keys[q]!=expected_key) continue;
            sat_scene3d_face_t expanded;
            if (sat_scene3d_faces_get(&scene.faces,q,&expanded)!=SAT_OK) continue;
            unsigned k;
            for (k=0;k<4;++k)
                if (expanded.projected.x[k]!=cp[idx[k]].x || expanded.projected.y[k]!=cp[idx[k]].y) break;
            if (k==4) {
                uint32_t pushed=actor_max<0xfffffcu?actor_max+2u:actor_max;
                scene.faces.keys[q]=((uint32_t)group<<24)|pushed;
                ++hud_support_pushed;
                break;
            }
        }
    }
    /* Near-clipped horizontal floor/carpet fallback faces (!projected_safe) are
     * skipped by the unclipped vertex test above because a corner lies behind
     * the camera. Use their exact 3D world corners to keep floors between the
     * camera and Mario behind Mario without disturbing distant geometry. */
    const uint32_t clipped_pushed=((uint32_t)group<<24)|(actor_max<0xfffffcu?actor_max+2u:actor_max);
    const int32_t sx0=(camera.eye.x<player.feet.x?camera.eye.x:player.feet.x)-12*ONE;
    const int32_t sx1=(camera.eye.x>player.feet.x?camera.eye.x:player.feet.x)+12*ONE;
    const int32_t sz0=(camera.eye.z<player.feet.z?camera.eye.z:player.feet.z)-12*ONE;
    const int32_t sz1=(camera.eye.z>player.feet.z?camera.eye.z:player.feet.z)+12*ONE;
    for (uint16_t q=castle_first;q<castle_end;++q) {
        uint32_t qk=scene.faces.keys[q];
        if ((qk>>24)!=group || (qk&0xffffffu)>=actor_max) continue;
        sat_scene3d_face_t expanded;
        if (sat_scene3d_faces_get(&scene.faces,q,&expanded)!=SAT_OK) continue;
        if (expanded.projected_safe) continue;
        int32_t min_x=expanded.world.v[0].x,max_x=min_x;
        int32_t min_y=expanded.world.v[0].y,max_y=min_y;
        int32_t min_z=expanded.world.v[0].z,max_z=min_z;
        for (unsigned k=1;k<4;++k) {
            int32_t wx=expanded.world.v[k].x,wy=expanded.world.v[k].y,wz=expanded.world.v[k].z;
            if (wx<min_x) min_x=wx;
            if (wx>max_x) max_x=wx;
            if (wy<min_y) min_y=wy;
            if (wy>max_y) max_y=wy;
            if (wz<min_z) min_z=wz;
            if (wz>max_z) max_z=wz;
        }
        if (max_y-min_y>ONE*2) continue;
        if (camera.eye.y<=max_y+ONE/4) continue;
        if (player.feet.y+ONE/2<max_y) continue;
        if (max_x<sx0 || min_x>sx1 || max_z<sz0 || min_z>sz1) continue;
        scene.faces.keys[q]=clipped_pushed;
        ++hud_support_pushed;
    }
#if defined(CASTLE_ROOM_CULLING) && defined(CASTLE_FLOOR_DECAL_COUNT)
    /* Keep room-0 floor decals (Sun Carpet) cleanly over the sunken pit floor
     * while remaining strictly behind Mario and Mario's shadow when stepped on. */
    if (CASTLE_FLOOR_DECAL_COUNT>0u && (visible_room_mask&1u)) {
        const uint16_t vbase=castle_room_vfirst[0];
        const uint32_t pushed_key=((uint32_t)group<<24)|(actor_max<0xfffffcu?actor_max+2u:actor_max);
        for (uint32_t d=0;d<CASTLE_FLOOR_DECAL_COUNT;++d) {
            uint32_t f=castle_floor_decals[d];
            if (f>=CF) continue;
            const uint16_t *is=&ci[f*4u];
            const uint16_t idx[4]={(uint16_t)(vbase+is[0]),(uint16_t)(vbase+is[1]),
                                   (uint16_t)(vbase+is[2]),(uint16_t)(vbase+is[3])};
            if (cp[idx[0]].w<=0 || cp[idx[1]].w<=0 || cp[idx[2]].w<=0 || cp[idx[3]].w<=0) continue;
            int64_t sum=(int64_t)cp[idx[0]].w+cp[idx[1]].w+cp[idx[2]].w+cp[idx[3]].w;
            int64_t depth=sum>0?(sum>>6):0;
            if (depth>0xfffffe) depth=0xfffffe;
            uint32_t expected_key=((uint32_t)group<<24)|(uint32_t)depth;
            for (uint16_t q=castle_first;q<castle_end;++q) {
                uint32_t qk=scene.faces.keys[q];
                if (qk!=expected_key && qk!=pushed_key) continue;
                sat_scene3d_face_t expanded;
                if (sat_scene3d_faces_get(&scene.faces,q,&expanded)!=SAT_OK) continue;
                unsigned k;
                for (k=0;k<4;++k)
                    if (expanded.projected.x[k]!=cp[idx[k]].x || expanded.projected.y[k]!=cp[idx[k]].y) break;
                if (k==4) {
                    if (qk==pushed_key) {
                        uint32_t decal_pushed=actor_max<0xfffffdu?actor_max+1u:actor_max;
                        scene.faces.keys[q]=((uint32_t)group<<24)|decal_pushed;
                    } else {
                        /* 49152 in (sum>>6) is ~12 world units: clears the wider
                         * sunken pit floor strips beneath the Sun Carpet. */
                        uint32_t biased=depth>49152?(uint32_t)(depth-49152):0u;
                        if (biased<=actor_max) {
                            int x0=cp[idx[0]].x,x1=x0,y0=cp[idx[0]].y,y1=y0;
                            for (unsigned j=1;j<4;++j) {
                                if (cp[idx[j]].x<x0) x0=cp[idx[j]].x;
                                if (cp[idx[j]].x>x1) x1=cp[idx[j]].x;
                                if (cp[idx[j]].y<y0) y0=cp[idx[j]].y;
                                if (cp[idx[j]].y>y1) y1=cp[idx[j]].y;
                            }
                            if (x1>=ax0-2 && x0<=ax1+2 && y1>=ay0-2 && y0<=ay1+2)
                                biased=actor_max<0xfffffdu?actor_max+1u:actor_max;
                        }
                        scene.faces.keys[q]=((uint32_t)group<<24)|biased;
                    }
                    break;
                }
            }
        }
    }
#endif
}
#endif
