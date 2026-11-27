/* Playable local-ROM castle prototype (exterior + interior 1F). No render LOD in collision. */
#include <saturn/app.h>
#include <saturn/input.h>
#include <saturn/scene.h>
#include <saturn/skin3d.h>
#include <saturn/math2d.h>
#include <saturn/color.h>
#include <saturn/font.h>
#include <saturn/vdp1.h>
#include <saturn/time.h>
#include <saturn/cd_mount.h>
#include <saturn/exec.h>
#include <limits.h>
#include "sm64ds_pose.h"
#include "sm64ds_background.h"
#include "sm64ds_actors.h"
#include "sm64ds_play.h"
#include "sm64ds_painter.h"
#include "sm64ds_stage_handoff.h"
#include "mario_preview.h"
#include "mario_head.h"
#include "castle_scene.h"
#ifndef SM64DS_VISUAL_DIAGNOSTICS
#define SM64DS_VISUAL_DIAGNOSTICS 0
#endif
#ifndef SM64DS_DIAG_OBJECTS
#define SM64DS_DIAG_OBJECTS 15
#endif
#ifndef SM64DS_DIAG_WALL_FIXTURE
#define SM64DS_DIAG_WALL_FIXTURE 0
#endif
#ifndef SM64DS_DIAG_FACE_IDS
#define SM64DS_DIAG_FACE_IDS 0
#endif
#ifndef SM64DS_DIAG_CASTLE_FACE_IDS
#define SM64DS_DIAG_CASTLE_FACE_IDS 0
#endif
#ifndef SM64DS_DIAG_SOLID
#define SM64DS_DIAG_SOLID 0
#endif
#ifndef SM64DS_DIAG_FAR_DEPTH_COUNT
#define SM64DS_DIAG_FAR_DEPTH_COUNT 0
#endif
#ifndef SM64DS_DIAG_SHOW_UI
#define SM64DS_DIAG_SHOW_UI 0
#endif
#ifndef SM64DS_VDP2_SKY
#define SM64DS_VDP2_SKY 0
#endif
#if SM64DS_VDP2_SKY
/* The sky is a VDP2 panorama: the VDP1 skybox mesh is not built. */
#undef CASTLE_HAS_SKYBOX
#define CASTLE_HAS_SKYBOX 0
#endif
#ifndef CASTLE_HAS_SKYBOX
#define CASTLE_HAS_SKYBOX 1
#endif
#if CASTLE_HAS_SKYBOX
#include "skybox_preview.h"
#endif
#if SM64DS_VDP2_SKY
#include <saturn/lz.h>
#include <saturn/math2d.h>
#include <saturn/vdp2_layers.h>
#include "sky_panorama.h"
#endif
#ifdef CASTLE_WATER_LAYERS
#include <saturn/vdp2_color_offset.h>
#include <saturn/vdp2_layers.h>
#endif
#ifdef CASTLE_WATER_PLANE
#include <saturn/water_plane.h>
#endif
#if defined(CASTLE_INTRO_PROPS_AVAILABLE) && !SM64DS_VISUAL_DIAGNOSTICS
#include <saturn/asset.h>
#include <saturn/audio.h>
#include <saturn/disc_stream.h>
#include <saturn/music.h>
#include <saturn/music_codecs.h>
#include <saturn/vdp2_color_offset.h>
#include <saturn/vdp2_layers.h>
#include "lakitu_actor.h"
#include "warp_pipe.h"
#include "castle_intro_sfx.h"
#include "intro_audio_meta.h"
SAT_MUSIC_CODECS_ADX_FROM_DISC_ONLY;
#endif

#define ONE SAT_FX16_ONE
#define N MARIO_PREVIEW_VERTEX_COUNT
#define F MARIO_PREVIEW_FACE_COUNT
#define T MARIO_PREVIEW_TEXTURE_COUNT
#define J MARIO_PREVIEW_JOINT_COUNT
#define CN CASTLE_VERTEX_COUNT
#define CF CASTLE_FACE_COUNT
#define CT CASTLE_TEXTURE_COUNT
#if CASTLE_HAS_SKYBOX
#define BN SKYBOX_PREVIEW_VERTEX_COUNT
#define BF SKYBOX_PREVIEW_FACE_COUNT
#define BT SKYBOX_PREVIEW_TEXTURE_COUNT
#else
#define BF 0u
#endif
#define HN MARIO_HEAD_VERTEX_COUNT
#define HF MARIO_HEAD_FACE_COUNT
#define HT MARIO_HEAD_TEXTURE_COUNT
#ifdef CASTLE_PROPS_AVAILABLE
#define SN CASTLE_SIGN_VERTEX_COUNT
#define SF CASTLE_SIGN_FACE_COUNT
#define ST CASTLE_SIGN_TEXTURE_COUNT
#define EXT_PROP_CAP (CASTLE_TREE_COUNT + CASTLE_SIGN_COUNT * SF)
#else
#define EXT_PROP_CAP 0u
#endif
#ifdef CASTLE_INTERIOR_PROPS_AVAILABLE
#define DN CASTLE_DOOR_VERTEX_COUNT
#define DF CASTLE_DOOR_FACE_COUNT
#define DT CASTLE_DOOR_TEXTURE_COUNT
#define TN CASTLE_TOAD_VERTEX_COUNT
#define TF CASTLE_TOAD_FACE_COUNT
#define TT CASTLE_TOAD_TEXTURE_COUNT
#define INT_PROP_CAP (CASTLE_PAINTING_COUNT + CASTLE_DOOR_COUNT * DF + 2u * TF)
#else
#define INT_PROP_CAP 0u
#endif
#ifdef CASTLE_ACTOR_FACE_CAP
#define ACTOR_CAP CASTLE_ACTOR_FACE_CAP
#else
#define ACTOR_CAP 0u
#endif
#define PROP_CAP (EXT_PROP_CAP + INT_PROP_CAP + ACTOR_CAP)
/* The Low WRAM face queue is a fixed 1 MiB region. Cap the total so large
 * courses (JRB ~4.8k faces) still link; the stage drops far chunks beyond
 * this. 2048 keeps the queue + projected cache + index scratch under budget. */
#define CAP_TOTAL (F+CF+BF+HF+1u+PROP_CAP+(SM64DS_VISUAL_DIAGNOSTICS && SM64DS_DIAG_WALL_FIXTURE ? 1 : 0))
#if CAP_TOTAL > 2048
#define CAP 2048u
#else
#define CAP CAP_TOTAL
#endif

static sat_vec3_t vertices[N],world_vertices[N];
static uint16_t indices[F*4],face_materials[F];
static sat_mesh_t mesh;
static sat_vdp1_texture_t textures[T] __attribute__((section(".wram_l"),aligned(4)));
static sat_scene3d_material_t materials[T] __attribute__((section(".wram_l"),aligned(4)));
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
static sat_scene3d_face_t faces[CAP] __attribute__((section(".wram_l"),aligned(4)));
#if !SM64DS_VISUAL_DIAGNOSTICS
static sat_scene3d_projected_face_t projected_faces[CAP] __attribute__((section(".wram_l"),aligned(4)));
static sat_scene3d_material_program_t castle_prog_entries[CT*2] __attribute__((section(".wram_l"),aligned(4)));
#if CASTLE_HAS_SKYBOX
static sat_scene3d_material_program_t sky_prog_entries[BT] __attribute__((section(".wram_l"),aligned(4)));
static sat_scene3d_material_programs_t sky_programs;
static sat_scene3d_instance_binding_t sky_binding;
#endif
static sat_scene3d_material_program_t actor_prog_entries[T] __attribute__((section(".wram_l"),aligned(4)));
static sat_scene3d_material_program_t head_prog_entries[HT] __attribute__((section(".wram_l"),aligned(4)));
#ifdef CASTLE_PROPS_AVAILABLE
static sat_scene3d_material_program_t sign_prog_entries[ST] __attribute__((section(".wram_l"),aligned(4)));
static sat_scene3d_material_programs_t sign_programs;
static sat_scene3d_instance_binding_t sign_binding;
#endif
#ifdef CASTLE_INTERIOR_PROPS_AVAILABLE
static sat_scene3d_material_program_t door_prog_entries[DT] __attribute__((section(".wram_l"),aligned(4)));
static sat_scene3d_material_programs_t door_programs;
static sat_scene3d_instance_binding_t door_binding;
static sat_scene3d_material_program_t toad_prog_entries[TT] __attribute__((section(".wram_l"),aligned(4)));
static sat_scene3d_material_programs_t toad_programs;
static sat_scene3d_instance_binding_t toad_binding;
#endif
static sat_scene3d_material_programs_t castle_programs,actor_programs,head_programs;
static sat_scene3d_instance_binding_t castle_binding,actor_binding,head_binding;
#ifdef CASTLE_ROOM_CULLING
static sat_scene3d_instance_binding_t room_bindings[CASTLE_ROOM_COUNT];
#elif defined(CASTLE_CHUNK_CULLING)
static sat_scene3d_instance_binding_t chunk_bindings[CASTLE_CHUNK_COUNT] __attribute__((section(".wram_l"),aligned(4)));
#endif
#endif
/* Low WRAM: the High WRAM image also holds the dual-SH-2 runtime. */
static uint32_t keys[CAP] __attribute__((section(".wram_l"),aligned(4)));
static uint16_t order[CAP] __attribute__((section(".wram_l"),aligned(4)));
static sat_scene_t scene;
static sat_ascii_font_t font;
static sm64ds_background_t castle;
#ifdef CASTLE_ROOM_CULLING
static sat_mesh_t room_meshes[CASTLE_ROOM_COUNT];
static sat_scene3d_instance_t room_instances[CASTLE_ROOM_COUNT];
static uint16_t room_qfirst[CASTLE_ROOM_COUNT],room_qend[CASTLE_ROOM_COUNT];
static uint8_t current_room=0;
static uint8_t visible_room_mask=1u;
static uint8_t hud_rooms_drawn=1u;
#elif defined(CASTLE_CHUNK_CULLING)
static sat_mesh_t chunk_meshes[CASTLE_CHUNK_COUNT] __attribute__((section(".wram_l"),aligned(4)));
static sat_scene3d_instance_t chunk_instances[CASTLE_CHUNK_COUNT] __attribute__((section(".wram_l"),aligned(4)));
static uint16_t chunk_qfirst[CASTLE_CHUNK_COUNT],chunk_qend[CASTLE_CHUNK_COUNT];
static uint8_t hud_chunks_drawn=0u;
#endif
/* Static castle geometry buffers are copied once at init; castle.world is
 * identity so cv[] is already world-space (no per-frame cw[] copy needed). */
static sat_vec3_t cv[CN] __attribute__((section(".wram_l"),aligned(4)));
static uint16_t ci[CF*4] __attribute__((section(".wram_l"),aligned(4)));
static uint16_t cm[CF] __attribute__((section(".wram_l"),aligned(4)));
#if CASTLE_HAS_SKYBOX
static sm64ds_background_t sky;
static sat_vec3_t bv[BN] __attribute__((section(".wram_l"),aligned(4)));
static sat_vec3_t bw[BN] __attribute__((section(".wram_l"),aligned(4)));
static uint16_t bi[BF*4] __attribute__((section(".wram_l"),aligned(4)));
static uint16_t bm[BF] __attribute__((section(".wram_l"),aligned(4)));
static sat_vdp1_texture_t bt[BT] __attribute__((section(".wram_l"),aligned(4)));
static sat_scene3d_material_t bmat[BT] __attribute__((section(".wram_l"),aligned(4)));
static sat_projected_vertex_t bp[BN] __attribute__((section(".wram_l"),aligned(4)));
/* 8-octant skybox frustum culling: lets LibSaturn's instance_bounds_visible()
 * reject the 4-6 off-screen octants before projection and near/guard clipping. */
#define SKY_OCT_VCAP (BF*2u)
static sat_vec3_t sky_ov[SKY_OCT_VCAP] __attribute__((section(".wram_l"),aligned(4)));
static sat_vec3_t sky_ow[SKY_OCT_VCAP] __attribute__((section(".wram_l"),aligned(4)));
static sat_projected_vertex_t sky_op[SKY_OCT_VCAP] __attribute__((section(".wram_l"),aligned(4)));
static uint16_t sky_oi[BF*4] __attribute__((section(".wram_l"),aligned(4)));
static uint16_t sky_om[BF] __attribute__((section(".wram_l"),aligned(4)));
static sat_mesh_t sky_oct_meshes[8];
static sat_scene3d_instance_t sky_oct_instances[8];
static sat_aabb3_t sky_oct_bounds[8];
static uint16_t sky_oct_vfirst[8];
static uint8_t sky_oct_ready=0u;
#if !SM64DS_VISUAL_DIAGNOSTICS
static sat_scene3d_instance_binding_t sky_oct_bindings[8];
#endif
#endif
/* Resident castle bindings are initialized once. Keep them in stock Low
 * WRAM so corrected material wrapping and detailed actor bakes fit High RAM. */
