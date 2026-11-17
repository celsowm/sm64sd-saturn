/* Playable local-ROM castle grounds prototype. No render LOD in collision. */
#include <saturn/app.h>
#include <saturn/input.h>
#include <saturn/scene.h>
#include <saturn/skin3d.h>
#include <saturn/color.h>
#include <saturn/font.h>
#include <saturn/vdp1.h>
#include <saturn/time.h>
#include "sm64ds_pose.h"
#include "sm64ds_background.h"
#include "sm64ds_play.h"
#include "mario_preview.h"
#include "mario_head.h"
#include "castle_scene.h"
#include "skybox_preview.h"

#define ONE SAT_FX16_ONE
#define N MARIO_PREVIEW_VERTEX_COUNT
#define F MARIO_PREVIEW_FACE_COUNT
#define T MARIO_PREVIEW_TEXTURE_COUNT
#define J MARIO_PREVIEW_JOINT_COUNT
#define CN CASTLE_VERTEX_COUNT
#define CF CASTLE_FACE_COUNT
#define CT CASTLE_TEXTURE_COUNT
#define BN SKYBOX_PREVIEW_VERTEX_COUNT
#define BF SKYBOX_PREVIEW_FACE_COUNT
#define BT SKYBOX_PREVIEW_TEXTURE_COUNT
#define HN MARIO_HEAD_VERTEX_COUNT
#define HF MARIO_HEAD_FACE_COUNT
#define HT MARIO_HEAD_TEXTURE_COUNT
#define CAP (F+CF+BF+HF)

static sat_vec3_t vertices[N],world_vertices[N];
static uint16_t indices[F*4],face_materials[F];
static sat_mesh_t mesh;
static sat_vdp1_texture_t textures[T];
static sat_scene3d_material_t materials[T];
#if SM64DS_VISUAL_DIAGNOSTICS && SM64DS_DIAG_FACE_IDS
static sat_scene3d_material_t diagnostic_face_materials[F] __attribute__((section(".wram_l"),aligned(4)));
#endif
#if SM64DS_VISUAL_DIAGNOSTICS && SM64DS_DIAG_CASTLE_FACE_IDS
static sat_scene3d_material_t diagnostic_castle_materials[CF] __attribute__((section(".wram_l"),aligned(4)));
#endif
static sat_projected_vertex_t projected[N];
static sat_scene3d_instance_t actor;
static sat_mat4_t actor_world;
static sat_skeleton_pose_joint_t pose[J];
static sat_vec3_t scales[J];
static sat_mat4_t bones[J];
static sat_aabb3_t bounds;
#if CF > 1337
static sat_scene3d_face_t faces[CAP] __attribute__((section(".wram_l"),aligned(4)));
#else
static sat_scene3d_face_t faces[CAP];
#endif
static uint32_t keys[CAP];
static uint16_t order[CAP];
static sat_scene_t scene;
static sat_ascii_font_t font;
static sm64ds_background_t castle,sky;
static sat_vec3_t cv[CN],cw[CN],bv[BN],bw[BN];
static uint16_t ci[CF*4],cm[CF],bi[BF*4],bm[BF];
/* Resident castle bindings are initialized once. Keep them in stock Low
 * WRAM so corrected material wrapping and detailed actor bakes fit High RAM. */
static sat_vdp1_texture_t ct[CT] __attribute__((section(".wram_l"),aligned(4)));
static sat_scene3d_material_t cmat[CT*2] __attribute__((section(".wram_l"),aligned(4)));
static sat_vdp1_texture_t bt[BT];
static sat_scene3d_material_t bmat[BT];
static sat_projected_vertex_t cp[CN],bp[BN];
static sm64ds_background_t head;
static sat_vec3_t hv[HN],hw[HN];
static uint16_t hi[HF*4],hm[HF];
static sat_vdp1_texture_t ht[HT];
static sat_scene3d_material_t hmat[HT];
static sat_projected_vertex_t hp[HN];
static sm64ds_player_t player;
static sat_camera3d_t camera;
static int yaw=0,camera_yaw=0,paused=0,facing=180,close_camera=0;
static uint8_t camera_choice=0;
static const int16_t camera_offsets[]={0,45,-45,90,-90,135,-135,180};
static uint16_t clip=0;
static int32_t anim_time=0;
/* Minimum camera-target distance below which the camera is not moved,
 * preventing the reverse-door view from backing the camera into Mario. */
