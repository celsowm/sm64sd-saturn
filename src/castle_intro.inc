/* Act III Lakitu intro cutscene; textually included by castle.c. */
#if defined(CASTLE_INTRO_PROPS_AVAILABLE) && !SM64DS_VISUAL_DIAGNOSTICS
static sat_result_t intro_service_cd_audio(void* ctx) {
    (void)ctx;
    return intro_audio_ready ? sat_audio_update() : SAT_OK;
}

static void intro_set_fade(int16_t v) {
    if (v<-255) v=-255;
    if (v>255) v=255;
    if (v==intro_fade_cur) return;
    intro_fade_cur=v;
    sat_vdp2_color_offset_t off={v,v,v};
    (void)sat_vdp2_color_offset_set(SAT_VDP2_COLOR_OFFSET_A,&off);
}

static void intro_play_sfx(sat_sound_t sfx,uint16_t vol) {
    if (!intro_audio_ready) return;
    sat_sound_play_params_t p={.volume=vol,.pan=0,.priority=12u,.flags=0u,.pitch=ONE,.start_tick=0u};
    (void)sat_sound_play(sfx,&p,0);
}

static void intro_init_audio(void) {
    if (sat_audio_init()!=SAT_OK) return;
    intro_audio_ready=1u;
    sat_sound_desc_t wd={0};
    wd.samples=castle_intro_whoosh_pcm;
    wd.sample_count=CASTLE_INTRO_WHOOSH_SAMPLES;
    wd.sample_rate=CASTLE_INTRO_SFX_RATE;
    wd.format=SAT_AUDIO_PCM_S8;
    (void)sat_sound_create(&intro_sfx_whoosh,&wd);
    sat_sound_desc_t pd={0};
    pd.samples=castle_intro_pipe_pcm;
    pd.sample_count=CASTLE_INTRO_PIPE_SAMPLES;
    pd.sample_rate=CASTLE_INTRO_SFX_RATE;
    pd.format=SAT_AUDIO_PCM_S8;
    (void)sat_sound_create(&intro_sfx_pipe,&pd);

    if (sat_cd_mount_default(&cd_block,intro_service_cd_audio,0,&cd_device,0u,&cd_volume)!=SAT_OK) return;
    intro_cd_mounted=1u;
    if (sat_disc_stream_init(&intro_disc,&cd_block)!=SAT_OK) return;
    intro_music_src_desc=(sat_cdfs_source_desc_t){
        SM64DS_AUDIO_OPENING_DISC_PATH,"disc/" SM64DS_AUDIO_OPENING_DISC_PATH,SM64DS_AUDIO_OPENING_BYTES
    };
    if (sat_cdfs_register_source_manifest(&cd_volume,&intro_music_src_desc,1u,&intro_music_src)!=SAT_OK) return;
    intro_music_asset_desc=(sat_asset_desc_t){0};
    intro_music_asset_desc.logical_path="music/opening";
    intro_music_asset_desc.source_path="disc/" SM64DS_AUDIO_OPENING_DISC_PATH;
    intro_music_asset_desc.size=intro_music_src.file.size;
    intro_music_asset_desc.sample_rate=SM64DS_AUDIO_OPENING_SAMPLE_RATE;
    intro_music_asset_desc.sample_count=SM64DS_AUDIO_OPENING_SAMPLE_COUNT;
    intro_music_asset_desc.channels=SM64DS_AUDIO_OPENING_CHANNELS;
    intro_music_asset_desc.format=SM64DS_AUDIO_OPENING_FORMAT;
    intro_music_asset_desc.kind=SAT_ASSET_STREAM;
    if (sat_asset_register_manifest(&intro_music_asset_desc,1u,&intro_music_asset)!=SAT_OK) return;
    sat_music_desc_t mdesc={
        .asset="music/opening",
        .disc=&intro_disc,
        .workspace=intro_music_ws,
        .workspace_bytes=sizeof(intro_music_ws),
        .ring_frames=16384u
    };
    if (sat_music_open(&intro_music,&mdesc)==SAT_OK) {
        if (sat_music_play(intro_music)==SAT_OK) intro_music_open=1u;
        else (void)sat_music_close(intro_music);
    }
}

static void intro_finish_cutscene(void) {
    if (!intro_cutscene_active) return;
    intro_cutscene_active=0u;
    if (intro_music_open) {
        (void)sat_music_stop(intro_music);
        (void)sat_music_close(intro_music);
        intro_music_open=0u;
    }
    if (intro_audio_ready) {
        (void)sat_audio_shutdown();
        intro_audio_ready=0u;
    }
    if (intro_cd_mounted) {
        (void)sat_cdfs_unmount(&cd_volume);
        intro_cd_mounted=0u;
    }
    (void)sat_vdp2_color_offset_disable(SAT_VDP2_LAYER_ALL);
    (void)sat_vdp2_layers_commit();
    sm64ds_player_reset(&player);
    yaw=spawn_yaw_default;
    camera_yaw=spawn_yaw_default;
    camera_choice=0;
    facing=spawn_facing_default;
    close_camera=1;
    clip=0;
    anim_time=0;
    paused=0;
}