static sat_vdp1_texture_t ct[CT] __attribute__((section(".wram_l"),aligned(4)));
static sat_scene3d_material_t cmat[CT*2] __attribute__((section(".wram_l"),aligned(4)));
static sat_projected_vertex_t cp[CN] __attribute__((section(".wram_l"),aligned(4)));
static sm64ds_background_t head;
static sat_vec3_t hv[HN],hw[HN];
/* Head mesh tables and textures are written once at setup, like ct/cmat. */
static uint16_t hi[HF*4] __attribute__((section(".wram_l"),aligned(4)));
static uint16_t hm[HF] __attribute__((section(".wram_l"),aligned(4)));
static sat_vdp1_texture_t ht[HT] __attribute__((section(".wram_l"),aligned(4)));
static sat_scene3d_material_t hmat[HT] __attribute__((section(".wram_l"),aligned(4)));
static sat_projected_vertex_t hp[HN];
/* Procedural 16x16 LUT4 circular drop shadow for grounding Mario. */
static const sat_vec3_t shadow_vertices[4]={{0,0,0},{ONE,0,0},{ONE,0,ONE},{0,0,ONE}};
static const uint16_t shadow_indices[4]={0,1,2,3};
static const uint16_t shadow_face_textures[1]={0};
static uint8_t shadow_pixels[128];
static const uint16_t shadow_luts[16]={0x0000u,0x8000u};
static const sat_model_texture_asset_t shadow_tex_assets[1]={{
    .pixels=shadow_pixels,.width=16,.height=16,.palette_slot=0,
    .flags=SAT_MODEL_TEXTURE_LUT4,.pixel_count=256
}};
static const sat_model_asset_t shadow_model={
    .vertices=shadow_vertices,.vertex_count=4,.indices=shadow_indices,.face_count=1,
    .face_texture_indices=shadow_face_textures,.textures=shadow_tex_assets,.texture_count=1,
    .palettes_rgb555=0,.palette_count=0,.palette_base=0,.luts_rgb555=shadow_luts,.lut_count=1
};
static sat_vdp1_texture_t shadow_texture;
static sat_scene3d_material_t shadow_material;
#ifdef CASTLE_PROPS_AVAILABLE
static sat_vdp1_texture_t tree_texture;
static sat_scene3d_material_t tree_material;
static sm64ds_background_t sign_prop;
static sat_vec3_t sv[SN],sw[SN];
static uint16_t si[SF*4],sm[SF];
static sat_vdp1_texture_t st[ST];
static sat_scene3d_material_t smat[ST];
static sat_projected_vertex_t sp[SN];
static sat_mat4_t sign_worlds[CASTLE_SIGN_COUNT];
#endif
#ifdef CASTLE_INTERIOR_PROPS_AVAILABLE
static sat_vdp1_texture_t painting_textures[CASTLE_PAINTING_TEXTURE_COUNT];
static sat_scene3d_material_t painting_materials[CASTLE_PAINTING_TEXTURE_COUNT];
static sm64ds_background_t door_prop;
static sat_vec3_t dv[DN],dw[DN];
static uint16_t di[DF*4],dm[DF];
static sat_vdp1_texture_t dt[DT];
static sat_scene3d_material_t dmat[DT];
static sat_projected_vertex_t dp[DN];
static sat_mat4_t door_worlds[CASTLE_DOOR_COUNT];
static sm64ds_background_t toad_prop;
static sat_vec3_t tv[TN],tw[TN];
static uint16_t ti[TF*4],tm[TF];
static sat_vdp1_texture_t tt[TT];
static sat_scene3d_material_t tmat[TT];
static sat_projected_vertex_t tp[TN];
static sat_mat4_t toad_worlds[CASTLE_TOAD_COUNT];
static uint16_t hud_paintings_drawn=0,hud_doors_drawn=0,hud_toads_drawn=0;
#endif
#if defined(CASTLE_WARP_AVAILABLE) && !SM64DS_VISUAL_DIAGNOSTICS
/* Must stay in High WRAM (not .wram_l) because sat_exec stages in Low WRAM. */
static sat_cd_block_t cd_block;
static sat_cd_device_t cd_device;
static sat_cdfs_volume_t cd_volume;
static uint8_t warp_fade=0;
static const sm64ds_warp_t *warp_target=0;
static sm64ds_loading_t warp_loading;
#endif
#if defined(CASTLE_INTRO_PROPS_AVAILABLE) && !SM64DS_VISUAL_DIAGNOSTICS
#define LN LAKITU_ACTOR_VERTEX_COUNT
#define LF LAKITU_ACTOR_FACE_COUNT
#define LJ LAKITU_ACTOR_JOINT_COUNT
#define LT LAKITU_ACTOR_TEXTURE_COUNT
#define PN WARP_PIPE_VERTEX_COUNT
#define PF WARP_PIPE_FACE_COUNT
#define PT WARP_PIPE_TEXTURE_COUNT
#define CASTLE_INTRO_DURATION_TICKS 295u
static uint8_t intro_cutscene_active=0u;
static uint8_t intro_cd_mounted=0u;
static uint8_t intro_music_open=0u;
static uint8_t intro_audio_ready=0u;
static uint8_t intro_sfx_flags=0u;
static uint32_t intro_ticks=0u;
static int32_t intro_lakitu_anim=0;
static int16_t intro_fade_cur=1000;
static sat_disc_stream_t intro_disc __attribute__((section(".wram_l"),aligned(4)));
static sat_cdfs_file_source_t intro_music_src __attribute__((section(".wram_l"),aligned(4)));
static sat_cdfs_source_desc_t intro_music_src_desc;
static sat_asset_desc_t intro_music_asset_desc;
static sat_asset_t intro_music_asset;
static sat_music_t intro_music;
static sat_sound_t intro_sfx_whoosh;
static sat_sound_t intro_sfx_pipe;
static uint8_t intro_music_ws[SAT_MUSIC_DISC_WORKSPACE_BYTES(16384u,1u)]
    __attribute__((section(".wram_l"),aligned(4)));
/* Lakitu & Green Warp Pipe render buffers (placed in .wram_l to save High WRAM) */
static sat_vec3_t lv[LN] __attribute__((section(".wram_l"),aligned(4)));
static sat_vec3_t lw[LN] __attribute__((section(".wram_l"),aligned(4)));
static sat_projected_vertex_t lp[LN] __attribute__((section(".wram_l"),aligned(4)));
static uint16_t li[LF*4u] __attribute__((section(".wram_l"),aligned(4)));
static uint16_t lm[LF] __attribute__((section(".wram_l"),aligned(4)));
static sat_vdp1_texture_t lt[LT] __attribute__((section(".wram_l"),aligned(4)));
static sat_scene3d_material_t lmat[LT+1u] __attribute__((section(".wram_l"),aligned(4)));
static sat_mesh_t lakitu_mesh;
static sat_skeleton_pose_joint_t lpose[LJ];
static sat_vec3_t lscales[LJ];
static sat_mat4_t lbones[LJ];
static sat_mat4_t lakitu_world;
static sat_aabb3_t lakitu_bounds;
static sat_scene3d_instance_t lakitu_inst;
static sat_vec3_t pv[PN] __attribute__((section(".wram_l"),aligned(4)));
static sat_vec3_t pw[PN] __attribute__((section(".wram_l"),aligned(4)));
static sat_projected_vertex_t pp[PN] __attribute__((section(".wram_l"),aligned(4)));
static uint16_t pi[PF*4u] __attribute__((section(".wram_l"),aligned(4)));
static uint16_t pm[PF] __attribute__((section(".wram_l"),aligned(4)));
static sat_vdp1_texture_t pt[PT] __attribute__((section(".wram_l"),aligned(4)));
static sat_scene3d_material_t pmat[PT] __attribute__((section(".wram_l"),aligned(4)));
static sm64ds_background_t pipe_prop;
#endif
static int spawn_yaw_default;
static int spawn_facing_default;
static sm64ds_player_t player;
static uint8_t g_stars;       /* stars collected this visit */
static uint32_t g_star_bits;  /* bit per course star collected (save bit) */
static uint8_t g_boss_defeated; /* boss hp hit 0 (star unlocked) */
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
/* Last good camera yaw (the yaw that produced previous_camera_eye). When the
 * requested yaw is blocked we keep the camera where it was, and when it
 * clears again we resume from the requested yaw rather than snapping to an
 * arbitrary angle. */
static int camera_last_good_yaw=-1;
/* Debug HUD telemetry state: Y cycles 0=full, 1=compact, 2=off. */
static uint8_t hud_mode=0;
static uint8_t hud_floor_ok=0;
static int16_t hud_floor_ny_pct=100;
static int16_t hud_floor_height=0;
static uint16_t hud_trees_drawn=0,hud_signs_drawn=0,hud_support_pushed=0;

#include "castle_diag.inc"

/* Stable debugger telemetry: all values are captured from real frames. */
volatile struct {
    uint32_t magic,frames,ticks,jumps,landings,wall_hits,resets;
    int32_t x,y,z,velocity_y,camera_x,camera_y,camera_z;
    int32_t target_x,target_y,target_z;
    uint32_t grounded,clip,commands,skipped,faces,paused;
    uint32_t culled,clipped,fallback;
    uint32_t sky_clip_candidates,castle_clip_candidates,body_clip_candidates,head_clip_candidates;
    uint32_t texture_arena_initial,texture_arena_remaining,texture_estimate;
    uint32_t health,max_health,dead,coins,star_bits;
    uint32_t boss_hp,boss_state,boss_held;
    int32_t boss_x,boss_y,boss_z;
    int32_t requested_yaw,actual_camera_yaw,camera_clearance;
    int32_t mario_facing,camera_fov_y;
    uint32_t climbing,climb_count,water_plane_faces;
} g_sm64ds_castle_stats={.magic=0x43415331};

/* Per-stage main-loop cost in FRT ticks (sat_time_frequency_hz per second),
 * summed over every draw. end_frame includes the wait for the VDP1 to finish
 * the previous list, so it separates VDP1-bound from CPU-bound frames. */
enum {
    PROF_VBLANK,PROF_SIM,PROF_SKIN,PROF_CAMERA,PROF_BEGIN,PROF_SKY,PROF_CASTLE,
    PROF_PROPS,PROF_ACTOR,PROF_SUPPORT,PROF_FLUSH,PROF_HUD,PROF_END,PROF_COUNT
};
volatile struct {
    uint32_t magic,frequency_hz,frames,sim_steps,max_sim_steps;
    uint32_t vdp1_draw_waits,vdp1_draw_timeouts,vdp1_late_swaps;
    uint32_t sum[PROF_COUNT],max[PROF_COUNT];
} g_sm64ds_castle_profile={.magic=0x50524f46};
static uint64_t profile_mark;
static void profile_lap(unsigned stage) {
    uint64_t now=sat_time_ticks();
    uint64_t delta=now>=profile_mark?now-profile_mark:0u;
    uint32_t ticks=delta>UINT32_MAX?UINT32_MAX:(uint32_t)delta;
    profile_mark=now;
    g_sm64ds_castle_profile.sum[stage]+=ticks;
    if(ticks>g_sm64ds_castle_profile.max[stage]) g_sm64ds_castle_profile.max[stage]=ticks;
}

static void skin(void) {
    const sat_skeleton_clip_t *c=&mario_preview_clips[clip];
    SAT_PANIC_IF_ERROR(sat_clip_sample(c,anim_time,pose,J));
    SAT_PANIC_IF_ERROR(sm64ds_clip_sample_scale(&mario_preview_scale_clips[clip],c,anim_time,scales,J));
    SAT_PANIC_IF_ERROR(sm64ds_pose_world_matrices(&mario_preview_skeleton,pose,scales,bones,J));
    SAT_PANIC_IF_ERROR(sat_skin_update_mesh(&mario_preview_skin,bones,J,&mesh,0,&bounds));
}
static void reset_view(void) {
    yaw=spawn_yaw_default;camera_yaw=spawn_yaw_default;camera_choice=0;
    facing=spawn_facing_default;anim_time=0;
    camera_last_good_yaw=yaw;
#ifdef CASTLE_ROOM_CULLING
    current_room=0;visible_room_mask=1u;
#endif
}
static void reset(void) {
    sm64ds_player_reset(&player);
    reset_view();
}
static sat_vec3_t camera_candidate(int angle,int32_t distance) {
    int32_t s=sat_sin_deg(angle*ONE),c=sat_cos_deg(angle*ONE);
    return (sat_vec3_t){camera.target.x+sat_fx16_mul(s,distance),
        camera.target.y+distance*30/65,camera.target.z+sat_fx16_mul(c,distance)};
}
static void update_camera_alive(void);
static void update_camera(void) {
    if (!player.dead) {
        update_camera_alive();
        return;
    }
    /* Death cam: hold the last good view. */
    g_sm64ds_castle_stats.requested_yaw=yaw;
    g_sm64ds_castle_stats.actual_camera_yaw=camera_yaw;
    g_sm64ds_castle_stats.camera_clearance=previous_camera_clearance;
    SAT_PANIC_IF_ERROR(sat_camera3d_update(&camera));
}