static sat_vec3_t previous_camera_eye;
static int32_t previous_camera_clearance=0;
static const int32_t camera_safe_min=12*ONE;

/* Stable debugger telemetry: all values are captured from real frames. */
volatile struct {
    uint32_t magic,frames,ticks,jumps,landings,wall_hits,resets;
    int32_t x,y,z,velocity_y,camera_x,camera_y,camera_z;
    uint32_t grounded,clip,commands,skipped,faces,paused;
    uint32_t culled,clipped,fallback;
    uint32_t sky_clip_candidates,castle_clip_candidates,body_clip_candidates,head_clip_candidates;
    uint32_t texture_arena_initial,texture_arena_remaining,texture_estimate;
    int32_t requested_yaw,actual_camera_yaw,camera_clearance;
} g_sm64ds_castle_stats={.magic=0x43415331};

static void skin(void) {
    const sat_skeleton_clip_t *c=&mario_preview_clips[clip];
    SAT_PANIC_IF_ERROR(sat_clip_sample(c,anim_time,pose,J));
    SAT_PANIC_IF_ERROR(sm64ds_clip_sample_scale(&mario_preview_scale_clips[clip],c,anim_time,scales,J));
    SAT_PANIC_IF_ERROR(sm64ds_pose_world_matrices(&mario_preview_skeleton,pose,scales,bones,J));
    SAT_PANIC_IF_ERROR(sat_skin_update_mesh(&mario_preview_skin,bones,J,&mesh,0,&bounds));
}
static void reset(void) {
    sm64ds_player_reset(&player);yaw=0;camera_yaw=0;camera_choice=0;facing=180;anim_time=0;
}
static sat_vec3_t camera_candidate(int angle,int32_t distance) {
    int32_t s=sat_sin_deg(angle*ONE),c=sat_cos_deg(angle*ONE);
    return (sat_vec3_t){camera.target.x+sat_fx16_mul(s,distance),
        camera.target.y+distance*30/65,camera.target.z+sat_fx16_mul(c,distance)};
}
static void update_camera(void) {
    camera.target=(sat_vec3_t){player.feet.x,player.feet.y+8*ONE,player.feet.z};
    int32_t distance=(close_camera?35:65)*ONE;
    sat_vec3_t candidates[8];int32_t fractions[8]={0},clearance[8]={0};
    candidates[0]=camera_candidate(yaw,distance);
    fractions[0]=sm64ds_camera_fraction(&castle_collision,&camera.target,&candidates[0]);
    clearance[0]=sat_fx16_mul(distance,fractions[0]);
    if (clearance[0]>=25*ONE) camera_choice=0;
    else {
        if (camera_choice>0 && camera_choice<8) {
            int angle=(yaw+camera_offsets[camera_choice]+360)%360;
            candidates[camera_choice]=camera_candidate(angle,distance);
            fractions[camera_choice]=sm64ds_camera_fraction(&castle_collision,&camera.target,&candidates[camera_choice]);
            clearance[camera_choice]=sat_fx16_mul(distance,fractions[camera_choice]);
        }
        if (!camera_choice || clearance[camera_choice]<20*ONE) {
            for (uint8_t i=1;i<8;++i) {
                if (i==camera_choice) continue;
                int angle=(yaw+camera_offsets[i]+360)%360;
                candidates[i]=camera_candidate(angle,distance);
                fractions[i]=sm64ds_camera_fraction(&castle_collision,&camera.target,&candidates[i]);
                clearance[i]=sat_fx16_mul(distance,fractions[i]);
            }
            camera_choice=sm64ds_camera_select(clearance,8,camera_choice,20*ONE,25*ONE);
        }
    }
    camera_yaw=(yaw+camera_offsets[camera_choice]+360)%360;
    const sat_vec3_t desired=candidates[camera_choice];
    const int32_t t=fractions[camera_choice];
    /* If no candidate clears the safe minimum, hold the previous camera
     * position rather than backing into Mario. */
    if (clearance[camera_choice]>=camera_safe_min) {
        camera.eye=(sat_vec3_t){camera.target.x+sat_fx16_mul(desired.x-camera.target.x,t),
            camera.target.y+sat_fx16_mul(desired.y-camera.target.y,t),
            camera.target.z+sat_fx16_mul(desired.z-camera.target.z,t)};
        previous_camera_eye=camera.eye;
        previous_camera_clearance=clearance[camera_choice];
    } else {
        camera.eye=previous_camera_eye;
        g_sm64ds_castle_stats.camera_clearance=previous_camera_clearance;
        SAT_PANIC_IF_ERROR(sat_camera3d_update(&camera));
        return;
    }
    g_sm64ds_castle_stats.requested_yaw=yaw;
    g_sm64ds_castle_stats.actual_camera_yaw=camera_yaw;
    g_sm64ds_castle_stats.camera_clearance=clearance[camera_choice];
    SAT_PANIC_IF_ERROR(sat_camera3d_update(&camera));
}
static void simulation(const sat_pad_state_t *pad,uint8_t jump) {
    if(pad->held&SAT_PAD_L)yaw=(yaw+358)%360;
    if(pad->held&SAT_PAD_R)yaw=(yaw+2)%360;
    camera_yaw=(yaw+camera_offsets[camera_choice]+360)%360;
    int x=((pad->held&SAT_PAD_RIGHT)!=0)-((pad->held&SAT_PAD_LEFT)!=0);
    int z=((pad->held&SAT_PAD_DOWN)!=0)-((pad->held&SAT_PAD_UP)!=0);
    int32_t speed=(pad->held&SAT_PAD_B)?ONE*3/2:ONE*3/4;
    if(x&&z)speed=sat_fx16_mul(speed,46341);
    int32_t s=sat_sin_deg(camera_yaw*ONE),c=sat_cos_deg(camera_yaw*ONE);
    int32_t dx=sat_fx16_mul(x*c+z*s,speed),dz=sat_fx16_mul(z*c-x*s,speed);
    if(x||z) {
        int heading=z<0?(x<0?225:x>0?135:180):z>0?(x<0?315:x>0?45:0):(x<0?270:90);
        facing=(heading+camera_yaw)%360;
    }
    sm64ds_player_step(&player,&castle_collision,dx,dz,jump,(pad->held&SAT_PAD_B)!=0);
    uint16_t next=!player.grounded?3:player.moving?(player.running?2:1):0;
    if(next!=clip) {clip=next;anim_time=0;}
    anim_time+=ONE/60;
}