static void intro_init_props(void) {
    SAT_PANIC_IF_ERROR(sat_mesh_init(&lakitu_mesh,lv,LN,li,LF));
    SAT_PANIC_IF_ERROR(sat_model_copy_to_mesh(&lakitu_actor_model,&lakitu_mesh));
    SAT_PANIC_IF_ERROR(sat_model_upload_textures(&lakitu_actor_model,lt,LT));
    for (uint16_t i=0u;i<LT;++i) {
        lmat[i]=(sat_scene3d_material_t){
            .kind=SAT_SCENE3D_INDEXED_TEXTURED,
            .rgb555=sm64ds_texture_fallback(&lakitu_actor_model,i),
            .texture=&lt[i],
            .color_calc_slot=SAT_INDEXED_SOLID_OPAQUE
        };
    }
    lmat[LT]=(sat_scene3d_material_t){
        .kind=SAT_SCENE3D_RGB,
        .rgb555=SAT_RGB555(28,28,28),
        .texture=0,
        .color_calc_slot=SAT_INDEXED_SOLID_OPAQUE
    };
    for (uint16_t i=0u;i<LF;++i) {
        uint16_t ti=lakitu_actor_model.face_texture_indices[i];
        lm[i]=(ti<LT)?ti:LT;
    }
    lakitu_inst=(sat_scene3d_instance_t){
        .mesh=&lakitu_mesh,.materials=lmat,.material_count=(uint16_t)(LT+1u),
        .face_materials=lm,.world=&lakitu_world,.pass=SM64DS_ACTOR_PASS,
        .cull_backfaces=SAT_SCENE3D_CULL_SCREEN
    };
    const sm64ds_background_buffers_t pb={pv,pi,pt,pmat,pm,PN,PF,PT};
    SAT_PANIC_IF_ERROR(sm64ds_background_init(&pipe_prop,&warp_pipe_model,&pb));
    pipe_prop.instance.pass=SM64DS_ACTOR_PASS;
    pipe_prop.instance.cull_backfaces=SAT_SCENE3D_CULL_SCREEN;
}

static int32_t intro_smoothstep_fx(uint32_t t,uint32_t dur) {
    if (dur==0u || t>=dur) return ONE;
    int32_t u=(int32_t)(((uint64_t)t*(uint64_t)ONE)/dur);
    int32_t u2=sat_fx16_mul(u,u);
    return sat_fx16_mul(u2,3*ONE-2*u);
}

static int32_t intro_lerp(int32_t a,int32_t b,int32_t s) {
    return a+sat_fx16_mul(b-a,s);
}

static sat_vec3_t intro_lerp_vec(sat_vec3_t a,sat_vec3_t b,int32_t s) {
    return (sat_vec3_t){intro_lerp(a.x,b.x,s),intro_lerp(a.y,b.y,s),intro_lerp(a.z,b.z,s)};
}