static void update_camera_alive(void) {
#if SM64DS_VISUAL_DIAGNOSTICS && SM64DS_DIAG_ABSOLUTE_CAMERA
    camera.eye=(sat_vec3_t){SM64DS_DIAG_CAMERA_X*ONE,SM64DS_DIAG_CAMERA_Y*ONE,SM64DS_DIAG_CAMERA_Z*ONE};
    camera.target=(sat_vec3_t){SM64DS_DIAG_TARGET_X*ONE,SM64DS_DIAG_TARGET_Y*ONE,SM64DS_DIAG_TARGET_Z*ONE};
    camera_yaw=((SM64DS_DIAG_YAW%360)+360)%360;
    g_sm64ds_castle_stats.requested_yaw=camera_yaw;
    g_sm64ds_castle_stats.actual_camera_yaw=camera_yaw;
    g_sm64ds_castle_stats.camera_clearance=-ONE;
    SAT_PANIC_IF_ERROR(sat_camera3d_update(&camera));
    return;
#endif
    camera.target=(sat_vec3_t){player.feet.x,player.feet.y+8*ONE,player.feet.z};
#if SM64DS_VISUAL_DIAGNOSTICS && SM64DS_DIAG_FIXED_CAMERA
    int32_t distance=SM64DS_DIAG_CAMERA_DISTANCE*ONE;
#else
    int32_t distance=(close_camera?castle_stage.close_cam_dist:castle_stage.default_cam_dist)*ONE;
#endif
    /* A swimmer sees the water volume from a wider berth: a wall a few units
     * behind the camera would fill the view, so ask for more room first. */
    const int32_t keep=player.swimming?40*ONE:20*ONE,restore=player.swimming?50*ONE:25*ONE;
    sat_vec3_t candidates[8];int32_t fractions[8]={0},clearance[8]={0};
    candidates[0]=camera_candidate(yaw,distance);
    fractions[0]=sm64ds_camera_fraction(&castle_collision,&camera.target,&candidates[0]);
    clearance[0]=sat_fx16_mul(distance,fractions[0]);
    if (clearance[0]>=restore) camera_choice=0;
    else {
        if (camera_choice>0 && camera_choice<8) {
            int angle=(yaw+camera_offsets[camera_choice]+360)%360;
            candidates[camera_choice]=camera_candidate(angle,distance);
            fractions[camera_choice]=sm64ds_camera_fraction(&castle_collision,&camera.target,&candidates[camera_choice]);
            clearance[camera_choice]=sat_fx16_mul(distance,fractions[camera_choice]);
        }
        if (!camera_choice || clearance[camera_choice]<keep) {
            for (uint8_t i=1;i<8;++i) {
                if (i==camera_choice) continue;
                int angle=(yaw+camera_offsets[i]+360)%360;
                candidates[i]=camera_candidate(angle,distance);
                fractions[i]=sm64ds_camera_fraction(&castle_collision,&camera.target,&candidates[i]);
                clearance[i]=sat_fx16_mul(distance,fractions[i]);
            }
            camera_choice=sm64ds_camera_select(clearance,8,camera_choice,keep,restore);
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
        camera_last_good_yaw=yaw;
    } else if (camera_choice==0 && clearance[0]<camera_safe_min) {
        /* Only hold the last good view when the *forward* candidate is
         * blocked. A side/back choice that is merely tight should still be
         * used (this is what lets the camera swing around the castle wall). */
        camera.eye=previous_camera_eye;
        g_sm64ds_castle_stats.camera_clearance=previous_camera_clearance;
        yaw=camera_last_good_yaw>=0?camera_last_good_yaw:yaw;
        camera_yaw=(yaw+camera_offsets[camera_choice]+360)%360;
        SAT_PANIC_IF_ERROR(sat_camera3d_update(&camera));
        return;
    } else {
        camera.eye=(sat_vec3_t){camera.target.x+sat_fx16_mul(desired.x-camera.target.x,t),
            camera.target.y+sat_fx16_mul(desired.y-camera.target.y,t),
            camera.target.z+sat_fx16_mul(desired.z-camera.target.z,t)};
        previous_camera_eye=camera.eye;
        previous_camera_clearance=clearance[camera_choice];
        camera_last_good_yaw=yaw;
    }
    g_sm64ds_castle_stats.requested_yaw=yaw;
    g_sm64ds_castle_stats.actual_camera_yaw=camera_yaw;
    g_sm64ds_castle_stats.camera_clearance=clearance[camera_choice];
    SAT_PANIC_IF_ERROR(sat_camera3d_update(&camera));
}
#ifdef CASTLE_WATER_LAYERS
/* A camera under the water surface fades a VDP2 colour offset toward a blue
 * tint over a few frames and back out. The surface comes from the collision's
 * water floors, so a dry cave below the water level is not tinted. Bank B and
 * the sprite/back layers are used so the intro's bank-A fade is untouched. */
#define WATER_TINT_FRAMES 8
static uint8_t water_tint_fade=0;
static void update_water_tint(void) {
    static const sat_vdp2_color_offset_t tint={-90,-40,-5};
    int32_t surface;
    const uint8_t under=sm64ds_water_surface(&castle_collision,camera.eye.x,camera.eye.z,
                                             camera.eye.y,&surface)!=0;
    const uint8_t before=water_tint_fade;
    if (under && water_tint_fade<WATER_TINT_FRAMES) ++water_tint_fade;
    else if (!under && water_tint_fade>0) --water_tint_fade;
    if (water_tint_fade) {
        const sat_vdp2_color_offset_t off={(int16_t)(tint.r*water_tint_fade/WATER_TINT_FRAMES),
            (int16_t)(tint.g*water_tint_fade/WATER_TINT_FRAMES),
            (int16_t)(tint.b*water_tint_fade/WATER_TINT_FRAMES)};
        (void)sat_vdp2_color_offset_set(SAT_VDP2_COLOR_OFFSET_B,&off);
        (void)sat_vdp2_color_offset_enable(SAT_VDP2_LAYER_SPRITE|SAT_VDP2_LAYER_BACK,
                                           SAT_VDP2_COLOR_OFFSET_B);
    } else if (before) {
        (void)sat_vdp2_color_offset_disable(SAT_VDP2_LAYER_SPRITE|SAT_VDP2_LAYER_BACK);
    }
    if (water_tint_fade||before) (void)sat_vdp2_layers_commit();
}

#ifdef CASTLE_WATER_PLANE
/* Build and submit the camera-centred water plane. Call after the terrain
 * chunks, before the actors, at the water pass. */
/* The moat and pond span the whole grounds (about 960 x 832 units), so the
 * rings must reach far enough that the water is visible from the lawn: a
 * 16-unit cell with four rings covers +-512 units around the camera. */
enum { WATER_PLANE_CELLS=8, WATER_PLANE_RINGS=4 };
/* Textured water grid: the original MC_WATER texture is a 32x32 repeat tile
 * scrolled diagonally by its BTA. Saturn's scene3d quad path maps a whole
 * texture per quad, so the scroll is baked into a ring of phase textures and
 * the grid walks the ring one entry per frame. */
#ifndef CASTLE_WATER_TEXTURE_AVAILABLE
#define CASTLE_WATER_TEXTURE_AVAILABLE 0
#endif
#if CASTLE_WATER_TEXTURE_AVAILABLE
static sat_scene3d_material_t water_material;
static sat_vdp1_texture_t water_tex_uploaded[CASTLE_WATER_TEX_PHASES];
static uint16_t water_lut_uploaded[16];
static void water_texture_init(void) {
    /* Upload one LUT and every phase's LUT4 pixels. The castle water LUT has
     * the VDP1 RGB bit set per entry by index_bakes_lut4. */
    SAT_PANIC_IF_ERROR(sat_vdp1_upload_lut(castle_water_lut, &water_lut_uploaded[0]));
    for (uint32_t p = 0; p < CASTLE_WATER_TEX_PHASES; ++p) {
        sat_vdp1_texture_t tex;
        SAT_PANIC_IF_ERROR(sat_tex_upload_lut4_pixels(&tex, castle_water_pixels[p],
            CASTLE_WATER_TEX_WIDTH, CASTLE_WATER_TEX_HEIGHT, water_lut_uploaded[0]));
        water_tex_uploaded[p] = tex;
    }
    water_material = (sat_scene3d_material_t){
        .kind = SAT_SCENE3D_INDEXED_TEXTURED,
        .rgb555 = SAT_RGB555(5,16,26),
        .texture = &water_tex_uploaded[0],
        .color_calc_slot = SAT_INDEXED_SOLID_OPAQUE,
        .sprite_flags = 0,
    };
}
/* The BTA scrolls transS 0..4096 over 91 frames (one full tile); the ring has
 * CASTLE_WATER_TEX_PHASES phases per tile, so advance that many phases per
 * frame's 46/4096-of-a-tile step. */
static void water_texture_pick(uint32_t ticks) {
    const uint32_t phase = ((ticks * CASTLE_WATER_TEX_STEP_S) >> 8) % CASTLE_WATER_TEX_PHASES;
    water_material.texture = &water_tex_uploaded[phase];
}
#else
static sat_scene3d_material_t water_material;
static void water_texture_init(void) {
    water_material = (sat_scene3d_material_t){
        .kind=SAT_SCENE3D_RGB,.rgb555=SAT_RGB555(5,16,26),
        .color_calc_slot=SAT_INDEXED_SOLID_OPAQUE,.sprite_flags=SAT_SPRITE_FLAG_MESH};
}
static void water_texture_pick(uint32_t ticks) { (void)ticks; }
#endif
/* Draw the water as lib-saturn's camera-centred water plane (rings of quads,
 * fine near the camera and coarser outward), with the original MC_WATER tile
 * cycled through its 16-phase ring for the BTA diagonal scroll. */
static void draw_water_texture(uint16_t pass) {
    static sat_water_plane_t water_plane __attribute__((section(".wram_l")));
    sat_vec3_t fwd={0,0,0};
    const sat_vec3_t delta={camera.target.x-camera.eye.x,0,camera.target.z-camera.eye.z};
    sat_vec3_normalize(&fwd,&delta);
    const int32_t eye_h=camera.eye.y-CASTLE_WATER_Y;
    const sat_water_plane_config_t cfg={
        .min_x=CASTLE_WATER_REGION_X0,.max_x=CASTLE_WATER_REGION_X1,
        .min_z=CASTLE_WATER_REGION_Z0,.max_z=CASTLE_WATER_REGION_Z1,
        .surface=CASTLE_WATER_Y,.cell=16*ONE,.cells=WATER_PLANE_CELLS,.rings=WATER_PLANE_RINGS,
        .underside=(uint8_t)(camera.eye.y<CASTLE_WATER_Y),
        .wobble=0,.period=12*ONE,.speed=6,.tick=player.ticks,
        .near_color=sat_gouraud_rgb(-11,0,10),.far_color=sat_gouraud_rgb(-8,4,12),
        .glint=3,.forward_x=fwd.x,.forward_z=fwd.z,
        .behind=(eye_h<0?-eye_h:eye_h)+4*ONE};
    SAT_PANIC_IF_ERROR(sat_water_plane_build(&water_plane,&cfg,camera.eye.x,camera.eye.z));
    water_texture_pick(player.ticks);
    const sat_scene3d_material_t rings[WATER_PLANE_RINGS]={water_material,water_material,
                                                          water_material,water_material};
    const uint16_t before=scene.faces.count;
    SAT_PANIC_IF_ERROR(sat_water_plane_submit(&scene,&water_plane,rings,pass));
    g_sm64ds_castle_stats.water_plane_faces=(uint16_t)(scene.faces.count-before);
}
#endif /* CASTLE_WATER_PLANE */
#endif
#ifdef CASTLE_PASS_DOOR_COUNT
/* Internal room doors. The doorway is a closed wall in the KCL; the DS door
 * actor carries Mario through it. Pressing into the wall beside a door moves
 * him to the far side, facing along the door's axis. */
static void door_pass(uint32_t wall_hits_before) {
    if(player.swimming||player.dead||player.climbing||!player.grounded||
       player.wall_hits==wall_hits_before) return;
    for(uint32_t i=0;i<CASTLE_PASS_DOOR_COUNT;++i) {
        const sat_vec3_t d=castle_pass_door_positions[i];
        const int deg=castle_pass_door_yaw_deg[i];
        const int32_t s=sat_sin_deg(deg*ONE),c=sat_cos_deg(deg*ONE);
        const int32_t rx=player.feet.x-d.x,rz=player.feet.z-d.z;
        const int32_t a=sat_fx16_mul(rx,s)+sat_fx16_mul(rz,c);
        const int32_t t=sat_fx16_mul(rx,c)-sat_fx16_mul(rz,s);
        const int32_t dy=player.feet.y-d.y;
        if(a>=9*ONE||a<=-9*ONE||t>=12*ONE||t<=-12*ONE||dy>=16*ONE||dy<=-16*ONE) continue;
        const int32_t out=a<0?13*ONE:-13*ONE;
        /* Walk out through the middle of the leaf (the hinge sits at the
         * doorway's edge), else where he pressed in. */
        const int32_t lateral[3]={(ONE*48)/10,-(ONE*48)/10,t};
        for(int k=0;k<3;++k) {
            const int32_t nx=d.x+sat_fx16_mul(out,s)+sat_fx16_mul(lateral[k],c);
            const int32_t nz=d.z+sat_fx16_mul(out,c)-sat_fx16_mul(lateral[k],s);
            int32_t fy=0;
            if(!sm64ds_floor(&castle_collision,nx,nz,player.feet.y+8*ONE,&fy)) continue;
            if(fy>player.feet.y+8*ONE||fy<player.feet.y-8*ONE) continue;
            player.feet=(sat_vec3_t){nx,fy,nz};
            player.velocity_y=0;player.grounded=1;
            facing=(deg+(a<0?0:180))%360;
            return;
        }
    }
}
#endif
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
    if(player.swimming) {
        /* St_Swim: the d-pad turns and pitches (back rises), A strokes. */
        player.swim_turn=(int8_t)x;player.swim_pitch=(int8_t)z;
        player.swim_stroke_held=(pad->held&SAT_PAD_A)!=0;
        dx=dz=0;
    } else if(x||z) {
        int heading=z<0?(x<0?225:x>0?135:180):z>0?(x<0?315:x>0?45:0):(x<0?270:90);
        facing=(heading+camera_yaw)%360;
    }
    if(!player.swimming) player.yaw=(uint16_t)((uint32_t)facing*65536u/360u);
#ifdef CASTLE_PASS_DOOR_COUNT
    const uint32_t wall_hits_before=player.wall_hits;
#endif
    sm64ds_player_step(&player,&castle_collision,dx,dz,jump,(pad->held&SAT_PAD_B)!=0);
#ifdef CASTLE_PASS_DOOR_COUNT
    door_pass(wall_hits_before);
#endif
    if(player.swimming) {
        facing=(int)((((uint32_t)player.yaw*360u)+32768u)>>16)%360;
        /* The camera eases round behind the swimmer unless L/R steer it. */
        if(!(pad->held&(SAT_PAD_L|SAT_PAD_R))) {
            int behind=(facing+180-camera_offsets[camera_choice]+720)%360;
            int turn=(behind-yaw+540)%360-180;
            yaw=(yaw+(turn>2?2:turn<-2?-2:turn)+360)%360;
        }
    }
    player.held_yaw=(uint8_t)((facing+camera_yaw)%360);
#ifdef CASTLE_ACTOR_KINDS_AVAILABLE
    sm64ds_actor_hit_t hit={0,0,0,0,0,0,0,0,0};
    const uint8_t grab = (pad->pressed & SAT_PAD_A) && !jump;
    const uint8_t throw = (pad->pressed & SAT_PAD_X) && jump;
    for (uint32_t k=0;k<CASTLE_ACTOR_KIND_COUNT;++k) {
        sm64ds_actor_kind_update(castle_actor_kinds[k],&castle_collision,&player,&hit);
        (void)sm64ds_actor_grab(castle_actor_kinds[k],&player,grab,throw,&hit);
    }
    g_stars+=hit.stars;
    if (hit.star_index) g_star_bits|=hit.star_bit;
    if (hit.boss_defeated) g_boss_defeated=1;
    if (hit.coins) sm64ds_player_add_coins(&player,hit.coins);
    if (hit.bounce) {player.velocity_y=4*ONE;player.grounded=0;}
    if (hit.count) {   /* damage once per invulnerability window, with knockback */
        sm64ds_player_hurt(&player,hit.damage?hit.damage:1,
                           sat_fx16_mul(hit.push_x,2*ONE),
                           sat_fx16_mul(hit.push_z,2*ONE));
    }
#endif
    uint16_t next=!player.grounded?3:player.moving?(player.running?2:1):0;
#if MARIO_PREVIEW_CLIP_COUNT >= 6
    if(player.swimming) next=(player.swim_phase==2||player.swim_phase==3)?4:5;
#endif
    if(next!=clip) {clip=next;anim_time=0;}
    anim_time+=ONE/60;
}