int main(void) {
    const sat_video_config_t video={320,224,SAT_VIDEO_AUTO,0};
    SAT_PANIC_IF_ERROR(sat_init(&video));
    /* This scene takes several fields to draw. Keep the completed picture
     * visible until VDP1 reaches END instead of swapping a partial list. */
    SAT_PANIC_IF_ERROR(sat_vdp1_set_frame_mode(SAT_VDP1_FRAME_ON_SUBMIT));
    uint32_t bytes=sat_model_vram_estimate_bytes(&mario_preview_model)+
        sat_model_vram_estimate_bytes(&castle_model)+sat_model_vram_estimate_bytes(&skybox_preview_model)+
        sat_model_vram_estimate_bytes(&mario_head_model);
    const uint32_t font_bytes=SAT_ASCII_FONT_GLYPH_COUNT*SAT_ASCII_FONT_GLYPH_WIDTH*SAT_ASCII_FONT_GLYPH_HEIGHT;
    const uint32_t arena_free=sat_vdp1_vram_free_bytes();
    g_sm64ds_castle_stats.texture_arena_initial=arena_free;
    g_sm64ds_castle_stats.texture_estimate=bytes+font_bytes;
    /* Font glyphs occupy individual 8x8 indexed textures in the same arena.
     * Leave room for alignment and future small runtime allocations. */
    if ((uint64_t)bytes+font_bytes+2048u>arena_free) SAT_PANIC_IF_ERROR(SAT_ERR_CAPACITY);
    SAT_PANIC_IF_ERROR(sat_mesh_init(&mesh,vertices,N,indices,F));
    SAT_PANIC_IF_ERROR(sat_model_copy_to_mesh(&mario_preview_model,&mesh));
    SAT_PANIC_IF_ERROR(sat_model_upload_textures(&mario_preview_model,textures,T));
    for(uint16_t i=0;i<T;++i) {
        materials[i].rgb555=sm64ds_texture_fallback(&mario_preview_model,i);
        materials[i].kind=SAT_SCENE3D_INDEXED_TEXTURED;materials[i].texture=&textures[i];
        materials[i].color_calc_slot=SAT_INDEXED_SOLID_OPAQUE;
    }
    for(uint16_t i=0;i<F;++i)face_materials[i]=mario_preview_model.face_texture_indices[i];
    const sm64ds_background_buffers_t cb={cv,ci,ct,cmat,cm,CN,CF,CT};
    const sm64ds_background_buffers_t bb={bv,bi,bt,bmat,bm,BN,BF,BT};
    const sm64ds_background_buffers_t hb={hv,hi,ht,hmat,hm,HN,HF,HT};
    SAT_PANIC_IF_ERROR(sm64ds_background_init(&castle,&castle_model,&cb));
    /* VDP1 indexed sprites cannot blend against another VDP1 sprite. Its
     * mesh mode provides bounded 50% coverage for DS partial-alpha faces. */
    for (uint16_t i=0;i<CT;++i) {
        cmat[CT+i]=cmat[i];
        cmat[CT+i].sprite_flags=SAT_SPRITE_FLAG_MESH;
    }
    for (uint16_t i=0;i<CF;++i)
        if (castle_polygon_alpha[i]<31u) cm[i]=(uint16_t)(cm[i]+CT);
    castle.instance.material_count=CT*2;
    SAT_PANIC_IF_ERROR(sm64ds_background_init(&sky,&skybox_preview_model,&bb));
    SAT_PANIC_IF_ERROR(sm64ds_background_init(&head,&mario_head_model,&hb));
    head.instance.pass=SM64DS_ACTOR_PASS;head.instance.cull_backfaces=1;
    castle.instance.pass=SM64DS_ACTOR_PASS;
    castle.instance.cull_backfaces=1;
    castle.instance.double_sided_faces=castle_double_sided;
    actor=(sat_scene3d_instance_t){.mesh=&mesh,.materials=materials,.material_count=T,
        .face_materials=face_materials,.world=&actor_world,.pass=SM64DS_ACTOR_PASS,.cull_backfaces=1};
#if SM64DS_VISUAL_DIAGNOSTICS
    if (SM64DS_DIAG_CASTLE_FALLBACK_COLOR) {
        /* Textured sprites ignore rgb555. Only the emergency polygon path
         * consumes it, exposing visible fallback coverage in captures. */
        for (uint16_t i=0;i<CT*2u;++i)
            if (cmat[i].rgb555) cmat[i].rgb555=SAT_RGB555(31,0,31);
    }
    if (SM64DS_DIAG_CLIP >= MARIO_PREVIEW_CLIP_COUNT || SM64DS_DIAG_FRAME < 0 ||
        SM64DS_DIAG_FRAME >= mario_preview_clips[SM64DS_DIAG_CLIP].frame_count)
        SAT_PANIC_IF_ERROR(SAT_ERR_INVALID_ARG);
    if (SM64DS_DIAG_NO_CULL) {
        castle.instance.cull_backfaces=0;
        actor.cull_backfaces=0;
        head.instance.cull_backfaces=0;
    }
    if (SM64DS_DIAG_SOLID) {
        sat_scene3d_material_t *sets[]={materials,cmat,hmat};
        const uint16_t counts[]={T,CT,HT};
        for (unsigned set=0;set<3;++set) for (uint16_t i=0;i<counts[set];++i) {
            /* Repeatable high-contrast colors keyed by the baked texture. */
            uint16_t r=(uint16_t)((i*13u+7u)&31u);
            uint16_t g=(uint16_t)((i*19u+11u)&31u);
            uint16_t b=(uint16_t)((i*23u+17u)&31u);
            sets[set][i].kind=SAT_SCENE3D_RGB;
            sets[set][i].rgb555=(uint16_t)(0x8000u|r|(g<<5)|(b<<10));
        }
    }
#if SM64DS_DIAG_FACE_IDS
    for (uint16_t i=0;i<F;++i) {
        diagnostic_face_materials[i]=(sat_scene3d_material_t){0};
        diagnostic_face_materials[i].kind=SAT_SCENE3D_RGB;
        /* Each 15-bit color uniquely identifies a body face, after RGB555
         * expansion; multiply by an odd value to spread adjacent IDs. */
        diagnostic_face_materials[i].rgb555=(uint16_t)(0x8000u|(((i+1u)*109u)&0x7fffu));
        diagnostic_face_materials[i].color_calc_slot=SAT_INDEXED_SOLID_OPAQUE;
        face_materials[i]=i;
    }
    actor.materials=diagnostic_face_materials;
    actor.material_count=F;
#endif
#if SM64DS_DIAG_CASTLE_FACE_IDS
    for (uint16_t i=0;i<CF;++i) {
        diagnostic_castle_materials[i]=(sat_scene3d_material_t){0};
        diagnostic_castle_materials[i].kind=SAT_SCENE3D_RGB;
        diagnostic_castle_materials[i].rgb555=(uint16_t)(0x8000u|(((i+1u)*109u)&0x7fffu));
        diagnostic_castle_materials[i].color_calc_slot=SAT_INDEXED_SOLID_OPAQUE;
        cm[i]=i;
    }
    castle.instance.materials=diagnostic_castle_materials;
    castle.instance.material_count=CF;
#endif
#endif
    SAT_PANIC_IF_ERROR(sat_scene_init(&scene,faces,keys,order,CAP));
    SAT_PANIC_IF_ERROR(sat_ascii_font_init_8x8_indexed8(&font,SAT_COLOR_WHITE,0,3));
    g_sm64ds_castle_stats.texture_arena_remaining=sat_vdp1_vram_free_bytes();
    player.spawn=(sat_vec3_t){0,100*ONE,256*ONE};
#if SM64DS_VISUAL_DIAGNOSTICS && SM64DS_DIAG_FIXED_CAMERA
    player.spawn.x=SM64DS_DIAG_X*ONE;
    player.spawn.z=SM64DS_DIAG_Z*ONE;
#endif
    int32_t floor;
#if SM64DS_VISUAL_DIAGNOSTICS && SM64DS_DIAG_FIXED_CAMERA
    const int32_t spawn_floor_ceiling=SM64DS_DIAG_FLOOR_CEILING*ONE;
#else
    const int32_t spawn_floor_ceiling=512*ONE;
#endif
    if(!sm64ds_floor(&castle_collision,player.spawn.x,player.spawn.z,spawn_floor_ceiling,&floor))
        SAT_PANIC_IF_ERROR(SAT_ERR_INVALID_ARG);
    player.spawn.y=floor;reset();
    /* The actor origin must not track the animated lowest vertex: doing so
     * cancels foot lift and moves the whole body (including the head) as
     * the pose changes. Calibrate once using the initial idle pose. */
    skin();
    const int32_t idle_ground_y=bounds.center.y-bounds.half.y;
    camera.up=(sat_vec3_t){0,ONE,0};camera.fov_y=60*ONE;
    camera.aspect=sat_fx16_div(320*ONE,224*ONE);camera.near_z=ONE;camera.far_z=1600*ONE;
    uint32_t previous=sat_time_ms(),accumulator=0;
    uint16_t jump_pending=0;
    while(1) {
        SAT_PANIC_IF_ERROR(sat_wait_vblank());
        sat_pad_state_t pad={0};SAT_PANIC_IF_ERROR(sat_pad_poll(&pad));
        uint32_t now=sat_time_ms(),elapsed=now-previous;previous=now;
        if(elapsed>250)elapsed=250;
        if(pad.pressed&SAT_PAD_START)paused=!paused;
        if(pad.pressed&SAT_PAD_C)reset();
        if(pad.pressed&SAT_PAD_X)close_camera=!close_camera;
        jump_pending|=pad.pressed&SAT_PAD_A;
        if(!paused) {
            accumulator+=elapsed*60;
            while(accumulator>=1000) {simulation(&pad,jump_pending!=0);jump_pending=0;accumulator-=1000;}
        } else {accumulator=0;jump_pending=0;}
#if SM64DS_VISUAL_DIAGNOSTICS && SM64DS_DIAG_FIXED_CAMERA
        /* Reproduce the same state even when render cadence changes pad polls. */
        sm64ds_player_reset(&player);
        yaw=((SM64DS_DIAG_YAW%360)+360)%360;
        close_camera=SM64DS_DIAG_CLOSE_CAMERA;
        facing=180;
#endif
#if SM64DS_VISUAL_DIAGNOSTICS
        clip=SM64DS_DIAG_CLIP;
        anim_time=(int32_t)(((int64_t)SM64DS_DIAG_FRAME*ONE+29)/30);
#endif
        skin();
        sat_model_transform3d_t transform;
        sat_model_transform3d_identity(&transform);
        transform.position=player.feet;transform.position.y-=idle_ground_y;
        transform.rotation_deg.y=facing*ONE;
        SAT_PANIC_IF_ERROR(sat_model_transform3d_matrix(&transform,&actor_world));
        SAT_PANIC_IF_ERROR(sat_mat4_multiply(&head.world,&actor_world,&bones[15]));
        update_camera();
        SAT_PANIC_IF_ERROR(sat_set_clear_color(SAT_RGB555(12,20,30)));
        SAT_PANIC_IF_ERROR(sat_begin_frame());
        SAT_PANIC_IF_ERROR(sat_scene_begin(&scene,&camera,camera.near_z,320,224,112));
        uint16_t previous_clipped=scene.faces.clipped_faces;
        if (!SM64DS_VISUAL_DIAGNOSTICS || (SM64DS_DIAG_OBJECTS&1))
            SAT_PANIC_IF_ERROR(sm64ds_background_submit(&sky,&scene,&camera.eye,bp,bw));
        g_sm64ds_castle_stats.sky_clip_candidates=scene.faces.clipped_faces-previous_clipped;
        previous_clipped=scene.faces.clipped_faces;
        if (!SM64DS_VISUAL_DIAGNOSTICS || (SM64DS_DIAG_OBJECTS&2))
            SAT_PANIC_IF_ERROR(sat_scene_submit_instance(&scene,&castle.instance,SAT_SCENE3D_SLOT_INHERIT,cp,cw));
        g_sm64ds_castle_stats.castle_clip_candidates=scene.faces.clipped_faces-previous_clipped;
        previous_clipped=scene.faces.clipped_faces;
        if (!SM64DS_VISUAL_DIAGNOSTICS || (SM64DS_DIAG_OBJECTS&4))
            SAT_PANIC_IF_ERROR(sat_scene_submit_instance(&scene,&actor,SAT_SCENE3D_SLOT_INHERIT,projected,world_vertices));
        g_sm64ds_castle_stats.body_clip_candidates=scene.faces.clipped_faces-previous_clipped;
        previous_clipped=scene.faces.clipped_faces;
        if (!SM64DS_VISUAL_DIAGNOSTICS || (SM64DS_DIAG_OBJECTS&8))
            SAT_PANIC_IF_ERROR(sat_scene_submit_instance(&scene,&head.instance,SAT_SCENE3D_SLOT_INHERIT,hp,hw));
        g_sm64ds_castle_stats.head_clip_candidates=scene.faces.clipped_faces-previous_clipped;
        SAT_PANIC_IF_ERROR(sat_scene_flush_trusted(&scene));
        SAT_PANIC_IF_ERROR(sat_draw_rect_screen(6,6,228,12,SAT_RGB555(0,0,0)));
        SAT_PANIC_IF_ERROR(sat_draw_rect_screen(6,206,308,12,SAT_RGB555(0,0,0)));
        SAT_PANIC_IF_ERROR(sat_ascii_font_draw_text_screen_indexed8(&font,
            paused?"PAUSED - START TO CONTINUE":"D-PAD MOVE  A JUMP  B RUN",8,8,8,3,0));
        SAT_PANIC_IF_ERROR(sat_ascii_font_draw_text_screen_indexed8(&font,"L/R CAM  X ZOOM  C RESET  START PAUSE",8,208,8,3,0));
        sat_scene_stats_t stats={0};sat_scene_stats(&scene,&stats);
        ++g_sm64ds_castle_stats.frames;g_sm64ds_castle_stats.ticks=player.ticks;
        g_sm64ds_castle_stats.jumps=player.jumps;g_sm64ds_castle_stats.landings=player.landings;
        g_sm64ds_castle_stats.wall_hits=player.wall_hits;g_sm64ds_castle_stats.resets=player.resets;
        g_sm64ds_castle_stats.x=player.feet.x;g_sm64ds_castle_stats.y=player.feet.y;g_sm64ds_castle_stats.z=player.feet.z;
        g_sm64ds_castle_stats.velocity_y=player.velocity_y;g_sm64ds_castle_stats.grounded=player.grounded;
        g_sm64ds_castle_stats.camera_x=camera.eye.x;g_sm64ds_castle_stats.camera_y=camera.eye.y;g_sm64ds_castle_stats.camera_z=camera.eye.z;
        g_sm64ds_castle_stats.clip=clip;g_sm64ds_castle_stats.commands=stats.commands_used;
        g_sm64ds_castle_stats.skipped=stats.skipped_faces;g_sm64ds_castle_stats.faces=stats.submitted_faces;
        g_sm64ds_castle_stats.paused=paused;
        g_sm64ds_castle_stats.culled=stats.culled_faces;
        g_sm64ds_castle_stats.clipped=stats.clipped_faces;
        g_sm64ds_castle_stats.fallback=stats.fallback_faces;
        SAT_PANIC_IF_ERROR(sat_end_frame());
    }
}