static void intro_update_cutscene_pose(int *out_mario_visible,int *out_pipe_visible,int *out_lakitu_visible) {
    const int32_t sy=player.spawn.y;
    const sat_vec3_t p0_eye={-96*ONE,118*ONE,130*ONE};
    const sat_vec3_t p1_eye={76*ONE,98*ONE,155*ONE};
    const sat_vec3_t p2_eye={40*ONE,sy+28*ONE,205*ONE};
    const sat_vec3_t p3_eye={26*ONE,sy+26*ONE,296*ONE};
    const sat_vec3_t p4_eye={player.spawn.x,sy+24*ONE,player.spawn.z+castle_stage.close_cam_dist*ONE};

    const sat_vec3_t t0={0,76*ONE,-45*ONE};
    const sat_vec3_t t1={0,62*ONE,-20*ONE};
    const sat_vec3_t t2={player.spawn.x,sy+14*ONE,player.spawn.z};
    const sat_vec3_t t3={player.spawn.x,sy+10*ONE,player.spawn.z};
    const sat_vec3_t t4={player.spawn.x,sy+8*ONE,player.spawn.z};

    if (intro_ticks<=18u) {
        intro_set_fade((int16_t)(255-((int32_t)intro_ticks*255)/18));
    } else {
        intro_set_fade(0);
    }

    if (intro_ticks>=105u && (intro_sfx_flags&1u)==0u) {
        intro_sfx_flags|=1u;
        intro_play_sfx(intro_sfx_whoosh,225u);
    }
    if (intro_ticks>=195u && (intro_sfx_flags&2u)==0u) {
        intro_sfx_flags|=2u;
        intro_play_sfx(intro_sfx_pipe,245u);
    }

    if (intro_ticks<95u) {
        int32_t s=intro_smoothstep_fx(intro_ticks,95u);
        camera.eye=intro_lerp_vec(p0_eye,p1_eye,s);
        camera.target=intro_lerp_vec(t0,t1,s);
    } else if (intro_ticks<185u) {
        int32_t s=intro_smoothstep_fx(intro_ticks-95u,90u);
        camera.eye=intro_lerp_vec(p1_eye,p2_eye,s);
        camera.target=intro_lerp_vec(t1,t2,s);
    } else if (intro_ticks<255u) {
        int32_t s=intro_smoothstep_fx(intro_ticks-185u,70u);
        camera.eye=intro_lerp_vec(p2_eye,p3_eye,s);
        camera.target=intro_lerp_vec(t2,t3,s);
    } else {
        int32_t s=intro_smoothstep_fx(intro_ticks-255u,40u);
        camera.eye=intro_lerp_vec(p3_eye,p4_eye,s);
        camera.target=intro_lerp_vec(t3,t4,s);
    }
    SAT_PANIC_IF_ERROR(sat_camera3d_update(&camera));

    *out_lakitu_visible=(intro_ticks>=95u && intro_ticks<255u)?1:0;
    if (*out_lakitu_visible) {
        const sat_skeleton_clip_t *lc=&lakitu_actor_clips[0];
        SAT_PANIC_IF_ERROR(sat_clip_sample(lc,intro_lakitu_anim,lpose,LJ));
        SAT_PANIC_IF_ERROR(sm64ds_clip_sample_scale(&lakitu_actor_scale_clips[0],lc,intro_lakitu_anim,lscales,LJ));
        SAT_PANIC_IF_ERROR(sm64ds_pose_world_matrices(&lakitu_actor_skeleton,lpose,lscales,lbones,LJ));
        SAT_PANIC_IF_ERROR(sat_skin_update_mesh(&lakitu_actor_skin,lbones,LJ,&lakitu_mesh,0,&lakitu_bounds));

        sat_vec3_t lpos;
        int32_t lyaw;
        if (intro_ticks<185u) {
            int32_t s=intro_smoothstep_fx(intro_ticks-95u,90u);
            lpos=intro_lerp_vec((sat_vec3_t){-36*ONE,62*ONE,130*ONE},(sat_vec3_t){-18*ONE,sy+22*ONE,242*ONE},s);
            lpos.x+=sat_sin_deg((int32_t)((intro_ticks*4u)%360u)*ONE)*10;
            lpos.y+=sat_sin_deg((int32_t)((intro_ticks*6u)%360u)*ONE)*3;
            lyaw=intro_lerp(20*ONE,55*ONE,s);
        } else {
            int32_t s=intro_smoothstep_fx(intro_ticks-185u,70u);
            lpos=intro_lerp_vec((sat_vec3_t){-18*ONE,sy+22*ONE,242*ONE},(sat_vec3_t){12*ONE,sy+36*ONE,310*ONE},s);
            lyaw=intro_lerp(55*ONE,190*ONE,s);
        }
        sat_model_transform3d_t ltr;
        sat_model_transform3d_identity(&ltr);
        ltr.position=lpos;
        ltr.rotation_deg.y=lyaw;
        ltr.scale=(sat_vec3_t){ONE/2,ONE/2,ONE/2};
        SAT_PANIC_IF_ERROR(sat_model_transform3d_matrix(&ltr,&lakitu_world));
    }

    *out_pipe_visible=(intro_ticks>=160u && intro_ticks<255u)?1:0;
    if (*out_pipe_visible) {
        int32_t sink=0;
        if (intro_ticks>228u) {
            int32_t s=intro_smoothstep_fx(intro_ticks-228u,27u);
            sink=sat_fx16_mul(16*ONE,s);
        }
        sat_model_transform3d_t ptr;
        sat_model_transform3d_identity(&ptr);
        ptr.position=(sat_vec3_t){player.spawn.x,sy-ONE-sink,player.spawn.z};
        ptr.scale=(sat_vec3_t){ONE/2,ONE/2,ONE/2};
        SAT_PANIC_IF_ERROR(sat_model_transform3d_matrix(&ptr,&pipe_prop.world));
    }

    *out_mario_visible=(intro_ticks>=195u)?1:0;
    player.feet=player.spawn;
    facing=180;
    if (intro_ticks>=195u && intro_ticks<230u) {
        uint32_t jt=intro_ticks-195u;
        int32_t u=(int32_t)(((uint64_t)jt*(uint64_t)ONE)/35u);
        int32_t arc=sat_fx16_mul(u,ONE-u)*72;
        int32_t rise=intro_lerp(-6*ONE,0,intro_smoothstep_fx(jt,12u));
        player.feet.y=sy+rise+arc;
        clip=3;
        anim_time=(int32_t)(((uint64_t)jt*10u*(uint64_t)ONE)/(35u*30u));
    } else {
        player.feet.y=sy;
        clip=0;
        anim_time=(int32_t)(((intro_ticks%120u)*(uint32_t)ONE)/30u);
    }
}
#endif