static void init_shadow_texture(void) {
    for (int y=0;y<16;++y) {
        int dy=2*y-15;
        for (int x=0;x<16;x+=2) {
            int dx0=2*x-15,dx1=2*(x+1)-15;
            uint8_t hi=(dx0*dx0+dy*dy<=196)?1u:0u;
            uint8_t lo=(dx1*dx1+dy*dy<=196)?1u:0u;
            shadow_pixels[y*8+(x>>1)]=(uint8_t)((hi<<4)|lo);
        }
    }
}

/* Frame-time experiments, off by default: skip the sky, or skip castle
 * chunks whose XZ bounds lie farther than SM64DS_EXP_FAR_CULL world units
 * from the camera. */
#ifndef SM64DS_EXP_NO_SKY
#define SM64DS_EXP_NO_SKY 0
#endif
#ifndef SM64DS_EXP_FAR_CULL
#define SM64DS_EXP_FAR_CULL 0
#endif
#ifdef CASTLE_CHUNK_CULLING
static int exp_chunk_far(uint8_t c) {
    const int32_t far_cull=SM64DS_EXP_FAR_CULL?SM64DS_EXP_FAR_CULL:castle_stage.far_cull;
    if (!far_cull) return 0;
    const sat_aabb3_t *b=&castle_chunk_bounds[c];
    int32_t dx=(camera.eye.x>b->center.x?camera.eye.x-b->center.x:b->center.x-camera.eye.x)-b->half.x;
    int32_t dz=(camera.eye.z>b->center.z?camera.eye.z-b->center.z:b->center.z-camera.eye.z)-b->half.z;
    if (dx<0) dx=0;
    if (dz<0) dz=0;
    dx>>=16; dz>>=16;
    return dx*dx+dz*dz>far_cull*far_cull;
}
#endif
#include "castle_slave_chunks.inc"

#include "castle_sky.inc"

static void submit_mario_shadow(void) {
    int32_t floor_y=0;
    sat_vec3_t normal={0,ONE,0};
    if (!sm64ds_floor_normal(&castle_collision,player.feet.x,player.feet.z,
                             player.feet.y+4*ONE,&floor_y,&normal)) {
        hud_floor_ok=0;hud_floor_ny_pct=0;hud_floor_height=0;
        return;
    }
    int32_t height=player.feet.y-floor_y;
    if (height<0) height=0;
    hud_floor_ok=1;
    hud_floor_ny_pct=(int16_t)(((int64_t)normal.y*100+ONE/2)/ONE);
    hud_floor_height=(int16_t)(height/ONE);
    if (height>48*ONE) return;
    int32_t r=(ONE*13)/4-(height/20);
    if (r<(ONE*7)/4) r=(ONE*7)/4;
    sat_vec3_t u_raw={-normal.y,normal.x,0},u,v;
    sat_vec3_normalize(&u,&u_raw);
    sat_vec3_cross(&v,&normal,&u);
    sat_vec3_scale(&u,&u,r);
    sat_vec3_scale(&v,&v,r);
    sat_vec3_t c={player.feet.x+(normal.x*3)/8,floor_y+(normal.y*3)/8,player.feet.z+(normal.z*3)/8};
    sat_quad3_t quad={.v={
        {c.x-u.x-v.x,c.y-u.y-v.y,c.z-u.z-v.z},
        {c.x+u.x-v.x,c.y+u.y-v.y,c.z+u.z-v.z},
        {c.x+u.x+v.x,c.y+u.y+v.y,c.z+u.z+v.z},
        {c.x-u.x+v.x,c.y-u.y+v.y,c.z-u.z+v.z}
    }};
    SAT_PANIC_IF_ERROR(sat_scene_submit_quad(&scene,&quad,&shadow_material,SM64DS_ACTOR_PASS));
}

#include "castle_props.inc"

#include "castle_rooms.inc"

#include "castle_interior.inc"

#include "castle_support_order.inc"

#include "castle_hud.inc"

#include "castle_intro.inc"

#if defined(CASTLE_WARP_AVAILABLE) && !SM64DS_VISUAL_DIAGNOSTICS
static void draw_warp_fade(uint8_t step) {
    if (step==0u) return;
    if (step<3u) {
        /* Fade to black: a half-transparent black quad over the scene. */
        sat_polygon_cmd_t cmd={
            .x={-160,160,160,-160},
            .y={-112,-112,112,112},
            .color=SAT_RGB555(0,0,0),
            .flags=SAT_SPRITE_FLAG_HALF_TRANSPARENT
        };
        SAT_PANIC_IF_ERROR(sat_vdp1_draw_polygon(&cmd));
        return;
    }
    /* Loading screen: lib-saturn sat_loading_screen_t bar fills over
     * steps 3..22, then execute_stage_warp reads the next stage over the
     * frozen last frame. Draws into the frame already begun by the main
     * loop, so it must NOT call sat_begin_frame/sat_end_frame itself. */
    if (!warp_loading.ready) sm64ds_loading_init(&warp_loading);
    uint16_t pct=(uint16_t)(((uint32_t)(step-3u)*100u)/19u);
    if (pct>100u) pct=100u;
    sm64ds_loading_frame(&warp_loading, "NOW LOADING",
                         warp_target?warp_target->bin:"", pct);
}

static void execute_stage_warp(const sm64ds_warp_t *target) {
    sm64ds_warp_arg_t out_arg={
        .magic=SM64DS_WARP_MAGIC,
        .entrance=target->entrance,
        .hud_mode=hud_mode,
        .close_camera=(uint8_t)close_camera,
        .stars=g_stars,
        .star_bits=(uint8_t)(g_star_bits&0xFFu),
        .reserved=0u
    };
    sat_result_t r=sat_cd_mount_default(&cd_block,0,0,&cd_device,0u,&cd_volume);
    if (r==SAT_OK) {
#if SM64DS_VDP2_SKY
        sky_shutdown();
#endif
#ifdef CASTLE_SLAVE_CHUNKS
        slave_chunks_stop();
#endif
        (void)sat_exec(&cd_volume,target->bin,&out_arg,sizeof(out_arg));
#if SM64DS_VDP2_SKY
        sky_init();
#endif
#ifdef CASTLE_SLAVE_CHUNKS
        slave_chunks_init();
#endif
    }
    /* If the target binary is absent (e.g. standalone single-stage test disc),
     * cancel the fade gracefully so gameplay continues uninterrupted. */
    warp_fade=0u;
}
#endif

int main(void) {
    const sat_video_config_t video={320,224,SAT_VIDEO_AUTO,0};
    SAT_PANIC_IF_ERROR(sat_init(&video));
    /* This scene takes several fields to draw. Keep the completed picture
     * visible until VDP1 reaches END instead of swapping a partial list. */
    SAT_PANIC_IF_ERROR(sat_vdp1_set_frame_mode(SAT_VDP1_FRAME_ON_SUBMIT));
#if defined(CASTLE_WARP_AVAILABLE) && !SM64DS_VISUAL_DIAGNOSTICS
    sm64ds_warp_arg_t in_arg={0};
    uint32_t in_arg_len=0;
    int in_arg_valid=(sat_exec_arg(&in_arg,sizeof(in_arg),&in_arg_len)==SAT_OK &&
                      in_arg_len==sizeof(in_arg) && in_arg.magic==SM64DS_WARP_MAGIC);
#if defined(CASTLE_INTRO_PROPS_AVAILABLE)
    if (in_arg_valid && in_arg.entrance==SM64DS_ENTRANCE_INTRO) {
        intro_cutscene_active=1u;
        SAT_PANIC_IF_ERROR(sat_vdp2_color_offset_enable(SAT_VDP2_LAYER_ALL,SAT_VDP2_COLOR_OFFSET_A));
        intro_set_fade(255);
        (void)sat_vdp2_layers_commit();
    }
#endif
#endif
    uint32_t bytes=sat_model_vram_estimate_bytes(&mario_preview_model)+
        sat_model_vram_estimate_bytes(&castle_model)+
        sat_model_vram_estimate_bytes(&mario_head_model)+
        sat_model_vram_estimate_bytes(&shadow_model);
#if CASTLE_HAS_SKYBOX
    bytes+=sat_model_vram_estimate_bytes(&skybox_preview_model);
#endif
#ifdef CASTLE_PROPS_AVAILABLE
    bytes+=sat_model_vram_estimate_bytes(&castle_tree_model)+
        sat_model_vram_estimate_bytes(&castle_sign_model);
#endif
#if defined(CASTLE_INTRO_PROPS_AVAILABLE) && !SM64DS_VISUAL_DIAGNOSTICS
    if (intro_cutscene_active) {
        bytes+=sat_model_vram_estimate_bytes(&lakitu_actor_model)+
            sat_model_vram_estimate_bytes(&warp_pipe_model);
    }
#endif
#ifdef CASTLE_INTERIOR_PROPS_AVAILABLE
    bytes+=sat_model_vram_estimate_bytes(&castle_painting_model)+
        sat_model_vram_estimate_bytes(&castle_door_model)+
        sat_model_vram_estimate_bytes(&castle_toad_model);
#endif
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
    const sm64ds_background_buffers_t hb={hv,hi,ht,hmat,hm,HN,HF,HT};
    SAT_PANIC_IF_ERROR(sm64ds_background_init(&castle,&castle_model,&cb));
    /* VDP1 indexed sprites cannot blend against another VDP1 sprite. Its
     * mesh mode provides bounded 50% coverage for DS partial-alpha faces. */
    for (uint16_t i=0;i<CT;++i) {
        cmat[CT+i]=cmat[i];
        cmat[CT+i].sprite_flags=SAT_SPRITE_FLAG_MESH;
        /* Translucent black shadow decals sit over solid terrain; drop
         * near-clipped pieces rather than drawing a solid black polygon. */
        if (cmat[CT+i].rgb555==0x8000u) cmat[CT+i].rgb555=0;
    }
    for (uint16_t i=0;i<CF;++i)
        if (castle_polygon_alpha[i]<31u) cm[i]=(uint16_t)(cm[i]+CT);
    castle.instance.material_count=CT*2;
#if CASTLE_HAS_SKYBOX
    const sm64ds_background_buffers_t bb={bv,bi,bt,bmat,bm,BN,BF,BT};
    SAT_PANIC_IF_ERROR(sm64ds_background_init(&sky,&skybox_preview_model,&bb));
    {
        uint16_t fcursor=0,vcursor=0;
        int ok=1;
        for (uint8_t o=0;o<8u && ok;++o) {
            uint16_t f0=fcursor,v0=vcursor;
            sky_oct_vfirst[o]=v0;
            uint16_t vmap[BN];
            for (uint16_t v=0;v<BN;++v) vmap[v]=0xffffu;
            int32_t minx=INT32_MAX,miny=INT32_MAX,minz=INT32_MAX;
            int32_t maxx=INT32_MIN,maxy=INT32_MIN,maxz=INT32_MIN;
            for (uint16_t f=0;f<BF;++f) {
                const uint16_t *fi=&bi[(uint32_t)f*4u];
                int32_t cx=(bv[fi[0]].x/4)+(bv[fi[1]].x/4)+(bv[fi[2]].x/4)+(bv[fi[3]].x/4);
                int32_t cy=(bv[fi[0]].y/4)+(bv[fi[1]].y/4)+(bv[fi[2]].y/4)+(bv[fi[3]].y/4);
                int32_t cz=(bv[fi[0]].z/4)+(bv[fi[1]].z/4)+(bv[fi[2]].z/4)+(bv[fi[3]].z/4);
                uint8_t fo=(uint8_t)(((cx>=0)?1u:0u)|((cy>=0)?2u:0u)|((cz>=0)?4u:0u));
                if (fo!=o) continue;
                for (uint8_t k=0;k<4u;++k) {
                    uint16_t sv=fi[k];
                    if (vmap[sv]==0xffffu) {
                        if (vcursor>=SKY_OCT_VCAP) { ok=0;break; }
                        vmap[sv]=(uint16_t)(vcursor-v0);
                        sat_vec3_t pt=bv[sv];
                        sky_ov[vcursor++]=pt;
                        if (pt.x<minx) minx=pt.x;
                        if (pt.x>maxx) maxx=pt.x;
                        if (pt.y<miny) miny=pt.y;
                        if (pt.y>maxy) maxy=pt.y;
                        if (pt.z<minz) minz=pt.z;
                        if (pt.z>maxz) maxz=pt.z;
                    }
                    sky_oi[(uint32_t)fcursor*4u+k]=vmap[sv];
                }
                if (!ok) break;
                sky_om[fcursor++]=bm[f];
            }
            uint16_t fc=(uint16_t)(fcursor-f0),vc=(uint16_t)(vcursor-v0);
            if (!ok || fc==0u || vc==0u) { sky_oct_meshes[o].face_count=0;continue; }
            SAT_PANIC_IF_ERROR(sat_mesh_init(&sky_oct_meshes[o],&sky_ov[v0],vc,&sky_oi[(uint32_t)f0*4u],fc));
            sky_oct_meshes[o].vertex_count=vc;
            sky_oct_meshes[o].face_count=fc;
            sky_oct_bounds[o]=(sat_aabb3_t){
                .center={(minx+maxx)/2,(miny+maxy)/2,(minz+maxz)/2},
                .half={(maxx-minx)/2+1,(maxy-miny)/2+1,(maxz-minz)/2+1}
            };
            sky_oct_instances[o]=(sat_scene3d_instance_t){
                .mesh=&sky_oct_meshes[o],.materials=bmat,.material_count=BT,
                .face_materials=&sky_om[f0],.world=&sky.world,.bounds=&sky_oct_bounds[o],
                .pass=SM64DS_BACKGROUND_PASS,.cull_backfaces=0
            };
        }
        sky_oct_ready=ok?1u:0u;
    }
#endif
    SAT_PANIC_IF_ERROR(sm64ds_background_init(&head,&mario_head_model,&hb));
    head.instance.pass=SM64DS_ACTOR_PASS;head.instance.cull_backfaces=SAT_SCENE3D_CULL_SCREEN;
    castle.instance.pass=SM64DS_ACTOR_PASS;
    castle.instance.world=0;
    castle.instance.cull_backfaces=SAT_SCENE3D_CULL_SCREEN;
    castle.instance.double_sided_faces=castle_double_sided;
#ifdef CASTLE_ROOM_CULLING
    for (uint8_t r=0;r<CASTLE_ROOM_COUNT;++r) {
        uint16_t f0=castle_room_first[r],fc=castle_room_count[r];
        uint16_t v0=castle_room_vfirst[r],vc=castle_room_vcount[r];
        for (uint32_t k=(uint32_t)f0*4u;k<(uint32_t)(f0+fc)*4u;++k)
            ci[k]=(uint16_t)(ci[k]-v0);
        SAT_PANIC_IF_ERROR(sat_mesh_init(&room_meshes[r],&cv[v0],vc,&ci[(uint32_t)f0*4u],fc));
        room_meshes[r].vertex_count=vc;
        room_meshes[r].face_count=fc;
        room_instances[r]=(sat_scene3d_instance_t){
            .mesh=&room_meshes[r],.materials=cmat,.material_count=CT*2,
            .face_materials=&cm[f0],.world=0,.bounds=&castle_room_bounds[r],
            .pass=SM64DS_ACTOR_PASS,.cull_backfaces=SAT_SCENE3D_CULL_SCREEN,
            .double_sided_faces=&castle_double_sided[f0]
        };
    }
#elif defined(CASTLE_CHUNK_CULLING)
    for (uint8_t c=0;c<CASTLE_CHUNK_COUNT;++c) {
        uint16_t f0=castle_chunk_first[c],fc=castle_chunk_count[c];
        uint16_t v0=castle_chunk_vfirst[c],vc=castle_chunk_vcount[c];
        for (uint32_t k=(uint32_t)f0*4u;k<(uint32_t)(f0+fc)*4u;++k)
            ci[k]=(uint16_t)(ci[k]-v0);
        SAT_PANIC_IF_ERROR(sat_mesh_init(&chunk_meshes[c],&cv[v0],vc,&ci[(uint32_t)f0*4u],fc));
        chunk_meshes[c].vertex_count=vc;
        chunk_meshes[c].face_count=fc;
        chunk_instances[c]=(sat_scene3d_instance_t){
            .mesh=&chunk_meshes[c],.materials=cmat,.material_count=CT*2,
            .face_materials=&cm[f0],.world=0,.bounds=&castle_chunk_bounds[c],
            .pass=SM64DS_ACTOR_PASS,.cull_backfaces=SAT_SCENE3D_CULL_SCREEN,
            .double_sided_faces=&castle_double_sided[f0]
        };
    }
#endif
    actor=(sat_scene3d_instance_t){.mesh=&mesh,.materials=materials,.material_count=T,
        .face_materials=face_materials,.world=&actor_world,.pass=SM64DS_ACTOR_PASS,.cull_backfaces=SAT_SCENE3D_CULL_SCREEN};
    init_shadow_texture();
    SAT_PANIC_IF_ERROR(sat_model_upload_textures(&shadow_model,&shadow_texture,1));
    shadow_material=(sat_scene3d_material_t){.kind=SAT_SCENE3D_INDEXED_TEXTURED,.rgb555=0,
        .texture=&shadow_texture,.color_calc_slot=SAT_INDEXED_SOLID_OPAQUE,.sprite_flags=SAT_SPRITE_FLAG_MESH};
#ifdef CASTLE_WATER_PLANE
    water_texture_init();
#endif
#ifdef CASTLE_PROPS_AVAILABLE
    SAT_PANIC_IF_ERROR(sat_model_upload_textures(&castle_tree_model,&tree_texture,1));
    tree_material=(sat_scene3d_material_t){.kind=SAT_SCENE3D_INDEXED_TEXTURED,.rgb555=0,
        .texture=&tree_texture,.color_calc_slot=SAT_INDEXED_SOLID_OPAQUE};
    const sm64ds_background_buffers_t sb={sv,si,st,smat,sm,SN,SF,ST};
    SAT_PANIC_IF_ERROR(sm64ds_background_init(&sign_prop,&castle_sign_model,&sb));
    sign_prop.instance.pass=SM64DS_ACTOR_PASS;
    sign_prop.instance.cull_backfaces=0;
    for (uint32_t i=0;i<CASTLE_SIGN_COUNT;++i) {
        sat_model_transform3d_t tr;
        sat_model_transform3d_identity(&tr);
        tr.position=castle_sign_positions[i];
        tr.rotation_deg.y=(int32_t)castle_sign_yaw_deg[i]*ONE;
        SAT_PANIC_IF_ERROR(sat_model_transform3d_matrix(&tr,&sign_worlds[i]));
    }
#ifdef CASTLE_ACTOR_KINDS_AVAILABLE
    for (uint32_t k=0;k<CASTLE_ACTOR_KIND_COUNT;++k)
        SAT_PANIC_IF_ERROR(sm64ds_actor_kind_init(castle_actor_kinds[k]));
#endif
#endif
#ifdef CASTLE_INTERIOR_PROPS_AVAILABLE
    SAT_PANIC_IF_ERROR(sat_model_upload_textures(&castle_painting_model,painting_textures,CASTLE_PAINTING_TEXTURE_COUNT));
    for (uint16_t i=0;i<CASTLE_PAINTING_TEXTURE_COUNT;++i) {
        painting_materials[i]=(sat_scene3d_material_t){
            .kind=SAT_SCENE3D_INDEXED_TEXTURED,
            .rgb555=sm64ds_texture_fallback(&castle_painting_model,i),
            .texture=&painting_textures[i],
            .color_calc_slot=SAT_INDEXED_SOLID_OPAQUE
        };
    }
    const sm64ds_background_buffers_t db={dv,di,dt,dmat,dm,DN,DF,DT};
    SAT_PANIC_IF_ERROR(sm64ds_background_init(&door_prop,&castle_door_model,&db));
    door_prop.instance.pass=SM64DS_ACTOR_PASS;
    door_prop.instance.cull_backfaces=SAT_SCENE3D_CULL_SCREEN;
    for (uint32_t i=0;i<CASTLE_DOOR_COUNT;++i) {
        sat_model_transform3d_t tr;
        sat_model_transform3d_identity(&tr);
        tr.position=castle_door_positions[i];
        tr.rotation_deg.y=(int32_t)castle_door_yaw_deg[i]*ONE;
        SAT_PANIC_IF_ERROR(sat_model_transform3d_matrix(&tr,&door_worlds[i]));
    }
    const sm64ds_background_buffers_t tb={tv,ti,tt,tmat,tm,TN,TF,TT};
    SAT_PANIC_IF_ERROR(sm64ds_background_init(&toad_prop,&castle_toad_model,&tb));
    toad_prop.instance.pass=SM64DS_ACTOR_PASS;
    toad_prop.instance.cull_backfaces=SAT_SCENE3D_CULL_SCREEN;
    for (uint32_t i=0;i<CASTLE_TOAD_COUNT;++i) {
        sat_model_transform3d_t tr;
        sat_model_transform3d_identity(&tr);
        tr.position=castle_toad_positions[i];
        tr.rotation_deg.y=(int32_t)castle_toad_yaw_deg[i]*ONE;
        SAT_PANIC_IF_ERROR(sat_model_transform3d_matrix(&tr,&toad_worlds[i]));
    }
#endif
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
#ifdef CASTLE_ROOM_CULLING
        for (uint8_t r=0;r<CASTLE_ROOM_COUNT;++r) room_instances[r].cull_backfaces=0;
#elif defined(CASTLE_CHUNK_CULLING)
        for (uint8_t c=0;c<CASTLE_CHUNK_COUNT;++c) chunk_instances[c].cull_backfaces=0;
#endif
#ifdef CASTLE_PROPS_AVAILABLE
        sign_prop.instance.cull_backfaces=0;
#endif
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
#ifdef CASTLE_ROOM_CULLING
    for (uint8_t r=0;r<CASTLE_ROOM_COUNT;++r) {
        room_instances[r].materials=diagnostic_castle_materials;
        room_instances[r].material_count=CF;
    }
#elif defined(CASTLE_CHUNK_CULLING)
    for (uint8_t c=0;c<CASTLE_CHUNK_COUNT;++c) {
        chunk_instances[c].materials=diagnostic_castle_materials;
        chunk_instances[c].material_count=CF;
    }
#endif
#endif
#endif
        SAT_PANIC_IF_ERROR(sat_scene_init(&scene,faces,keys,order,CAP));
#if !SM64DS_VISUAL_DIAGNOSTICS
        SAT_PANIC_IF_ERROR(sat_scene3d_faces_use_projected_storage(&scene.faces,projected_faces,CAP));
    SAT_PANIC_IF_ERROR(sat_scene3d_material_programs_init(&castle_programs,cmat,CT*2,castle_prog_entries,CT*2));
#ifdef CASTLE_ROOM_CULLING
    for (uint8_t r=0;r<CASTLE_ROOM_COUNT;++r) {
        uint16_t f0=castle_room_first[r];
        SAT_PANIC_IF_ERROR(sat_scene3d_instance_binding_init(&room_bindings[r],&room_meshes[r],cmat,CT*2,&cm[f0]));
        room_bindings[r].programs=&castle_programs;
        room_instances[r].validated_binding=&room_bindings[r];
    }
#elif defined(CASTLE_CHUNK_CULLING)
    for (uint8_t c=0;c<CASTLE_CHUNK_COUNT;++c) {
        uint16_t f0=castle_chunk_first[c];
        SAT_PANIC_IF_ERROR(sat_scene3d_instance_binding_init(&chunk_bindings[c],&chunk_meshes[c],cmat,CT*2,&cm[f0]));
        chunk_bindings[c].programs=&castle_programs;
        chunk_instances[c].validated_binding=&chunk_bindings[c];
    }
#ifdef CASTLE_SLAVE_CHUNKS
    slave_chunks_setup();
    slave_chunks_init();
#endif
#else
    SAT_PANIC_IF_ERROR(sat_scene3d_instance_binding_init(&castle_binding,&castle.mesh,cmat,CT*2,cm));
    castle_binding.programs=&castle_programs;castle.instance.validated_binding=&castle_binding;
#endif
#if CASTLE_HAS_SKYBOX
    SAT_PANIC_IF_ERROR(sat_scene3d_material_programs_init(&sky_programs,bmat,BT,sky_prog_entries,BT));
    SAT_PANIC_IF_ERROR(sat_scene3d_instance_binding_init(&sky_binding,&sky.mesh,bmat,BT,bm));
    sky_binding.programs=&sky_programs;sky.instance.validated_binding=&sky_binding;
    if (sky_oct_ready) {
        for (uint8_t o=0;o<8u;++o) {
            if (!sky_oct_meshes[o].face_count) continue;
            SAT_PANIC_IF_ERROR(sat_scene3d_instance_binding_init(
                &sky_oct_bindings[o],&sky_oct_meshes[o],bmat,BT,sky_oct_instances[o].face_materials));
            sky_oct_bindings[o].programs=&sky_programs;
            sky_oct_instances[o].validated_binding=&sky_oct_bindings[o];
        }
    }
#endif
    SAT_PANIC_IF_ERROR(sat_scene3d_material_programs_init(&actor_programs,materials,T,actor_prog_entries,T));
    SAT_PANIC_IF_ERROR(sat_scene3d_instance_binding_init(&actor_binding,&mesh,materials,T,face_materials));
    actor_binding.programs=&actor_programs;actor.validated_binding=&actor_binding;
    SAT_PANIC_IF_ERROR(sat_scene3d_material_programs_init(&head_programs,hmat,HT,head_prog_entries,HT));
    SAT_PANIC_IF_ERROR(sat_scene3d_instance_binding_init(&head_binding,&head.mesh,hmat,HT,hm));
    head_binding.programs=&head_programs;head.instance.validated_binding=&head_binding;
#ifdef CASTLE_PROPS_AVAILABLE
    SAT_PANIC_IF_ERROR(sat_scene3d_material_programs_init(&sign_programs,smat,ST,sign_prog_entries,ST));
    SAT_PANIC_IF_ERROR(sat_scene3d_instance_binding_init(&sign_binding,&sign_prop.mesh,smat,ST,sm));
    sign_binding.programs=&sign_programs;sign_prop.instance.validated_binding=&sign_binding;
#endif
#ifdef CASTLE_INTERIOR_PROPS_AVAILABLE
    SAT_PANIC_IF_ERROR(sat_scene3d_material_programs_init(&door_programs,dmat,DT,door_prog_entries,DT));
    SAT_PANIC_IF_ERROR(sat_scene3d_instance_binding_init(&door_binding,&door_prop.mesh,dmat,DT,dm));
    door_binding.programs=&door_programs;door_prop.instance.validated_binding=&door_binding;
    SAT_PANIC_IF_ERROR(sat_scene3d_material_programs_init(&toad_programs,tmat,TT,toad_prog_entries,TT));
    SAT_PANIC_IF_ERROR(sat_scene3d_instance_binding_init(&toad_binding,&toad_prop.mesh,tmat,TT,tm));
    toad_binding.programs=&toad_programs;toad_prop.instance.validated_binding=&toad_binding;
#endif
#endif
    SAT_PANIC_IF_ERROR(sat_ascii_font_init_8x8_indexed8(&font,SAT_COLOR_WHITE,0,3));
#if defined(CASTLE_WARP_AVAILABLE) && !SM64DS_VISUAL_DIAGNOSTICS
    /* Eager init so the loading screen's CRAM bank 6 is in place before any
     * warp transition draws it (the lazy path in draw_warp_fade stays as a
     * fallback). */
    sm64ds_loading_init(&warp_loading);
#endif
#if defined(CASTLE_INTRO_PROPS_AVAILABLE) && !SM64DS_VISUAL_DIAGNOSTICS
    if (intro_cutscene_active) {
        intro_init_props();
        intro_init_audio();
    }
#endif
    g_sm64ds_castle_stats.texture_arena_remaining=sat_vdp1_vram_free_bytes();
    player.spawn=(sat_vec3_t){castle_entrances[0].x,0,castle_entrances[0].z};
    int32_t spawn_floor_ceiling=castle_entrances[0].floor_ceiling;
    spawn_yaw_default=castle_entrances[0].yaw;
    spawn_facing_default=castle_entrances[0].facing;
#if defined(CASTLE_WARP_AVAILABLE) && !SM64DS_VISUAL_DIAGNOSTICS
    if (in_arg_valid) {
        if (in_arg.hud_mode<3u) hud_mode=in_arg.hud_mode;
        close_camera=in_arg.close_camera?1:0;
        g_stars=in_arg.stars;
        g_star_bits=in_arg.star_bits;
        if (in_arg.entrance!=SM64DS_ENTRANCE_INTRO && in_arg.entrance<castle_stage.entrance_count) {
            const sm64ds_entrance_t *e=&castle_entrances[in_arg.entrance];
            player.spawn.x=e->x;
            player.spawn.z=e->z;
            spawn_floor_ceiling=e->floor_ceiling;
            spawn_yaw_default=e->yaw;
            spawn_facing_default=e->facing;
        }
    }
#endif
#if SM64DS_VISUAL_DIAGNOSTICS && SM64DS_DIAG_FIXED_CAMERA
    player.spawn.x=SM64DS_DIAG_X*ONE;
    player.spawn.z=SM64DS_DIAG_Z*ONE;
    spawn_floor_ceiling=SM64DS_DIAG_FLOOR_CEILING*ONE;
#endif
    int32_t floor;
    if(!sm64ds_floor(&castle_collision,player.spawn.x,player.spawn.z,spawn_floor_ceiling,&floor))
        SAT_PANIC_IF_ERROR(SAT_ERR_INVALID_ARG);
    player.spawn.y=floor;reset();
#if SM64DS_VISUAL_DIAGNOSTICS && SM64DS_DIAG_FIXED_CAMERA && SM64DS_DIAG_ORBIT_PLAYER
    yaw=((SM64DS_DIAG_YAW%360)+360)%360;
#endif
    /* The actor origin must not track the animated lowest vertex: doing so
     * cancels foot lift and moves the whole body (including the head) as
     * the pose changes. Calibrate once using the initial idle pose. */
    skin();
    const int32_t idle_ground_y=bounds.center.y-bounds.half.y;
    camera.up=(sat_vec3_t){0,ONE,0};
#if SM64DS_VISUAL_DIAGNOSTICS
    camera.fov_y=SM64DS_DIAG_FOV_Y*ONE;
#else
    camera.fov_y=60*ONE;
#endif
#if SM64DS_VISUAL_DIAGNOSTICS && SM64DS_DIAG_DS_ASPECT
    camera.aspect=sat_fx16_div(256*ONE,192*ONE);
#else
    camera.aspect=sat_fx16_div(320*ONE,224*ONE);camera.near_z=ONE;camera.far_z=1600*ONE;
#endif
    camera.near_z=ONE;camera.far_z=1600*ONE;
#if SM64DS_VDP2_SKY
    sky_init();
#endif
    uint32_t previous=sat_time_ms(),accumulator=0;
    uint16_t jump_pending=0;
    uint32_t frame_ms_ring[8]={0},cpu_ms_ring[8]={0};
    uint32_t frame_ms_sum=0,cpu_ms_sum=0,prev_late_swaps=0;
    uint8_t timing_idx=0,timing_count=0;
    g_sm64ds_castle_profile.frequency_hz=sat_time_frequency_hz();
    profile_mark=sat_time_ticks();
    while(1) {
        /* No VBlank wait: in SAT_VDP1_FRAME_ON_SUBMIT mode sat_end_frame
         * already waits for the previous list's swap before reusing its
         * VRAM, and a frame takes several fields of CPU work, so waiting
         * here only idled the CPU until the next field. */
        profile_lap(PROF_VBLANK);
        sat_pad_state_t pad={0};SAT_PANIC_IF_ERROR(sat_pad_poll(&pad));
        uint32_t now=sat_time_ms(),elapsed=now-previous;previous=now;
        if(elapsed>250)elapsed=250;
#if defined(CASTLE_INTRO_PROPS_AVAILABLE) && !SM64DS_VISUAL_DIAGNOSTICS
        int intro_mario_vis=1,intro_pipe_vis=0,intro_lakitu_vis=0;
        if (intro_cutscene_active) {
            if (intro_music_open) (void)sat_music_update(intro_music);
            if (intro_audio_ready) (void)sat_audio_update();
            if ((pad.pressed&SAT_PAD_START)!=0u && intro_ticks>8u) {
                intro_finish_cutscene();
            } else {
                accumulator+=elapsed*30u;
                while (accumulator>=1000u && intro_cutscene_active) {
                    accumulator-=1000u;
                    ++intro_ticks;
                    intro_lakitu_anim+=ONE/30;
                    if (intro_lakitu_anim>=((int32_t)lakitu_actor_clips[0].frame_count*ONE)/30)
                        intro_lakitu_anim=0;
                    if (intro_ticks>=CASTLE_INTRO_DURATION_TICKS) {
                        intro_finish_cutscene();
                    }
                }
            }
        }
        if (!intro_cutscene_active) {
#endif
        if(pad.pressed&SAT_PAD_START)paused=!paused;
        if(pad.pressed&SAT_PAD_C)reset();
        if(pad.pressed&SAT_PAD_X)close_camera=!close_camera;
        if(pad.pressed&SAT_PAD_Y)hud_mode=(uint8_t)((hud_mode+1u)%3u);
#if defined(CASTLE_WARP_AVAILABLE) && !SM64DS_VISUAL_DIAGNOSTICS
        if (warp_fade==0u && (pad.held&(SAT_PAD_L|SAT_PAD_R))==(SAT_PAD_L|SAT_PAD_R) &&
            (pad.pressed&SAT_PAD_Z)) {
            warp_fade=1u;
            warp_target=&castle_warps[0];
        }
#endif
        jump_pending|=pad.pressed&SAT_PAD_A;
        if(!paused
#if defined(CASTLE_WARP_AVAILABLE) && !SM64DS_VISUAL_DIAGNOSTICS
           && warp_fade==0u
#endif
        ) {
            accumulator+=elapsed*60;
            uint32_t steps=0;
            while(accumulator>=1000) {
                uint8_t was_dead=player.dead;
                simulation(&pad,jump_pending!=0);jump_pending=0;accumulator-=1000;++steps;
                if(was_dead && !player.dead) reset_view();   /* death finished: respawn view */
            }
            if(player.feet.y<castle_stage.kill_y) reset();
            g_sm64ds_castle_profile.sim_steps+=steps;
            if(steps>g_sm64ds_castle_profile.max_sim_steps) g_sm64ds_castle_profile.max_sim_steps=steps;
        } else {accumulator=0;jump_pending=0;}
#if defined(CASTLE_WARP_AVAILABLE) && !SM64DS_VISUAL_DIAGNOSTICS
        if (warp_fade==0u && player.ticks>45u) {
            for (uint32_t w=0;w<castle_stage.warp_count;++w) {
                const sm64ds_warp_t *k=&castle_warps[w];
                if (player.feet.x>=k->min[0] && player.feet.x<=k->max[0] &&
                    player.feet.y>=k->min[1] && player.feet.y<=k->max[1] &&
                    player.feet.z>=k->min[2] && player.feet.z<=k->max[2] &&
                    (!k->needs_air || !player.grounded)) {
                    warp_fade=1u;
                    warp_target=k;
                    break;
                }
            }
        }
        if (warp_fade>0u) {
            ++warp_fade;
            /* Hold the loading screen ~20 frames so the "NOW LOADING" bar is
             * readable, then read the next stage over the frozen frame. */
            if (warp_fade>=23u) execute_stage_warp(warp_target);
        }
#endif
#if defined(CASTLE_INTRO_PROPS_AVAILABLE) && !SM64DS_VISUAL_DIAGNOSTICS
        }
#endif
#if SM64DS_VISUAL_DIAGNOSTICS && SM64DS_DIAG_FIXED_CAMERA
        /* Reproduce the same state even when render cadence changes pad polls. */
        sm64ds_player_reset(&player);
#if SM64DS_DIAG_OVERRIDE_PLAYER_Y
        player.feet.y=SM64DS_DIAG_PLAYER_Y*ONE;
#endif
        player.grounded=1;player.velocity_y=0;
#if !SM64DS_DIAG_ORBIT_PLAYER
        yaw=((SM64DS_DIAG_YAW%360)+360)%360;
#endif
        close_camera=SM64DS_DIAG_CLOSE_CAMERA;
        facing=((SM64DS_DIAG_FACING%360)+360)%360;
#endif
#if SM64DS_VISUAL_DIAGNOSTICS && !SM64DS_DIAG_LIVE_ANIMATION
        clip=SM64DS_DIAG_CLIP;
        anim_time=(int32_t)(((int64_t)SM64DS_DIAG_FRAME*ONE+29)/30);
#endif
#if defined(CASTLE_INTRO_PROPS_AVAILABLE) && !SM64DS_VISUAL_DIAGNOSTICS
        if (intro_cutscene_active) {
            intro_update_cutscene_pose(&intro_mario_vis,&intro_pipe_vis,&intro_lakitu_vis);
            (void)sat_vdp2_layers_commit();
        }
#endif
        profile_lap(PROF_SIM);
        skin();
        profile_lap(PROF_SKIN);
        sat_model_transform3d_t transform;
        sat_model_transform3d_identity(&transform);
        /* The imported BMD skin is twice the gameplay-space height in the
         * DS reference. Keep the actor on the KCL floor after correcting it. */
        transform.scale=(sat_vec3_t){ONE/2,ONE/2,ONE/2};
        transform.position=player.feet;transform.position.y-=sat_fx16_mul(idle_ground_y,transform.scale.y);
#if SM64DS_VISUAL_DIAGNOSTICS && SM64DS_DIAG_GROUND_POSE
        /* Preserve positive foot lift, but don't sink a grounded pose below
         * the collision point. Airborne animation is not adjusted. */
        int32_t pose_low=bounds.center.y-bounds.half.y;
        if(player.grounded && pose_low<idle_ground_y)
            transform.position.y+=sat_fx16_mul(idle_ground_y-pose_low,transform.scale.y)+ONE/256;
#endif
        transform.rotation_deg.y=facing*ONE;
        if(player.swimming) {
            /* St_Swim's body pitch: 6/10 of the nose-up angle, 10/8 nose down. */
            int32_t pitch=player.pitch<0?player.pitch*6/10:player.pitch*10/8;
            transform.rotation_deg.x=pitch*360;
        }
        SAT_PANIC_IF_ERROR(sat_model_transform3d_matrix(&transform,&actor_world));
        if(player.swimming&&transform.rotation_deg.x) {
            /* Pitch the swimmer about mid-body, not the feet, so a tilted
             * Mario does not swing up out of the water. The local Y axis in
             * the matrix is scaled by ONE/2, hence the doubling. */
            const int32_t half=6*ONE;
            actor_world.m[3]-=sat_fx16_mul(half,actor_world.m[1]*2);
            actor_world.m[7]+=half-sat_fx16_mul(half,actor_world.m[5]*2);
            actor_world.m[11]-=sat_fx16_mul(half,actor_world.m[9]*2);
        }
#if SM64DS_VISUAL_DIAGNOSTICS && SM64DS_DIAG_GROUND_POSE
        if(player.grounded) {
            sat_vec3_t normal;int32_t floor;
            if(sm64ds_floor_normal(&castle_collision,player.feet.x,player.feet.z,
                                   player.feet.y+ONE/4,&floor,&normal) &&
               floor>=player.feet.y-ONE/4) {
                sat_vec3_t contact={player.feet.x,floor,player.feet.z};
                int32_t lift=sm64ds_ground_pose_lift(vertices,N,&actor_world,&contact,&normal);
                if(lift>0 && lift<=2*ONE) actor_world.m[7]+=lift;
            }
        }
#endif
        SAT_PANIC_IF_ERROR(sat_mat4_multiply(&head.world,&actor_world,&bones[15]));
#if defined(CASTLE_INTRO_PROPS_AVAILABLE) && !SM64DS_VISUAL_DIAGNOSTICS
        if (!intro_cutscene_active)
#endif
        update_camera();
#ifdef CASTLE_WATER_LAYERS
        update_water_tint();
#endif
#ifdef CASTLE_ROOM_CULLING
        update_visible_rooms();
#endif
        profile_lap(PROF_CAMERA);
#if !SM64DS_VDP2_SKY
        SAT_PANIC_IF_ERROR(sat_set_clear_color(SAT_RGB555(castle_stage.bg_rgb[0],castle_stage.bg_rgb[1],castle_stage.bg_rgb[2])));
#endif
        SAT_PANIC_IF_ERROR(sat_begin_frame());
#if !SM64DS_VISUAL_DIAGNOSTICS || SM64DS_DIAG_SHOW_UI
        uint16_t overlay_reserve=hud_mode==0u?180u:(hud_mode==1u?56u:4u);
#if defined(CASTLE_INTRO_PROPS_AVAILABLE)
        if (intro_cutscene_active) overlay_reserve=32u;
#endif
#else
        uint16_t overlay_reserve=0u;
#endif
        SAT_PANIC_IF_ERROR(sat_scene_begin(&scene,&camera,camera.near_z,320,224,overlay_reserve));
        uint16_t previous_clipped=scene.faces.clipped_faces;
        profile_lap(PROF_BEGIN);
#if CASTLE_HAS_SKYBOX
        if (!SM64DS_EXP_NO_SKY && (!SM64DS_VISUAL_DIAGNOSTICS || (SM64DS_DIAG_OBJECTS&1))) {
            if (sky_oct_ready) {
                SAT_PANIC_IF_ERROR(sat_mat4_translate(&sky.world,camera.eye.x,camera.eye.y,camera.eye.z));
                for (uint8_t o=0;o<8u;++o) {
                    if (!sky_oct_meshes[o].face_count) continue;
                    uint16_t v0=sky_oct_vfirst[o];
                    SAT_PANIC_IF_ERROR(sat_scene_submit_instance(
                        &scene,&sky_oct_instances[o],SAT_SCENE3D_SLOT_INHERIT,&sky_op[v0],&sky_ow[v0]));
                }
            } else {
                SAT_PANIC_IF_ERROR(sm64ds_background_submit(&sky,&scene,&camera.eye,bp,bw));
            }
        }
#endif
#if SM64DS_VDP2_SKY
        sky_update();
#endif
        profile_lap(PROF_SKY);
        g_sm64ds_castle_stats.sky_clip_candidates=scene.faces.clipped_faces-previous_clipped;
        previous_clipped=scene.faces.clipped_faces;
#if (!SM64DS_VISUAL_DIAGNOSTICS && defined(CASTLE_SUPPORT_PLANE_LIST_AVAILABLE)) || (SM64DS_VISUAL_DIAGNOSTICS && SM64DS_DIAG_FAR_DEPTH_COUNT > 0)
        uint16_t castle_first=scene.faces.count;
#endif
        if (!SM64DS_VISUAL_DIAGNOSTICS || (SM64DS_DIAG_OBJECTS&2)) {
#ifdef CASTLE_ROOM_CULLING
            for (uint8_t r=0;r<CASTLE_ROOM_COUNT;++r) {
                room_qfirst[r]=scene.faces.count;
                if (visible_room_mask&(1u<<r)) {
                    uint16_t v0=castle_room_vfirst[r];
                    SAT_PANIC_IF_ERROR(sat_scene_submit_instance(
                        &scene,&room_instances[r],SAT_SCENE3D_SLOT_INHERIT,&cp[v0],0));
                }
                room_qend[r]=scene.faces.count;
            }
#elif defined(CASTLE_CHUNK_CULLING)
            hud_chunks_drawn=0u;
            const uint16_t extra_reserve=
#if defined(CASTLE_INTRO_PROPS_AVAILABLE) && !SM64DS_VISUAL_DIAGNOSTICS
                intro_cutscene_active?540u:260u;
#else
                260u;
#endif
            const uint16_t chunk_cap=(uint16_t)(2048u-overlay_reserve-extra_reserve);
#ifdef CASTLE_WATER_PLANE
            const uint16_t terrain_cap=chunk_cap-WATER_PLANE_RINGS*WATER_PLANE_CELLS*WATER_PLANE_CELLS;
#else
            const uint16_t terrain_cap=chunk_cap;
#endif
#ifdef CASTLE_WATER_LAYERS
            /* Faces wholly on the far side of the water surface from the camera
             * cannot be in front of the rest, so they draw first, then the water. */
            const uint8_t camera_above=camera.eye.y>=CASTLE_WATER_Y;
            const uint16_t layer_pass[3]={
                camera_above?SM64DS_FAR_WATER_PASS:SM64DS_ACTOR_PASS,SM64DS_WATER_PASS,
                camera_above?SM64DS_ACTOR_PASS:SM64DS_FAR_WATER_PASS};
#endif
#ifdef CASTLE_SLAVE_CHUNKS
#ifdef CASTLE_WATER_LAYERS
            for (uint8_t c=0;c<CASTLE_CHUNK_COUNT;++c)
                chunk_instances[c].pass=layer_pass[castle_chunk_layer[c]];
#endif
            const int slave_pending=slave_chunks_begin(terrain_cap);
            for (uint8_t c=0;c<CASTLE_CHUNK_COUNT;++c) {
                chunk_qfirst[c]=chunk_qend[c]=scene.faces.count;
                if (!chunk_visible[c] || chunk_on_slave[c]) continue;
                if (scene.faces.count+scene.faces.projected_gap<terrain_cap) submit_chunk(c);
                chunk_qend[c]=scene.faces.count;
            }
#ifdef CASTLE_WATER_PLANE
            /* Built and queued while the Slave works; it still lands inside
             * the castle range, ahead of the Slave's chunks. */
            draw_water_texture(SM64DS_WATER_PASS);
#endif
            if (slave_pending) slave_chunks_finish();
            for (uint8_t c=0;c<CASTLE_CHUNK_COUNT;++c)
                if (chunk_qend[c]>chunk_qfirst[c]) ++hud_chunks_drawn;
#else
            for (uint8_t c=0;c<CASTLE_CHUNK_COUNT;++c) {
                chunk_qfirst[c]=scene.faces.count;
                if (scene.faces.count<terrain_cap && !exp_chunk_far(c)) {
                    uint16_t v0=castle_chunk_vfirst[c];
#ifdef CASTLE_WATER_LAYERS
                    chunk_instances[c].pass=layer_pass[castle_chunk_layer[c]];
#endif
                    SAT_PANIC_IF_ERROR(sat_scene_submit_instance(
                        &scene,&chunk_instances[c],SAT_SCENE3D_SLOT_INHERIT,&cp[v0],0));
                }
                chunk_qend[c]=scene.faces.count;
                if (chunk_qend[c]>chunk_qfirst[c]) ++hud_chunks_drawn;
            }
#endif
#else
            SAT_PANIC_IF_ERROR(sat_scene_submit_instance(&scene,&castle.instance,SAT_SCENE3D_SLOT_INHERIT,cp,0));
#endif
#if defined(CASTLE_WATER_PLANE) && !defined(CASTLE_SLAVE_CHUNKS)
            /* The water surface draws between the submerged terrain and the
             * dry world / actors. */
            draw_water_texture(SM64DS_WATER_PASS);
#endif
        }
#if (!SM64DS_VISUAL_DIAGNOSTICS && defined(CASTLE_SUPPORT_PLANE_LIST_AVAILABLE)) || (SM64DS_VISUAL_DIAGNOSTICS && SM64DS_DIAG_FAR_DEPTH_COUNT > 0 && (SM64DS_DIAG_GEOMETRIC_DEPTH || SM64DS_DIAG_PAIR_DEPTH || SM64DS_DIAG_SUPPORT_DEPTH))
        uint16_t castle_end=scene.faces.count;
#endif
#if SM64DS_VISUAL_DIAGNOSTICS && SM64DS_DIAG_FAR_DEPTH_COUNT > 0 && !SM64DS_DIAG_GEOMETRIC_DEPTH && !SM64DS_DIAG_PAIR_DEPTH && !SM64DS_DIAG_SUPPORT_DEPTH
        diagnostic_far_depth(castle_first,scene.faces.count);
#endif
#if SM64DS_VISUAL_DIAGNOSTICS && SM64DS_DIAG_WALL_FIXTURE
        if(SM64DS_DIAG_OBJECTS&2) {
            /* Reproducible front wall for the recorded orbit pose. */
            const int left_x=SM64DS_DIAG_WALL_PARTIAL?-69:-75;
            const int left_z=SM64DS_DIAG_WALL_PARTIAL?392:383;
            const int right_x=SM64DS_DIAG_WALL_PARTIAL?-66:-61;
            const int right_z=SM64DS_DIAG_WALL_PARTIAL?396:403;
            const sat_quad3_t wall={.v={{left_x*ONE,8*ONE,left_z*ONE},{right_x*ONE,8*ONE,right_z*ONE},
                                       {right_x*ONE,45*ONE,right_z*ONE},{left_x*ONE,45*ONE,left_z*ONE}}};
            const sat_scene3d_material_t wall_material={.kind=SAT_SCENE3D_RGB,
                .rgb555=SAT_RGB555(31,0,31),.color_calc_slot=SAT_INDEXED_SOLID_OPAQUE};
            SAT_PANIC_IF_ERROR(sat_scene_submit_quad(&scene,&wall,&wall_material,SM64DS_ACTOR_PASS));
        }
#endif
        g_sm64ds_castle_stats.castle_clip_candidates=scene.faces.clipped_faces-previous_clipped;
        previous_clipped=scene.faces.clipped_faces;
        profile_lap(PROF_CASTLE);
#ifdef CASTLE_PROPS_AVAILABLE
        if (!SM64DS_VISUAL_DIAGNOSTICS ||
            ((SM64DS_DIAG_OBJECTS&2) && !SM64DS_DIAG_CASTLE_FACE_IDS && !SM64DS_DIAG_SOLID &&
             SM64DS_DIAG_FAR_DEPTH_COUNT==0))
            submit_castle_props();
#endif
#ifdef CASTLE_INTERIOR_PROPS_AVAILABLE
        if (!SM64DS_VISUAL_DIAGNOSTICS ||
            ((SM64DS_DIAG_OBJECTS&2) && !SM64DS_DIAG_CASTLE_FACE_IDS && !SM64DS_DIAG_SOLID &&
             SM64DS_DIAG_FAR_DEPTH_COUNT==0))
            submit_interior_props();
#endif
#if defined(CASTLE_INTRO_PROPS_AVAILABLE) && !SM64DS_VISUAL_DIAGNOSTICS
        if (intro_cutscene_active) {
            if (intro_pipe_vis) {
                SAT_PANIC_IF_ERROR(sat_scene_submit_instance(&scene,&pipe_prop.instance,SAT_SCENE3D_SLOT_INHERIT,pp,pw));
            }
            if (intro_lakitu_vis) {
                SAT_PANIC_IF_ERROR(sat_scene_submit_instance(&scene,&lakitu_inst,SAT_SCENE3D_SLOT_INHERIT,lp,lw));
            }
        }
#endif
        profile_lap(PROF_PROPS);
#if !SM64DS_VISUAL_DIAGNOSTICS && defined(CASTLE_SUPPORT_PLANE_LIST_AVAILABLE)
        uint16_t shadow_first=scene.faces.count;
#endif
        if ((!SM64DS_VISUAL_DIAGNOSTICS ||
            ((SM64DS_DIAG_OBJECTS&4) && !SM64DS_DIAG_FACE_IDS && !SM64DS_DIAG_CASTLE_FACE_IDS &&
             !SM64DS_DIAG_SOLID && SM64DS_DIAG_FAR_DEPTH_COUNT==0))
#if defined(CASTLE_INTRO_PROPS_AVAILABLE) && !SM64DS_VISUAL_DIAGNOSTICS
            && (!intro_cutscene_active || intro_mario_vis)
#endif
        )
            submit_mario_shadow();
#if (!SM64DS_VISUAL_DIAGNOSTICS && defined(CASTLE_SUPPORT_PLANE_LIST_AVAILABLE)) || (SM64DS_VISUAL_DIAGNOSTICS && SM64DS_DIAG_FAR_DEPTH_COUNT > 0 && (SM64DS_DIAG_PAIR_DEPTH || SM64DS_DIAG_SUPPORT_DEPTH))
        uint16_t actor_first=scene.faces.count;
#endif
        if ((!SM64DS_VISUAL_DIAGNOSTICS || (SM64DS_DIAG_OBJECTS&4))
#if defined(CASTLE_INTRO_PROPS_AVAILABLE) && !SM64DS_VISUAL_DIAGNOSTICS
            && (!intro_cutscene_active || intro_mario_vis)
#endif
        )
            SAT_PANIC_IF_ERROR(sat_scene_submit_instance(&scene,&actor,SAT_SCENE3D_SLOT_INHERIT,projected,world_vertices));
#if SM64DS_VISUAL_DIAGNOSTICS && SM64DS_DIAG_FAR_DEPTH_COUNT > 0 && SM64DS_DIAG_PAIR_DEPTH && !SM64DS_DIAG_SUPPORT_DEPTH
        uint16_t actor_end=scene.faces.count;
#endif
        g_sm64ds_castle_stats.body_clip_candidates=scene.faces.clipped_faces-previous_clipped;
        previous_clipped=scene.faces.clipped_faces;
        if ((!SM64DS_VISUAL_DIAGNOSTICS || (SM64DS_DIAG_OBJECTS&8))
#if defined(CASTLE_INTRO_PROPS_AVAILABLE) && !SM64DS_VISUAL_DIAGNOSTICS
            && (!intro_cutscene_active || intro_mario_vis)
#endif
        )
            SAT_PANIC_IF_ERROR(sat_scene_submit_instance(&scene,&head.instance,SAT_SCENE3D_SLOT_INHERIT,hp,hw));
        g_sm64ds_castle_stats.head_clip_candidates=scene.faces.clipped_faces-previous_clipped;
        profile_lap(PROF_ACTOR);
#if !SM64DS_VISUAL_DIAGNOSTICS && defined(CASTLE_SUPPORT_PLANE_LIST_AVAILABLE)
        order_support_behind_actor(castle_first,castle_end,shadow_first,actor_first,scene.faces.count);
#endif
#if SM64DS_VISUAL_DIAGNOSTICS && SM64DS_DIAG_FAR_DEPTH_COUNT > 0 && SM64DS_DIAG_SUPPORT_DEPTH
#if SM64DS_DIAG_SUPPORT_GUARD
        uint64_t support_started=sat_time_ticks();
#endif
        diagnostic_support_depth(castle_first,castle_end,actor_first,scene.faces.count);
#if SM64DS_DIAG_SUPPORT_GUARD
        uint64_t support_ended=sat_time_ticks();
        if(support_started && support_ended>=support_started) {
            uint64_t elapsed=support_ended-support_started;
            uint32_t ticks=elapsed>UINT32_MAX?UINT32_MAX:(uint32_t)elapsed;
            ++g_sm64ds_support_diag.profile_calls;
            g_sm64ds_support_diag.profile_ticks_sum+=ticks;
            g_sm64ds_support_diag.profile_ticks_last=ticks;
            if(ticks>g_sm64ds_support_diag.profile_ticks_max) g_sm64ds_support_diag.profile_ticks_max=ticks;
        }
#endif
#elif SM64DS_VISUAL_DIAGNOSTICS && SM64DS_DIAG_FAR_DEPTH_COUNT > 0 && SM64DS_DIAG_PAIR_DEPTH
        diagnostic_pair_depth(castle_first,castle_end,actor_first,actor_end,scene.faces.count);
#elif SM64DS_VISUAL_DIAGNOSTICS && SM64DS_DIAG_FAR_DEPTH_COUNT > 0 && SM64DS_DIAG_GEOMETRIC_DEPTH
        diagnostic_geometric_depth(castle_first,castle_end);
#endif
        profile_lap(PROF_SUPPORT);
        SAT_PANIC_IF_ERROR(sat_scene_flush_trusted(&scene));
        profile_lap(PROF_FLUSH);
        sat_scene_stats_t stats={0};sat_scene_stats(&scene,&stats);
        uint32_t cpu_ms=sat_time_ms()-now;
        if (cpu_ms>250u) cpu_ms=250u;
        frame_ms_sum-=frame_ms_ring[timing_idx];
        cpu_ms_sum-=cpu_ms_ring[timing_idx];
        frame_ms_ring[timing_idx]=elapsed;
        cpu_ms_ring[timing_idx]=cpu_ms;
        frame_ms_sum+=elapsed;
        cpu_ms_sum+=cpu_ms;
        timing_idx=(uint8_t)((timing_idx+1u)&7u);
        if (timing_count<8u) ++timing_count;
        uint32_t avg_ms=timing_count?(frame_ms_sum+timing_count/2u)/timing_count:elapsed;
        uint32_t avg_cpu_ms=timing_count?(cpu_ms_sum+timing_count/2u)/timing_count:cpu_ms;
        uint32_t fps=frame_ms_sum?(timing_count*1000u+frame_ms_sum/2u)/frame_ms_sum:0u;
        sat_vdp1_frame_stats_t vdp1_fstats={0};
        sat_vdp1_frame_stats(&vdp1_fstats);
        uint32_t late_delta=vdp1_fstats.late_swaps-prev_late_swaps;
        prev_late_swaps=vdp1_fstats.late_swaps;
#if !SM64DS_VISUAL_DIAGNOSTICS || SM64DS_DIAG_SHOW_UI
#if defined(CASTLE_INTRO_PROPS_AVAILABLE) && !SM64DS_VISUAL_DIAGNOSTICS
        if (intro_cutscene_active) {
            hud_draw_text(224,210,"START:SKIP");
        } else
#endif
        draw_debug_hud(&stats,fps,avg_ms,avg_cpu_ms,late_delta);
#else
        (void)avg_ms;(void)avg_cpu_ms;(void)fps;(void)late_delta;
#endif
#if defined(CASTLE_WARP_AVAILABLE) && !SM64DS_VISUAL_DIAGNOSTICS
        draw_warp_fade(warp_fade);
#endif
        ++g_sm64ds_castle_stats.frames;g_sm64ds_castle_stats.ticks=player.ticks;
        g_sm64ds_castle_stats.jumps=player.jumps;g_sm64ds_castle_stats.landings=player.landings;
        g_sm64ds_castle_stats.wall_hits=player.wall_hits;g_sm64ds_castle_stats.resets=player.resets;
        g_sm64ds_castle_stats.x=player.feet.x;g_sm64ds_castle_stats.y=player.feet.y;g_sm64ds_castle_stats.z=player.feet.z;
        g_sm64ds_castle_stats.velocity_y=player.velocity_y;g_sm64ds_castle_stats.grounded=player.grounded;
        g_sm64ds_castle_stats.climbing=player.climbing;
        g_sm64ds_castle_stats.climb_count=player.climb_count;
        g_sm64ds_castle_stats.camera_x=camera.eye.x;g_sm64ds_castle_stats.camera_y=camera.eye.y;g_sm64ds_castle_stats.camera_z=camera.eye.z;
        g_sm64ds_castle_stats.target_x=camera.target.x;g_sm64ds_castle_stats.target_y=camera.target.y;g_sm64ds_castle_stats.target_z=camera.target.z;
        g_sm64ds_castle_stats.mario_facing=facing*ONE;g_sm64ds_castle_stats.camera_fov_y=camera.fov_y;
        g_sm64ds_castle_stats.health=player.health;g_sm64ds_castle_stats.max_health=player.max_health;
        g_sm64ds_castle_stats.dead=player.dead;g_sm64ds_castle_stats.coins=player.coins;
        g_sm64ds_castle_stats.star_bits=g_star_bits;
#ifdef CASTLE_ACTOR_KINDS_AVAILABLE
        for (uint32_t k=0;k<CASTLE_ACTOR_KIND_COUNT;++k) {
            const sm64ds_actor_kind_t *bk=castle_actor_kinds[k];
            if (bk->behavior!=SM64DS_ACTOR_BOSS) continue;
            g_sm64ds_castle_stats.boss_hp=bk->hp_left;
            g_sm64ds_castle_stats.boss_held=sm64ds_actor_held(bk);
            for (uint16_t i=0;i<bk->count;++i) {
                g_sm64ds_castle_stats.boss_state=bk->st[i];
                g_sm64ds_castle_stats.boss_x=bk->pos[i].x;
                g_sm64ds_castle_stats.boss_y=bk->pos[i].y;
                g_sm64ds_castle_stats.boss_z=bk->pos[i].z;
            }
        }
#endif
        g_sm64ds_castle_stats.clip=clip;g_sm64ds_castle_stats.commands=stats.commands_used;
        g_sm64ds_castle_stats.skipped=stats.skipped_faces;g_sm64ds_castle_stats.faces=stats.submitted_faces;
        g_sm64ds_castle_stats.paused=paused;
        g_sm64ds_castle_stats.culled=stats.culled_faces;
        g_sm64ds_castle_stats.clipped=stats.clipped_faces;
        g_sm64ds_castle_stats.fallback=stats.fallback_faces;
        profile_lap(PROF_HUD);
        SAT_PANIC_IF_ERROR(sat_end_frame());
        profile_lap(PROF_END);
        ++g_sm64ds_castle_profile.frames;
        g_sm64ds_castle_profile.vdp1_draw_waits=vdp1_fstats.draw_waits;
        g_sm64ds_castle_profile.vdp1_draw_timeouts=vdp1_fstats.draw_timeouts;
        g_sm64ds_castle_profile.vdp1_late_swaps=vdp1_fstats.late_swaps;
    }
}
