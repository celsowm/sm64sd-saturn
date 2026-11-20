/* Playable local-ROM castle prototype (exterior + interior 1F). No render LOD in collision. */
#include <saturn/app.h>
#include <saturn/input.h>
#include <saturn/scene.h>
#include <saturn/skin3d.h>
#include <saturn/color.h>
#include <saturn/font.h>
#include <saturn/vdp1.h>
#include <saturn/time.h>
#include <saturn/cd_mount.h>
#include <saturn/exec.h>
#include <limits.h>
#include "sm64ds_pose.h"
#include "sm64ds_background.h"
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
#ifndef CASTLE_STAGE_ID
#define CASTLE_STAGE_ID 0u
#endif
#ifndef CASTLE_SPAWN_X
#define CASTLE_SPAWN_X 0
#define CASTLE_SPAWN_Y (100*SAT_FX16_ONE)
#define CASTLE_SPAWN_Z (256*SAT_FX16_ONE)
#define CASTLE_SPAWN_FLOOR_CEILING (512*SAT_FX16_ONE)
#define CASTLE_SPAWN_YAW 0
#define CASTLE_SPAWN_FACING 180
#define CASTLE_DEFAULT_CAM_DIST 65
#define CASTLE_CLOSE_CAM_DIST 35
#define CASTLE_BG_R 12
#define CASTLE_BG_G 20
#define CASTLE_BG_B 30
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
#define PROP_CAP (EXT_PROP_CAP + INT_PROP_CAP)
#define CAP (F+CF+BF+HF+1u+PROP_CAP+(SM64DS_VISUAL_DIAGNOSTICS && SM64DS_DIAG_WALL_FIXTURE ? 1 : 0))

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
static uint32_t keys[CAP];
static uint16_t order[CAP];
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
static uint16_t hi[HF*4],hm[HF];
static sat_vdp1_texture_t ht[HT];
static sat_scene3d_material_t hmat[HT];
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
static uint8_t warp_target_entrance=0;
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
static int spawn_yaw_default=CASTLE_SPAWN_YAW;
static int spawn_facing_default=CASTLE_SPAWN_FACING;
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
/* Debug HUD telemetry state: Y cycles 0=full, 1=compact, 2=off. */
static uint8_t hud_mode=0;
static uint8_t hud_floor_ok=0;
static int16_t hud_floor_ny_pct=100;
static int16_t hud_floor_height=0;
static uint16_t hud_trees_drawn=0,hud_signs_drawn=0,hud_support_pushed=0;

#if SM64DS_VISUAL_DIAGNOSTICS && SM64DS_DIAG_FAR_DEPTH_COUNT > 0
#if SM64DS_DIAG_GEOMETRIC_DEPTH || SM64DS_DIAG_PAIR_DEPTH
static sm64ds_painter_vertex_t painter_vertex(sat_projected_vertex_t p) {
    return (sm64ds_painter_vertex_t){p.x,p.y,p.w};
}
#endif

#if SM64DS_DIAG_SUPPORT_DEPTH
#if SM64DS_DIAG_SUPPORT_AUTO && !SM64DS_DIAG_SUPPORT_GUARD
#error "Automatic support-depth diagnostics require the scenery guard"
#endif
#if SM64DS_DIAG_SLOPED_SUPPORT && (!SM64DS_DIAG_SUPPORT_AUTO || !defined(CASTLE_SUPPORT_PLANE_LIST_AVAILABLE))
#error "Sloped support diagnostics require auto mode and regenerated support-plane metadata"
#endif
#if SM64DS_DIAG_SUPPORT_GUARD
volatile struct {
    uint32_t count;
    struct { uint16_t face,queue; sat_quad2_t projected; } blockers[8];
    uint32_t mapped,expected;
    uint32_t calls,potential,map_failed,changes,blocked;
    uint32_t profile_calls,profile_ticks_sum,profile_ticks_max,profile_ticks_last;
} g_sm64ds_support_diag;
static int32_t diagnostic_support_cache[CAP];

static int diagnostic_same_support(uint16_t q,int32_t y,uint32_t target_face) {
#if SM64DS_DIAG_SUPPORT_AUTO && defined(CASTLE_FACE_SOURCE_AVAILABLE)
    int face=diagnostic_support_cache[q];
    if(face<0 || castle_face_source[face]!=castle_face_source[target_face]) return 0;
    const uint16_t *is=&ci[(uint32_t)face*4u];
    return cv[is[0]].y==y && cv[is[1]].y==y && cv[is[2]].y==y && cv[is[3]].y==y;
#else
    (void)target_face;
    if(diagnostic_support_cache[q]!=-1) {
        int face=diagnostic_support_cache[q];
        return face>=0 && cv[ci[(uint32_t)face*4u]].y==y;
    }
    const sat_quad2_t *quad=&scene.faces.entries[q].projected;
    for(uint32_t f=SM64DS_DIAG_FAR_DEPTH_FIRST;
        f<(uint32_t)SM64DS_DIAG_FAR_DEPTH_FIRST+SM64DS_DIAG_FAR_DEPTH_COUNT && f<CF;++f) {
        const uint16_t *is=&ci[f*4u];
        int32_t fy=cv[is[0]].y;
        if(cv[is[1]].y!=fy || cv[is[2]].y!=fy || cv[is[3]].y!=fy) continue;
        unsigned k;
        for(k=0;k<4;++k) if(quad->x[k]!=cp[is[k]].x || quad->y[k]!=cp[is[k]].y) break;
        if(k==4) { diagnostic_support_cache[q]=(int32_t)f;return fy==y; }
    }
    diagnostic_support_cache[q]=-2;
    return 0;
#endif
}

#if SM64DS_DIAG_SUPPORT_AUTO && defined(CASTLE_FACE_SOURCE_AVAILABLE)
static uint16_t diagnostic_support_face_queue[CF];
/* Instance submission preserves face order. Associate each queued entry with
 * its source face only when both its four coordinates and its original
 * painter key agree; reject the entire experiment if any entry is unmapped. */
static int diagnostic_map_castle(uint16_t first,uint16_t end) {
    uint16_t cursor=first;
    for(uint32_t face=0;face<CF;++face) diagnostic_support_face_queue[face]=0xffffu;
    for(uint32_t face=0;face<CF && cursor<end;++face) {
        const uint16_t *is=&ci[face*4u];
        sat_scene3d_face_t *entry=&scene.faces.entries[cursor];
        int64_t sum=0;
        unsigned k;
        for(k=0;k<4;++k) {
            if(entry->projected.x[k]!=cp[is[k]].x || entry->projected.y[k]!=cp[is[k]].y) break;
            sum+=cp[is[k]].w;
        }
        if(k!=4) continue;
        int64_t depth=sum>0?sum>>6:0;
        if(depth>0xfffffe) depth=0xfffffe;
        uint32_t key=((255u-castle.instance.pass)<<24)|(uint32_t)depth;
        if(scene.faces.keys[cursor]!=key) continue;
        diagnostic_support_cache[cursor]=(int32_t)face;
        diagnostic_support_face_queue[face]=cursor++;
    }
    g_sm64ds_support_diag.mapped=cursor-first;
    g_sm64ds_support_diag.expected=end-first;
    return cursor==end;
}
#endif

static int diagnostic_not_near_clipped(const sat_scene3d_face_t *face) {
    if(!face->projected_safe) {
        for(unsigned k=0;k<4;++k) {
            sat_fx16_t depth;
            if(sat_scene3d_faces_depth(&scene.faces,&face->world.v[k],&depth)!=SAT_OK ||
               depth<scene.faces.near_depth+ONE/256) return 0;
        }
    }
    return 1;
}

static int diagnostic_separate_triangles(const sat_scene3d_face_t *a,
                                         const sat_scene3d_face_t *b) {
    const sat_quad2_t *qa=&a->projected,*qb=&b->projected;
    if(qa->x[2]!=qa->x[3] || qa->y[2]!=qa->y[3] ||
       qb->x[2]!=qb->x[3] || qb->y[2]!=qb->y[3]) return 0;
    sm64ds_painter_vertex_t ta[3],tb[3];
    for(unsigned k=0;k<3;++k) {
        ta[k]=(sm64ds_painter_vertex_t){qa->x[k],qa->y[k],ONE};
        tb[k]=(sm64ds_painter_vertex_t){qb->x[k],qb->y[k],ONE};
    }
    return sm64ds_painter_triangles_separated(ta,tb,2);
}

static int diagnostic_quad_outside(const sat_quad2_t *quad,
                                   int x0,int x1,int y0,int y1) {
    int lx=quad->x[0],hx=lx,ly=quad->y[0],hy=ly;
    for(unsigned k=1;k<4;++k) {
        if(quad->x[k]<lx)lx=quad->x[k];
        if(quad->x[k]>hx)hx=quad->x[k];
        if(quad->y[k]<ly)ly=quad->y[k];
        if(quad->y[k]>hy)hy=quad->y[k];
    }
    return hx<x0-2 || lx>x1+2 || hy<y0-2 || ly>y1+2;
}

/* Match the SDK's near-clipped fallback before rejecting a depth change.
 * Project the original too: a textured face can be drawn whole if its
 * corners clear the near plane. Any error remains a conservative blocker. */
static int diagnostic_clipped_outside(const sat_scene3d_face_t *face,
                                      int x0,int x1,int y0,int y1) {
    sat_quad2_t projected;
    sat_result_t result=sat_project_quad(&scene.faces.view_proj,&face->world,&projected);
    if(result==SAT_OK && !diagnostic_quad_outside(&projected,x0,x1,y0,y1)) return 0;
    if(result!=SAT_OK && result!=SAT_ERR_UNSUPPORTED) return 0;
    sat_quad3_t pieces[4];uint8_t count=0;
    if(sat_clip_quad_near(&face->world,&scene.faces.eye,&scene.faces.forward,
                          scene.faces.near_depth,pieces,&count)!=SAT_OK) return 0;
    for(uint8_t i=0;i<count;++i) {
        result=sat_project_quad(&scene.faces.view_proj,&pieces[i],&projected);
        if(result==SAT_ERR_UNSUPPORTED) continue; /* SDK skips this piece. */
        if(result!=SAT_OK || !diagnostic_quad_outside(&projected,x0,x1,y0,y1)) return 0;
    }
    return 1;
}


#endif
/* Diagnostic proof for a flat plane: when the camera and every actor
 * vertex are above the plane, a ray to the actor cannot hit that plane
 * first. This does not establish the ground's order against other scenery. */
#if SM64DS_DIAG_SLOPED_SUPPORT
#define SUPPORT_FACE_COUNT CASTLE_SUPPORT_PLANE_COUNT
#define SUPPORT_FACE_AT(i) ((uint32_t)castle_support_faces[i])
#elif SM64DS_DIAG_SUPPORT_AUTO && defined(CASTLE_FLAT_FACE_LIST_AVAILABLE)
#define SUPPORT_FACE_COUNT CASTLE_FLAT_FACE_COUNT
#define SUPPORT_FACE_AT(i) ((uint32_t)castle_flat_faces[i])
#else
#define SUPPORT_FACE_COUNT SM64DS_DIAG_FAR_DEPTH_COUNT
#define SUPPORT_FACE_AT(i) ((uint32_t)SM64DS_DIAG_FAR_DEPTH_FIRST+(i))
#endif
#if SM64DS_DIAG_SLOPED_SUPPORT
/* The minimum actor dot product depends on the normal, not the plane's
 * position. Many split faces share a normal, so reuse that exact value for
 * the duration of this call. Hash collisions simply recompute it. */
static struct {
    sat_vec3_t normal;
    int64_t minimum;
    uint8_t valid;
} support_normal_cache[64];
static sat_vec3_t support_actor_min,support_actor_max;

static int diagnostic_same_sloped_support(uint16_t q,uint32_t scan,uint32_t target) {
    int other=diagnostic_support_cache[q];
    if(other<0 || castle_face_source[other]!=castle_face_source[target]) return 0;
    const sat_vec3_t n=castle_support_normals[scan],p=cv[ci[target*4u]];
    const uint16_t *is=&ci[(uint32_t)other*4u];
    for(unsigned k=0;k<4;++k) {
        sat_vec3_t v=cv[is[k]];
        int64_t side=((int64_t)v.x-p.x)*n.x+((int64_t)v.y-p.y)*n.y+
                     ((int64_t)v.z-p.z)*n.z;
        if(side < -((int64_t)ONE*ONE/256) || side > ((int64_t)ONE*ONE/256)) return 0;
    }
    return 1;
}

static int diagnostic_above_sloped_plane(uint32_t scan,uint32_t f) {
    const sat_vec3_t n=castle_support_normals[scan],p=cv[ci[f*4u]];
    const sat_vec3_t eye=camera.eye;
    int64_t plane=(int64_t)p.x*n.x+(int64_t)p.y*n.y+(int64_t)p.z*n.z;
    int64_t side=(int64_t)eye.x*n.x+(int64_t)eye.y*n.y+(int64_t)eye.z*n.z-plane;
    if(side<=((int64_t)ONE*ONE/256)) return 0;
    /* The minimum over the actor's bounding box is a conservative lower
     * bound for every vertex. Only scan vertices when it cannot prove the
     * entire box lies above the support plane. */
    int64_t bound=(int64_t)(n.x>=0?support_actor_min.x:support_actor_max.x)*n.x+
                  (int64_t)(n.y>=0?support_actor_min.y:support_actor_max.y)*n.y+
                  (int64_t)(n.z>=0?support_actor_min.z:support_actor_max.z)*n.z;
    if(bound-plane>=((int64_t)ONE*ONE/1024)) return 1;
    unsigned slot=((uint32_t)n.x*17u+(uint32_t)n.y*31u+(uint32_t)n.z*47u)&63u;
    if(support_normal_cache[slot].valid &&
       support_normal_cache[slot].normal.x==n.x &&
       support_normal_cache[slot].normal.y==n.y &&
       support_normal_cache[slot].normal.z==n.z)
        return support_normal_cache[slot].minimum-plane>=((int64_t)ONE*ONE/1024);
    int64_t minimum=INT64_MAX;
    for(unsigned group=0;group<2;++group) {
        if(!(SM64DS_DIAG_OBJECTS&(group?8:4))) continue;
        const sat_vec3_t *vertices=group?hw:world_vertices;
        unsigned count=group?HN:N;
        for(unsigned v=0;v<count;++v) {
            side=(int64_t)vertices[v].x*n.x+(int64_t)vertices[v].y*n.y+
                 (int64_t)vertices[v].z*n.z;
            if(side<minimum) minimum=side;
        }
    }
    support_normal_cache[slot].normal=n;
    support_normal_cache[slot].minimum=minimum;
    support_normal_cache[slot].valid=1;
    return minimum-plane>=((int64_t)ONE*ONE/1024);
}

#endif
static void diagnostic_support_depth(uint16_t first,uint16_t end,
                                     uint16_t actor_first,uint16_t actor_end) {
#if SM64DS_DIAG_SUPPORT_GUARD
    /* Retain the first blockers across calls: WRAM captures can occur between
     * frames, after a per-call counter would already have been cleared. */
    g_sm64ds_support_diag.mapped=0;g_sm64ds_support_diag.expected=0;
    ++g_sm64ds_support_diag.calls;
#endif
    if(scene.faces.projected_entries || actor_first==actor_end) return;
#if SM64DS_DIAG_SLOPED_SUPPORT
    for(unsigned i=0;i<64;++i) support_normal_cache[i].valid=0;
#endif
    uint8_t group=(uint8_t)(255u-castle.instance.pass);
    uint32_t actor_max=0;int has_actor=0;
    int ax0=32767,ax1=-32768,ay0=32767,ay1=-32768;
    for(uint16_t a=actor_first;a<actor_end;++a) {
        sat_scene3d_face_t *entry=&scene.faces.entries[a];
        if(!entry->projected_safe) return;
        uint32_t key=scene.faces.keys[a];
        if((key>>24)==group) {
            uint32_t depth=key&0xffffffu;
            if(depth>actor_max)actor_max=depth;
            has_actor=1;
        }
        for(unsigned k=0;k<4;++k) {
            if(entry->projected.x[k]<ax0)ax0=entry->projected.x[k];
            if(entry->projected.x[k]>ax1)ax1=entry->projected.x[k];
            if(entry->projected.y[k]<ay0)ay0=entry->projected.y[k];
            if(entry->projected.y[k]>ay1)ay1=entry->projected.y[k];
        }
    }
    if(!has_actor) return;
    int32_t actor_lowest=INT32_MAX;
#if SM64DS_DIAG_SLOPED_SUPPORT
    support_actor_min=(sat_vec3_t){INT32_MAX,INT32_MAX,INT32_MAX};
    support_actor_max=(sat_vec3_t){INT32_MIN,INT32_MIN,INT32_MIN};
    for(unsigned group_index=0;group_index<2;++group_index) {
        if(!(SM64DS_DIAG_OBJECTS&(group_index?8:4))) continue;
        const sat_vec3_t *vertices=group_index?hw:world_vertices;
        unsigned count=group_index?HN:N;
        for(unsigned v=0;v<count;++v) {
            sat_vec3_t p=vertices[v];
            if(p.x<support_actor_min.x)support_actor_min.x=p.x;
            if(p.y<support_actor_min.y)support_actor_min.y=p.y;
            if(p.z<support_actor_min.z)support_actor_min.z=p.z;
            if(p.x>support_actor_max.x)support_actor_max.x=p.x;
            if(p.y>support_actor_max.y)support_actor_max.y=p.y;
            if(p.z>support_actor_max.z)support_actor_max.z=p.z;
        }
    }
    actor_lowest=support_actor_min.y;
#else
    if(SM64DS_DIAG_OBJECTS&4) for(unsigned v=0;v<N;++v)
        if(world_vertices[v].y<actor_lowest) actor_lowest=world_vertices[v].y;
    if(SM64DS_DIAG_OBJECTS&8) for(unsigned v=0;v<HN;++v)
        if(hw[v].y<actor_lowest) actor_lowest=hw[v].y;
#endif

    /* Avoid mapping the entire castle queue if no flat projected face can
     * both overlap the actor and sort after it. */
    int possible=0;
    for(uint32_t scan=0;scan<SUPPORT_FACE_COUNT;++scan) {
        uint32_t f=SUPPORT_FACE_AT(scan);if(f>=CF) continue;
        const uint16_t *is=&ci[f*4u];int32_t y=cv[is[0]].y;
        int flat=cv[is[1]].y==y && cv[is[2]].y==y && cv[is[3]].y==y;
        if(flat && (camera.eye.y<=y || actor_lowest<y)) continue;
#if !SM64DS_DIAG_SLOPED_SUPPORT
        if(!flat) continue;
#endif
        int x0=cp[is[0]].x,x1=x0,y0=cp[is[0]].y,y1=y0;int64_t sum=0;
        for(unsigned k=0;k<4;++k) {
            if(cp[is[k]].x<x0)x0=cp[is[k]].x;
            if(cp[is[k]].x>x1)x1=cp[is[k]].x;
            if(cp[is[k]].y<y0)y0=cp[is[k]].y;
            if(cp[is[k]].y>y1)y1=cp[is[k]].y;
            sum+=cp[is[k]].w;
        }
        if(x1<ax0-1 || x0>ax1+1 || y1<ay0-1 || y0>ay1+1) continue;
        if(sum<0 || (uint64_t)(sum/64)<actor_max) {
#if SM64DS_DIAG_SLOPED_SUPPORT
            if(!flat && !diagnostic_above_sloped_plane(scan,f)) continue;
#endif
            possible=1;break;
        }
    }
    if(!possible) return;
#if SM64DS_DIAG_SUPPORT_GUARD
    ++g_sm64ds_support_diag.potential;
    for(uint16_t q=0;q<actor_first;++q) {
        diagnostic_support_cache[q]=-1;
    }
#if SM64DS_DIAG_SUPPORT_AUTO && defined(CASTLE_FACE_SOURCE_AVAILABLE)
    if(!diagnostic_map_castle(first,end)) { ++g_sm64ds_support_diag.map_failed;return; }
#elif SM64DS_DIAG_SUPPORT_AUTO
    return; /* Regenerate castle_scene with source metadata first. */
#endif
    sm64ds_painter_bucket_plan_t bucket;
    if(!sm64ds_painter_bucket_plan(scene.faces.keys,scene.faces.count,group,&bucket)) return;
#endif
    for(uint32_t scan=0;scan<SUPPORT_FACE_COUNT;++scan) {
        uint32_t f=SUPPORT_FACE_AT(scan);if(f>=CF) continue;
#if SM64DS_DIAG_SUPPORT_AUTO && defined(CASTLE_FACE_SOURCE_AVAILABLE)
        /* This face cannot need a key change if it is absent from the queue
         * or already sorts at least as far away as every actor face. */
        uint16_t mapped=diagnostic_support_face_queue[f];
        if(mapped==0xffffu || (scene.faces.keys[mapped]&0xffffffu)>=actor_max) continue;
#endif
        const uint16_t *is=&ci[f*4u];
        int32_t y=cv[is[0]].y;
        int flat=cv[is[1]].y==y && cv[is[2]].y==y && cv[is[3]].y==y;
        if(flat && camera.eye.y<=y) continue;
#if !SM64DS_DIAG_SLOPED_SUPPORT
        if(!flat) continue;
#endif
        int x0=cp[is[0]].x,x1=x0,y0=cp[is[0]].y,y1=y0;
        for(unsigned k=1;k<4;++k) {
            if(cp[is[k]].x<x0)x0=cp[is[k]].x;
            if(cp[is[k]].x>x1)x1=cp[is[k]].x;
            if(cp[is[k]].y<y0)y0=cp[is[k]].y;
            if(cp[is[k]].y>y1)y1=cp[is[k]].y;
        }
        if(x1<ax0-1 || x0>ax1+1 || y1<ay0-1 || y0>ay1+1) continue;
        int above=flat && actor_lowest>=y;
#if SM64DS_DIAG_SLOPED_SUPPORT
        if(!flat) above=diagnostic_above_sloped_plane(scan,f);
#endif
        if(!above) continue;
#if SM64DS_DIAG_SUPPORT_AUTO && defined(CASTLE_FACE_SOURCE_AVAILABLE)
        for(uint16_t q=mapped;q<(uint16_t)(mapped+1u);++q) {
#else
        for(uint16_t q=first;q<end;++q) {
#endif
            sat_scene3d_face_t *entry=&scene.faces.entries[q];
#if SM64DS_DIAG_SLOPED_SUPPORT
            if(!entry->projected_safe && !diagnostic_not_near_clipped(entry)) continue;
#else
            if(!entry->projected_safe) continue;
#endif
            unsigned k;
            for(k=0;k<4;++k)
                if(entry->projected.x[k]!=cp[is[k]].x || entry->projected.y[k]!=cp[is[k]].y) break;
            if(k!=4) continue;
            uint32_t old=scene.faces.keys[q],depth=old&0xffffffu;
            /* Castle is submitted before the actor, and the SDK preserves
             * submission order within a bucket. */
            if(actor_max>depth) depth=actor_max;
#if SM64DS_DIAG_SUPPORT_GUARD
            if(above && depth>(old&0xffffffu)) {
                /* Keep the original group minimum and maximum in place, so
                 * the SDK computes the same bucket boundaries at flush. */
                uint32_t old_depth=old&0xffffffu;
                if(old_depth==bucket.low || depth>bucket.high) break;
                uint32_t old_bucket=(old_depth-bucket.low)>>bucket.shift;
                uint32_t new_bucket=(depth-bucket.low)>>bucket.shift;
                int x0=entry->projected.x[0],x1=x0,y0=entry->projected.y[0],y1=y0;
                for(k=1;k<4;++k) {
                    if(entry->projected.x[k]<x0)x0=entry->projected.x[k];
                    if(entry->projected.x[k]>x1)x1=entry->projected.x[k];
                    if(entry->projected.y[k]<y0)y0=entry->projected.y[k];
                    if(entry->projected.y[k]>y1)y1=entry->projected.y[k];
                }
                /* Only intersections in the framebuffer can change pixels.
                 * Keep a two-pixel margin for rasterization at the edge. */
                if(x0< -2)x0=-2;
                if(x1>321)x1=321;
                if(y0< -2)y0=-2;
                if(y1>225)y1=225;
                for(uint16_t other=0;other<actor_first;++other) {
                    if(other==q || (scene.faces.keys[other]>>24)!=(old>>24)) continue;
                    uint32_t od=scene.faces.keys[other]&0xffffffu;
                    uint32_t ob=(od-bucket.low)>>bucket.shift;
                    int before_old=old_bucket>ob || (old_bucket==ob && q<other);
                    int before_new=new_bucket>ob || (new_bucket==ob && q<other);
                    if(before_old==before_new) continue;
                    if(flat && other>=first && other<end && diagnostic_same_support(other,y,f)) continue;
#if SM64DS_DIAG_SLOPED_SUPPORT
                    if(!flat && other>=first && other<end && diagnostic_same_sloped_support(other,scan,f)) continue;
#endif
                    sat_scene3d_face_t *other_face=&scene.faces.entries[other];
                    if(!diagnostic_not_near_clipped(other_face)) {
                        if(diagnostic_clipped_outside(other_face,x0,x1,y0,y1)) continue;
                        if(g_sm64ds_support_diag.count<8) {
                            uint32_t i=g_sm64ds_support_diag.count++;
                            g_sm64ds_support_diag.blockers[i].face=(uint16_t)f;
                            g_sm64ds_support_diag.blockers[i].queue=other;
                            g_sm64ds_support_diag.blockers[i].projected=other_face->projected;
                        }
                        ++g_sm64ds_support_diag.blocked;above=0;break;
                    }
                    sat_quad2_t *quad=&other_face->projected;
                    int ox0=quad->x[0],ox1=ox0,oy0=quad->y[0],oy1=oy0;
                    for(k=1;k<4;++k) {
                        if(quad->x[k]<ox0)ox0=quad->x[k];
                        if(quad->x[k]>ox1)ox1=quad->x[k];
                        if(quad->y[k]<oy0)oy0=quad->y[k];
                        if(quad->y[k]>oy1)oy1=quad->y[k];
                    }
                    if(ox1<x0-1 || ox0>x1+1 || oy1<y0-1 || oy0>y1+1) continue;
                    if(diagnostic_separate_triangles(entry,other_face)) continue;
                    if(g_sm64ds_support_diag.count<8) {
                        uint32_t i=g_sm64ds_support_diag.count++;
                        g_sm64ds_support_diag.blockers[i].face=(uint16_t)f;
                        g_sm64ds_support_diag.blockers[i].queue=other;
                        g_sm64ds_support_diag.blockers[i].projected=*quad;
                    }
                    ++g_sm64ds_support_diag.blocked;above=0;break;
                }
            }
#endif
            if(above) {
#if SM64DS_DIAG_SUPPORT_GUARD
                if(depth!=(old&0xffffffu)) ++g_sm64ds_support_diag.changes;
#endif
                scene.faces.keys[q]=(old&0xff000000u)|depth;
            }
            break;
        }
    }
}
#elif SM64DS_DIAG_PAIR_DEPTH
static int diagnostic_quads_overlap(const sat_quad2_t *a,const sat_quad2_t *b) {
    /* VDP1 can cover the same pixel on shared or immediately adjacent
     * projected vertices even when the ideal triangles have zero area in
     * common. Preserve their existing ordering as well. */
    for(unsigned i=0;i<4;++i) for(unsigned j=0;j<4;++j) {
        int dx=a->x[i]-b->x[j],dy=a->y[i]-b->y[j];
        if(dx>=-1 && dx<=1 && dy>=-1 && dy<=1) return 1;
    }
    for(unsigned i=0;i<2;++i) {
        unsigned ac[3]={0,i?2:1,i?3:2};
        sm64ds_painter_vertex_t at[3];
        for(unsigned k=0;k<3;++k) at[k]=(sm64ds_painter_vertex_t){a->x[ac[k]],a->y[ac[k]],ONE};
        int64_t area=(int64_t)(at[1].x-at[0].x)*(at[2].y-at[0].y)-
            (int64_t)(at[1].y-at[0].y)*(at[2].x-at[0].x);
        if(!area) continue;
        for(unsigned j=0;j<2;++j) {
            unsigned bc[3]={0,j?2:1,j?3:2};
            sm64ds_painter_vertex_t bt[3];
            for(unsigned k=0;k<3;++k) bt[k]=(sm64ds_painter_vertex_t){b->x[bc[k]],b->y[bc[k]],ONE};
            area=(int64_t)(bt[1].x-bt[0].x)*(bt[2].y-bt[0].y)-
                (int64_t)(bt[1].y-bt[0].y)*(bt[2].x-bt[0].x);
            if(!area) continue;
            if(sm64ds_painter_compare_triangles(at,bt)!=SM64DS_PAINTER_DISJOINT) return 1;
        }
    }
    return 0;
}

/* Test pairwise body/ground ordering without claiming correctness against
 * walls or other actor faces. Only selected ground triangles are examined. */
static void diagnostic_pair_depth(uint16_t ground_first,uint16_t ground_end,
                                  uint16_t actor_first,uint16_t actor_end,uint16_t actor_head_end) {
    if(scene.faces.projected_entries) return;
    /* The experiment is bounded so it does not allocate a variable-size
     * stack array from a user-supplied diagnostic setting. */
    if(SM64DS_DIAG_FAR_DEPTH_COUNT>32) return;
    struct candidate { sm64ds_painter_vertex_t p[3];uint16_t queue;int x0,x1,y0,y1; } ground[32];
    unsigned ground_count=0;
    for(uint32_t g=SM64DS_DIAG_FAR_DEPTH_FIRST;
        g<(uint32_t)SM64DS_DIAG_FAR_DEPTH_FIRST+SM64DS_DIAG_FAR_DEPTH_COUNT && g<CF;++g) {
        const uint16_t *gi=&ci[g*4u];
        if(gi[2]!=gi[3]) continue;
        for(uint16_t q=ground_first;q<ground_end;++q) {
            sat_scene3d_face_t *entry=&scene.faces.entries[q];
            if(!entry->projected_safe) continue;
            unsigned k;
            for(k=0;k<4;++k)
                if(entry->projected.x[k]!=cp[gi[k]].x || entry->projected.y[k]!=cp[gi[k]].y) break;
            if(k!=4) continue;
            struct candidate *c=&ground[ground_count++];c->queue=q;
            for(k=0;k<3;++k) c->p[k]=painter_vertex(cp[gi[k]]);
            c->x0=c->x1=c->p[0].x;c->y0=c->y1=c->p[0].y;
            for(k=1;k<3;++k) {
                if(c->p[k].x<c->x0)c->x0=c->p[k].x;
                if(c->p[k].x>c->x1)c->x1=c->p[k].x;
                if(c->p[k].y<c->y0)c->y0=c->p[k].y;
                if(c->p[k].y>c->y1)c->y1=c->p[k].y;
            }
            break;
        }
    }
    uint16_t cursor=actor_first;
    for(uint16_t f=0;f<F;++f) {
        if(cursor==actor_end) break;
        const uint16_t *ai=&indices[(uint32_t)f*4];
        sat_scene3d_face_t *entry=&scene.faces.entries[cursor];
        unsigned k;
        for(k=0;k<4;++k)
            if(entry->projected.x[k]!=projected[ai[k]].x || entry->projected.y[k]!=projected[ai[k]].y) break;
        if(k!=4) continue;
        uint16_t aq=cursor++;
        if(!entry->projected_safe) continue;
        uint32_t proposed=scene.faces.keys[aq]&0xffffffu;
        int valid=1,changed=0;
        for(unsigned g=0;g<ground_count && valid;++g) {
            struct candidate *c=&ground[g];uint16_t gq=c->queue;
            if((scene.faces.keys[gq]>>24)!=(scene.faces.keys[aq]>>24)) continue;
            uint32_t ground_depth=scene.faces.keys[gq]&0xffffffu;
            uint32_t actor_depth=scene.faces.keys[aq]&0xffffffu;
            /* This actor face already sorts sufficiently after this ground;
             * moving it even nearer cannot cross this ground's key. */
            if(actor_depth<ground_depth && ground_depth-actor_depth>=16384u) continue;
            for(unsigned tri=0;tri<2;++tri) {
                unsigned corners[3]={0,tri?2:1,tri?3:2};
                sm64ds_painter_vertex_t body[3];
                for(unsigned k=0;k<3;++k) body[k]=painter_vertex(projected[ai[corners[k]]]);
                int x0=body[0].x,x1=x0,y0=body[0].y,y1=y0;
                for(unsigned k=1;k<3;++k) {
                    if(body[k].x<x0)x0=body[k].x;
                    if(body[k].x>x1)x1=body[k].x;
                    if(body[k].y<y0)y0=body[k].y;
                    if(body[k].y>y1)y1=body[k].y;
                }
                if(x1<c->x0 || x0>c->x1 || y1<c->y0 || y0>c->y1) continue;
                int64_t area=(int64_t)(body[1].x-body[0].x)*(body[2].y-body[0].y)-
                    (int64_t)(body[1].y-body[0].y)*(body[2].x-body[0].x);
                if(!area) continue;
                sm64ds_painter_relation_t relation=sm64ds_painter_compare_triangles(c->p,body);
                if(relation==SM64DS_PAINTER_DISJOINT) continue;
                if(relation!=SM64DS_PAINTER_A_BEHIND) { valid=0;break; }
                /* Wider than the painter's typical depth bucket; this is a
                 * diagnostic bias, not a proof about intervening geometry. */
                uint32_t target=ground_depth>16384u?ground_depth-16384u:0;
                if(target<proposed) { proposed=target;changed=1; }
            }
        }
        if(valid && changed) {
            /* Preserve the existing ordering against overlapping body/head
             * queue entries. Bounding boxes are deliberately conservative. */
            int x0=entry->projected.x[0],x1=x0,y0=entry->projected.y[0],y1=y0;
            for(unsigned j=1;j<4;++j) {
                if(entry->projected.x[j]<x0)x0=entry->projected.x[j];
                if(entry->projected.x[j]>x1)x1=entry->projected.x[j];
                if(entry->projected.y[j]<y0)y0=entry->projected.y[j];
                if(entry->projected.y[j]>y1)y1=entry->projected.y[j];
            }
            uint32_t old=scene.faces.keys[aq]&0xffffffu;
            for(uint16_t q=actor_first;q<actor_head_end;++q) {
                if(q==aq || (scene.faces.keys[q]>>24)!=(scene.faces.keys[aq]>>24)) continue;
                uint32_t other=scene.faces.keys[q]&0xffffffu;
                /* The SDK's bucket sort can reorder keys that are close
                 * without the exact keys crossing. Include a conservative
                 * margin while this experiment lacks its bucket metadata. */
                uint32_t lower=proposed>32768u?proposed-32768u:0;
                uint32_t upper=old<0xfffffeu-32768u?old+32768u:0xfffffeu;
                if(other<lower || other>upper) continue;
                sat_quad2_t *quad=&scene.faces.entries[q].projected;
                int ox0=quad->x[0],ox1=ox0,oy0=quad->y[0],oy1=oy0;
                for(unsigned j=1;j<4;++j) {
                    if(quad->x[j]<ox0)ox0=quad->x[j];
                    if(quad->x[j]>ox1)ox1=quad->x[j];
                    if(quad->y[j]<oy0)oy0=quad->y[j];
                    if(quad->y[j]>oy1)oy1=quad->y[j];
                }
                if(ox1>=x0-1 && ox0<=x1+1 && oy1>=y0-1 && oy0<=y1+1 &&
                   diagnostic_quads_overlap(&entry->projected,quad)) { valid=0;break; }
            }
            if(valid) scene.faces.keys[aq]=(scene.faces.keys[aq]&0xff000000u)|proposed;
        }
    }
}
#elif SM64DS_DIAG_GEOMETRIC_DEPTH
/* Conservative diagnostic prototype: compare the ground triangle against
 * both triangles of every actor face whose screen bounds overlap it.  Using
 * even back-facing actor triangles may reject a safe adjustment. */
static int diagnostic_actor_depth(const sm64ds_painter_vertex_t ground[3],
        const sat_projected_vertex_t *p,const uint16_t *idx,uint16_t count,
        uint32_t *required_depth,int *overlap) {
    int gx0=ground[0].x,gx1=gx0,gy0=ground[0].y,gy1=gy0;
    for(unsigned k=1;k<3;++k) {
        if(ground[k].x<gx0) gx0=ground[k].x;
        if(ground[k].x>gx1) gx1=ground[k].x;
        if(ground[k].y<gy0) gy0=ground[k].y;
        if(ground[k].y>gy1) gy1=ground[k].y;
    }
    for(uint16_t f=0;f<count;++f) {
        const uint16_t *is=&idx[(uint32_t)f*4];
        int64_t sum=0;
        for(unsigned k=0;k<4;++k) sum+=p[is[k]].w;
        if(sum<=0) continue;
        for(unsigned tri=0;tri<2;++tri) {
            unsigned corners[3]={0,tri?2:1,tri?3:2};
            sm64ds_painter_vertex_t b[3];
            for(unsigned k=0;k<3;++k) b[k]=painter_vertex(p[is[corners[k]]]);
            int minx=b[0].x,maxx=minx,miny=b[0].y,maxy=miny;
            for(unsigned k=1;k<3;++k) {
                if(b[k].x<minx) minx=b[k].x;
                if(b[k].x>maxx) maxx=b[k].x;
                if(b[k].y<miny) miny=b[k].y;
                if(b[k].y>maxy) maxy=b[k].y;
            }
            if(maxx<gx0 || minx>gx1 || maxy<gy0 || miny>gy1) continue;
            int64_t area=(int64_t)(b[1].x-b[0].x)*(b[2].y-b[0].y)-
                         (int64_t)(b[1].y-b[0].y)*(b[2].x-b[0].x);
            if(!area) continue;
            sm64ds_painter_relation_t relation=sm64ds_painter_compare_triangles(ground,b);
            if(relation==SM64DS_PAINTER_DISJOINT) continue;
            if(relation!=SM64DS_PAINTER_A_BEHIND) return 0;
            *overlap=1;
            uint32_t depth=(uint32_t)(sum/64);
            if(depth>=0xfffffeu) return 0;
            if(depth+1>*required_depth) *required_depth=depth+1;
        }
    }
    return 1;
}

static void diagnostic_geometric_depth(uint16_t first,uint16_t end) {
    if(scene.faces.projected_entries) return;
    for(uint32_t face=SM64DS_DIAG_FAR_DEPTH_FIRST;
        face<(uint32_t)SM64DS_DIAG_FAR_DEPTH_FIRST+SM64DS_DIAG_FAR_DEPTH_COUNT && face<CF;
        ++face) {
        const uint16_t *is=&ci[face*4u];
        if(is[2]!=is[3]) continue;
        sm64ds_painter_vertex_t ground[3];
        for(unsigned k=0;k<3;++k) ground[k]=painter_vertex(cp[is[k]]);
        uint32_t depth=0;int overlap=0;
        if((SM64DS_DIAG_OBJECTS&4) && !diagnostic_actor_depth(ground,projected,indices,F,&depth,&overlap)) continue;
        if((SM64DS_DIAG_OBJECTS&8) && !diagnostic_actor_depth(ground,hp,hi,HF,&depth,&overlap)) continue;
        if(!overlap) continue;
        for(uint16_t q=first;q<end;++q) {
            sat_scene3d_face_t *entry=&scene.faces.entries[q];
            if(!entry->projected_safe) continue;
            unsigned k;
            for(k=0;k<4;++k)
                if(entry->projected.x[k]!=cp[is[k]].x || entry->projected.y[k]!=cp[is[k]].y) break;
            if(k==4) {
                if((scene.faces.keys[q]&0xffffffu)<depth)
                    scene.faces.keys[q]=(scene.faces.keys[q]&0xff000000u)|depth;
                break;
            }
        }
    }
}
#else
/* Experiment only: use the farthest corner as a face's painter depth.  It
 * is intentionally restricted to selected render-face IDs; this does not
 * establish that a face is behind an actor over their screen intersection. */
static void diagnostic_far_depth(uint16_t first,uint16_t end) {
    if(scene.faces.projected_entries) return;
    for(uint32_t face=SM64DS_DIAG_FAR_DEPTH_FIRST;
        face<(uint32_t)SM64DS_DIAG_FAR_DEPTH_FIRST+SM64DS_DIAG_FAR_DEPTH_COUNT && face<CF;
        ++face) {
        const uint16_t *index=&ci[face*4u];
        int32_t depth=0;
        for(unsigned c=0;c<4;++c) if(cp[index[c]].w>depth) depth=cp[index[c]].w;
        uint32_t key_depth=(uint32_t)depth/16u;
        if(key_depth>0xfffffeu) key_depth=0xfffffeu;
        for(uint16_t q=first;q<end;++q) {
            sat_scene3d_face_t *entry=&scene.faces.entries[q];
            if(!entry->projected_safe) continue;
            unsigned c;
            for(c=0;c<4;++c)
                if(entry->projected.x[c]!=cp[index[c]].x || entry->projected.y[c]!=cp[index[c]].y) break;
            if(c==4) {
                scene.faces.keys[q]=(scene.faces.keys[q]&0xff000000u)|key_depth;
                break;
            }
        }
    }
}
#endif
#endif

/* Stable debugger telemetry: all values are captured from real frames. */
volatile struct {
    uint32_t magic,frames,ticks,jumps,landings,wall_hits,resets;
    int32_t x,y,z,velocity_y,camera_x,camera_y,camera_z;
    int32_t target_x,target_y,target_z;
    uint32_t grounded,clip,commands,skipped,faces,paused;
    uint32_t culled,clipped,fallback;
    uint32_t sky_clip_candidates,castle_clip_candidates,body_clip_candidates,head_clip_candidates;
    uint32_t texture_arena_initial,texture_arena_remaining,texture_estimate;
    int32_t requested_yaw,actual_camera_yaw,camera_clearance;
    int32_t mario_facing,camera_fov_y;
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
static void reset(void) {
    sm64ds_player_reset(&player);
    yaw=spawn_yaw_default;camera_yaw=spawn_yaw_default;camera_choice=0;
    facing=spawn_facing_default;anim_time=0;
#ifdef CASTLE_ROOM_CULLING
    current_room=0;visible_room_mask=1u;
#endif
}
static sat_vec3_t camera_candidate(int angle,int32_t distance) {
    int32_t s=sat_sin_deg(angle*ONE),c=sat_cos_deg(angle*ONE);
    return (sat_vec3_t){camera.target.x+sat_fx16_mul(s,distance),
        camera.target.y+distance*30/65,camera.target.z+sat_fx16_mul(c,distance)};
}
static void update_camera(void) {
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
    int32_t distance=(close_camera?CASTLE_CLOSE_CAM_DIST:CASTLE_DEFAULT_CAM_DIST)*ONE;
#endif
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
    if (!SM64DS_EXP_FAR_CULL) return 0;
    const sat_aabb3_t *b=&castle_chunk_bounds[c];
    int32_t dx=(camera.eye.x>b->center.x?camera.eye.x-b->center.x:b->center.x-camera.eye.x)-b->half.x;
    int32_t dz=(camera.eye.z>b->center.z?camera.eye.z-b->center.z:b->center.z-camera.eye.z)-b->half.z;
    if (dx<0) dx=0;
    if (dz<0) dz=0;
    dx>>=16; dz>>=16;
    return dx*dx+dz*dz>SM64DS_EXP_FAR_CULL*SM64DS_EXP_FAR_CULL;
}
#endif

#if SM64DS_VDP2_SKY
/* The sky is a cylindrical panorama (sky_panorama.h) on NBG0, behind the
 * sprite layer, instead of a camera-following VDP1 mesh: the mesh's huge
 * faces all took the flush's clipping fallback, about a third of a frame.
 * The scroll follows the camera's yaw and pitch, and is written in the
 * VBlank that swaps in the list it was computed for. */
#define SKY_PALETTE_BANK 3u
#define SKY_BAND_BYTES ((uint32_t)SKY_PANORAMA_WIDTH*SKY_PANORAMA_BAND_ROWS)
#define VDP2_REG16(offset) (*(volatile uint16_t*)(0x25F80000u+(offset)))
static uint8_t sky_band[SKY_BAND_BYTES] __attribute__((section(".wram_l"),aligned(4)));
static int32_t sky_half_w,sky_half_h;     /* screen half size in bitmap pixels, 16.16 */
typedef struct { uint32_t serial; int32_t x,y; } sky_scroll_t;
static volatile sky_scroll_t sky_pending[4];

static uint8_t sky_pixel(void *user,uint16_t x,uint16_t y) {
    (void)user;
    int32_t row=(int32_t)y-(int32_t)SKY_PANORAMA_BAND_FIRST;
    if (row<0) row=0;
    if (row>=(int32_t)SKY_PANORAMA_BAND_ROWS) row=(int32_t)SKY_PANORAMA_BAND_ROWS-1;
    return sky_band[(uint32_t)row*SKY_PANORAMA_WIDTH+x];
}

static uint32_t sky_isqrt64(uint64_t v) {
    uint64_t root=0,bit=(uint64_t)1<<62;
    while (bit>v) bit>>=2;
    while (bit) {
        if (v>=root+bit) { v-=root+bit; root=(root>>1)+bit; }
        else root>>=1;
        bit>>=2;
    }
    return (uint32_t)root;
}

/* Top-left bitmap dot (16.16) for the current camera. Column u looks along
 * azimuth -2*pi*u/width, so screen x and bitmap x grow together; row v looks
 * at tan(elevation) = (horizon - v) / focal. */
static void sky_scroll_for_camera(int32_t *out_x,int32_t *out_y) {
    const int32_t fx=camera.target.x-camera.eye.x;
    const int32_t fy=camera.target.y-camera.eye.y;
    const int32_t fz=camera.target.z-camera.eye.z;
    const uint16_t theta=sat_atan2_16(fx,fz);
    const int32_t column=(int32_t)((uint32_t)(uint16_t)(0u-theta)*SKY_PANORAMA_WIDTH);
    *out_x=(column-sky_half_w)&(int32_t)(SKY_PANORAMA_WIDTH*ONE-1);
    const uint32_t flat=sky_isqrt64((uint64_t)((int64_t)fx*fx+(int64_t)fz*fz));
    int64_t tan_pitch=flat?((int64_t)fy*ONE)/(int64_t)flat:(fy>0?4*ONE:-4*ONE);
    if (tan_pitch>4*ONE) tan_pitch=4*ONE;
    if (tan_pitch<-4*ONE) tan_pitch=-4*ONE;
    *out_y=(int32_t)((int64_t)SKY_PANORAMA_HORIZON_ROW*ONE-
                     ((int64_t)SKY_PANORAMA_FOCAL_FX16*tan_pitch)/ONE)-sky_half_h;
}

/* VBlank of the swap that shows list `serial`: NBG0 scroll registers
 * (SCXIN0/SCXDN0/SCYIN0/SCYDN0, 8 fractional bits) with plain CPU writes. */
static void sky_swap_handler(uint32_t serial,void *user) {
    (void)user;
    const sky_scroll_t *s=(const sky_scroll_t*)&sky_pending[serial&3u];
    if (s->serial!=serial) return;
    VDP2_REG16(0x070)=(uint16_t)(((uint32_t)s->x>>16)&0x07FFu);
    VDP2_REG16(0x072)=(uint16_t)((uint32_t)s->x&0xFF00u);
    VDP2_REG16(0x074)=(uint16_t)(((uint32_t)s->y>>16)&0x07FFu);
    VDP2_REG16(0x076)=(uint16_t)((uint32_t)s->y&0xFF00u);
}

/* Called once per frame before sat_end_frame: the scroll for the list that
 * call will submit. The layer manager keeps the same value, so a
 * sat_vdp2_layers_commit (intro fades) does not move the sky back. */
static void sky_update(void) {
    int32_t x,y;
    sky_scroll_for_camera(&x,&y);
    const uint32_t serial=sat_vdp1_list_serial()+1u;
    volatile sky_scroll_t *s=&sky_pending[serial&3u];
    s->serial=0u;
    s->x=x;
    s->y=y;
    s->serial=serial;
    SAT_PANIC_IF_ERROR(sat_vdp2_layer_set_scroll(SAT_VDP2_NBG0,x,y));
}

static void sky_init(void) {
    uint32_t bytes=0;
    SAT_PANIC_IF_ERROR(sat_lz_decode(sky_panorama_lz,SKY_PANORAMA_LZ_BYTES,
                                     sky_band,SKY_BAND_BYTES,&bytes));
    if (bytes!=SKY_BAND_BYTES) SAT_PANIC_IF_ERROR(SAT_ERR_IO);
    SAT_PANIC_IF_ERROR(sat_vdp2_palette_upload(sky_panorama_palette,256u,
                                               (uint16_t)(SKY_PALETTE_BANK*256u)));
    uint16_t row_words[SKY_PANORAMA_WIDTH/2u];
    SAT_PANIC_IF_ERROR(sat_vdp2_bitmap_upload_indexed8(
        0u,SKY_PANORAMA_WIDTH,SKY_PANORAMA_HEIGHT,sky_pixel,0,0,
        row_words,SKY_PANORAMA_WIDTH/2u));
    sat_vdp2_layer_config_t cfg;
    sat_vdp2_layer_config_default(SAT_VDP2_NBG0,&cfg);
    cfg.bitmap=1u;
    cfg.color_mode=SAT_VDP2_COLOR_MODE_256;
    cfg.bitmap_size=SKY_PANORAMA_HEIGHT==512u?SAT_VDP2_BITMAP_512X512:SAT_VDP2_BITMAP_512X256;
    cfg.priority=1u;            /* behind the sprite layer */
    cfg.transparent=0u;
    cfg.palette=SKY_PALETTE_BANK;
    cfg.plane_address[0]=0u;
    SAT_PANIC_IF_ERROR(sat_vdp2_layer_configure(&cfg));
    /* Screen focal length (224/2) / tan(fov_y/2) over the bitmap's
     * width/(2*pi): one bitmap dot then spans the screen pixels one radian
     * of azimuth does. */
    const sat_angle16_t half_fov=(sat_angle16_t)(((int64_t)camera.fov_y*32768)/(180*ONE)/2);
    const int64_t screen_focal=((int64_t)112*sat_cos16(half_fov)*ONE)/sat_sin16(half_fov);
    const uint32_t zoom=(uint32_t)((screen_focal*ONE)/SKY_PANORAMA_FOCAL_FX16);
    SAT_PANIC_IF_ERROR(sat_vdp2_layer_set_zoom(SAT_VDP2_NBG0,zoom,zoom));
    sky_half_w=(int32_t)(((int64_t)160*ONE*ONE)/zoom);
    sky_half_h=(int32_t)(((int64_t)112*ONE*ONE)/zoom);
    int32_t x,y;
    sky_scroll_for_camera(&x,&y);
    SAT_PANIC_IF_ERROR(sat_vdp2_layer_set_scroll(SAT_VDP2_NBG0,x,y));
    SAT_PANIC_IF_ERROR(sat_vdp1_set_erase_transparent());
    SAT_PANIC_IF_ERROR(sat_vdp2_layers_commit());
    SAT_PANIC_IF_ERROR(sat_vdp1_set_swap_handler(sky_swap_handler,0));
}

static void sky_shutdown(void) {
    (void)sat_vdp1_set_swap_handler(0,0);
    (void)sat_vdp2_layer_release(SAT_VDP2_NBG0);
}
#endif

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

#ifdef CASTLE_PROPS_AVAILABLE
static void submit_castle_props(void) {
    hud_trees_drawn=0;hud_signs_drawn=0;
    sat_vec3_t fwd={camera.target.x-camera.eye.x,0,camera.target.z-camera.eye.z};
    sat_vec3_normalize(&fwd,&fwd);
    if (!fwd.x && !fwd.z) return;
    sat_vec3_t right={-fwd.z,0,fwd.x};
    int32_t lx=sat_fx16_mul(right.x,CASTLE_TREE_LEFT),lz=sat_fx16_mul(right.z,CASTLE_TREE_LEFT);
    int32_t rx=sat_fx16_mul(right.x,CASTLE_TREE_RIGHT),rz=sat_fx16_mul(right.z,CASTLE_TREE_RIGHT);
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
}
#endif

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

#if !SM64DS_VISUAL_DIAGNOSTICS || SM64DS_DIAG_SHOW_UI
typedef struct hud_buf {
    char data[48];
    uint8_t len;
} hud_buf_t;

static void hud_put_str(hud_buf_t *b,const char *s) {
    while (*s && b->len<40u) b->data[b->len++]=*s++;
    b->data[b->len]='\0';
}
static void hud_put_u32(hud_buf_t *b,uint32_t v) {
    char tmp[12];unsigned n=0;
    do { tmp[n++]=(char)('0'+(v%10u));v/=10u; } while (v);
    while (n && b->len<40u) b->data[b->len++]=tmp[--n];
    b->data[b->len]='\0';
}
static void hud_put_i32(hud_buf_t *b,int32_t v) {
    if (v<0) {
        if (b->len<40u) b->data[b->len++]='-';
        hud_put_u32(b,(uint32_t)(-(int64_t)v));
    } else hud_put_u32(b,(uint32_t)v);
}
static void hud_draw_box(int16_t x,int16_t y,uint16_t w,uint16_t h) {
    sat_polygon_cmd_t cmd={
        .x={(int16_t)(x-160),(int16_t)(x+(int16_t)w-160),
            (int16_t)(x+(int16_t)w-160),(int16_t)(x-160)},
        .y={(int16_t)(y-112),(int16_t)(y-112),
            (int16_t)(y+(int16_t)h-112),(int16_t)(y+(int16_t)h-112)},
        .color=SAT_RGB555(0,0,0),
        .flags=SAT_SPRITE_FLAG_HALF_TRANSPARENT
    };
    SAT_PANIC_IF_ERROR(sat_vdp1_draw_polygon(&cmd));
}
static void hud_draw_text(int x,int y,const char *text) {
    char run[44];
    int col=0;
    while (text[col]!='\0') {
        while (text[col]==' ') ++col;
        if (text[col]=='\0') break;
        int start=col,n=0;
        while (text[col]!='\0' && text[col]!=' ' && n<(int)(sizeof(run)-1))
            run[n++]=text[col++];
        run[n]='\0';
        if (x+start*8>=320) break;
        SAT_PANIC_IF_ERROR(sat_ascii_font_draw_text_screen_indexed8(
            &font,run,x+start*8,y,8,3,0));
    }
}
static void draw_debug_hud(const sat_scene_stats_t *stats,uint32_t fps,
                           uint32_t avg_ms,uint32_t avg_cpu_ms,
                           uint32_t late_delta) {
    if (hud_mode>=2u) return;
    hud_buf_t b;
    if (hud_mode==1u) {
        hud_draw_box(0,1,320,10);
        b.len=0;b.data[0]='\0';
        hud_put_u32(&b,fps);hud_put_str(&b,"FPS ");
        hud_put_u32(&b,avg_ms);hud_put_str(&b,"M CMD:");
        hud_put_u32(&b,stats->commands_used);hud_put_str(&b," M:");
        hud_put_i32(&b,player.feet.x/ONE);hud_put_str(&b,",");
        hud_put_i32(&b,player.feet.y/ONE);hud_put_str(&b,",");
        hud_put_i32(&b,player.feet.z/ONE);hud_put_str(&b," Y:");
        hud_put_i32(&b,camera_yaw);
        hud_draw_text(2,2,b.data);
        return;
    }
    static const char *const clip_names[4]={"IDL","WLK","RUN","JMP"};
    hud_draw_box(0,1,320,20);
    /* Line 1: timing, CPU work, VDP1 commands/capacity, late VBlanks, VRAM free */
    b.len=0;b.data[0]='\0';
    hud_put_u32(&b,fps);hud_put_str(&b,"FPS ");
    hud_put_u32(&b,avg_ms);hud_put_str(&b,"M CPU:");
    hud_put_u32(&b,avg_cpu_ms);hud_put_str(&b," CMD:");
    hud_put_u32(&b,stats->commands_used);hud_put_str(&b,"/");
    hud_put_u32(&b,stats->commands_capacity);hud_put_str(&b," L:");
    hud_put_u32(&b,late_delta);hud_put_str(&b," ");
    hud_put_u32(&b,g_sm64ds_castle_stats.texture_arena_remaining/1024u);
    hud_put_str(&b,"K");
    hud_draw_text(2,2,b.data);

    /* Line 2: submitted/culled/clipped/fallback/skipped faces + support pushes */
    b.len=0;b.data[0]='\0';
    hud_put_str(&b,"F:");hud_put_u32(&b,stats->submitted_faces);
    hud_put_str(&b," CU:");hud_put_u32(&b,stats->culled_faces);
    hud_put_str(&b," CL:");hud_put_u32(&b,stats->clipped_faces);
    hud_put_str(&b," FB:");hud_put_u32(&b,stats->fallback_faces);
    hud_put_str(&b," SK:");hud_put_u32(&b,stats->skipped_faces);
    hud_put_str(&b," SP:");hud_put_u32(&b,hud_support_pushed);
    hud_draw_text(2,11,b.data);

    hud_draw_box(0,203,320,20);
    /* Line 3: Mario position, facing, grounded/air/paused, anim, floor slope, height/walls */
    b.len=0;b.data[0]='\0';
    hud_put_str(&b,"M:");
    hud_put_i32(&b,player.feet.x/ONE);hud_put_str(&b,",");
    hud_put_i32(&b,player.feet.y/ONE);hud_put_str(&b,",");
    hud_put_i32(&b,player.feet.z/ONE);
    hud_put_str(&b," F:");hud_put_i32(&b,facing);
    hud_put_str(&b,paused?" P PAU":(player.grounded?" G ":" A "));
    if (!paused) hud_put_str(&b,clip<4u?clip_names[clip]:"???");
    hud_put_str(&b," NY:");
    if (hud_floor_ok) hud_put_i32(&b,hud_floor_ny_pct);
    else hud_put_str(&b,"--");
    if (!player.grounded) {
        hud_put_str(&b," H:");hud_put_i32(&b,hud_floor_height);
    } else {
        hud_put_str(&b," W:");hud_put_u32(&b,player.wall_hits);
    }
    hud_draw_text(2,204,b.data);

    /* Line 4: Camera eye position, req/actual yaw, clearance, zoom, visible props */
    b.len=0;b.data[0]='\0';
    hud_put_str(&b,"C:");
    hud_put_i32(&b,camera.eye.x/ONE);hud_put_str(&b,",");
    hud_put_i32(&b,camera.eye.y/ONE);hud_put_str(&b,",");
    hud_put_i32(&b,camera.eye.z/ONE);
    hud_put_str(&b," Y:");hud_put_i32(&b,yaw);
    hud_put_str(&b,"/");hud_put_i32(&b,camera_yaw);
    hud_put_str(&b," D:");hud_put_i32(&b,g_sm64ds_castle_stats.camera_clearance/ONE);
    hud_put_str(&b,close_camera?" N":" F");
#ifdef CASTLE_PROPS_AVAILABLE
    hud_put_str(&b," T:");hud_put_u32(&b,hud_trees_drawn);
    hud_put_str(&b," S:");hud_put_u32(&b,hud_signs_drawn);
#ifdef CASTLE_CHUNK_CULLING
    hud_put_str(&b," V:");hud_put_u32(&b,hud_chunks_drawn);
#endif
#elif defined(CASTLE_ROOM_CULLING)
    hud_put_str(&b," R:");hud_put_u32(&b,current_room);
    hud_put_str(&b," V:");hud_put_u32(&b,hud_rooms_drawn);
#endif
    hud_draw_text(2,213,b.data);
}
#endif

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
    const sat_vec3_t p4_eye={player.spawn.x,sy+24*ONE,player.spawn.z+CASTLE_CLOSE_CAM_DIST*ONE};

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

#if defined(CASTLE_WARP_AVAILABLE) && !SM64DS_VISUAL_DIAGNOSTICS
static void draw_warp_fade(uint8_t step) {
    if (step==0u) return;
    sat_polygon_cmd_t cmd={
        .x={-160,160,160,-160},
        .y={-112,-112,112,112},
        .color=SAT_RGB555(0,0,0),
        .flags=step<3u?SAT_SPRITE_FLAG_HALF_TRANSPARENT:0u
    };
    SAT_PANIC_IF_ERROR(sat_vdp1_draw_polygon(&cmd));
}

static void execute_stage_warp(uint8_t entrance) {
    sm64ds_warp_arg_t out_arg={
        .magic=SM64DS_WARP_MAGIC,
        .entrance=entrance,
        .hud_mode=hud_mode,
        .close_camera=(uint8_t)close_camera,
        .reserved=0u
    };
    sat_result_t r=sat_cd_mount_default(&cd_block,0,0,&cd_device,0u,&cd_volume);
    if (r==SAT_OK) {
#if SM64DS_VDP2_SKY
        sky_shutdown();
#endif
        (void)sat_exec(&cd_volume,CASTLE_WARP_TARGET_BIN,&out_arg,sizeof(out_arg));
#if SM64DS_VDP2_SKY
        sky_init();
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
#if defined(CASTLE_INTRO_PROPS_AVAILABLE) && !SM64DS_VISUAL_DIAGNOSTICS
    if (intro_cutscene_active) {
        intro_init_props();
        intro_init_audio();
    }
#endif
    g_sm64ds_castle_stats.texture_arena_remaining=sat_vdp1_vram_free_bytes();
    player.spawn=(sat_vec3_t){CASTLE_SPAWN_X,CASTLE_SPAWN_Y,CASTLE_SPAWN_Z};
    int32_t spawn_floor_ceiling=CASTLE_SPAWN_FLOOR_CEILING;
#if defined(CASTLE_WARP_AVAILABLE) && !SM64DS_VISUAL_DIAGNOSTICS
    if (in_arg_valid) {
        if (in_arg.hud_mode<3u) hud_mode=in_arg.hud_mode;
        close_camera=in_arg.close_camera?1:0;
        if (in_arg.entrance==SM64DS_ENTRANCE_RETURN) {
            player.spawn.x=CASTLE_RETURN_SPAWN_X;
            player.spawn.z=CASTLE_RETURN_SPAWN_Z;
            spawn_floor_ceiling=CASTLE_RETURN_FLOOR_CEILING;
            spawn_yaw_default=CASTLE_RETURN_YAW;
            spawn_facing_default=CASTLE_RETURN_FACING;
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
            warp_target_entrance=CASTLE_WARP_TARGET_ENTRANCE;
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
            while(accumulator>=1000) {simulation(&pad,jump_pending!=0);jump_pending=0;accumulator-=1000;++steps;}
            g_sm64ds_castle_profile.sim_steps+=steps;
            if(steps>g_sm64ds_castle_profile.max_sim_steps) g_sm64ds_castle_profile.max_sim_steps=steps;
        } else {accumulator=0;jump_pending=0;}
#if defined(CASTLE_WARP_AVAILABLE) && !SM64DS_VISUAL_DIAGNOSTICS
        if (warp_fade==0u && player.ticks>45u &&
            player.feet.x>=CASTLE_WARP_MIN_X && player.feet.x<=CASTLE_WARP_MAX_X &&
            player.feet.y>=CASTLE_WARP_MIN_Y && player.feet.y<=CASTLE_WARP_MAX_Y &&
            player.feet.z>=CASTLE_WARP_MIN_Z && player.feet.z<=CASTLE_WARP_MAX_Z) {
            warp_fade=1u;
            warp_target_entrance=CASTLE_WARP_TARGET_ENTRANCE;
        }
        if (warp_fade>0u) {
            ++warp_fade;
            if (warp_fade>=5u) execute_stage_warp(warp_target_entrance);
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
        SAT_PANIC_IF_ERROR(sat_model_transform3d_matrix(&transform,&actor_world));
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
#ifdef CASTLE_ROOM_CULLING
        update_visible_rooms();
#endif
        profile_lap(PROF_CAMERA);
#if !SM64DS_VDP2_SKY
        SAT_PANIC_IF_ERROR(sat_set_clear_color(SAT_RGB555(CASTLE_BG_R,CASTLE_BG_G,CASTLE_BG_B)));
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
            for (uint8_t c=0;c<CASTLE_CHUNK_COUNT;++c) {
                chunk_qfirst[c]=scene.faces.count;
                if (scene.faces.count<chunk_cap && !exp_chunk_far(c)) {
                    uint16_t v0=castle_chunk_vfirst[c];
                    SAT_PANIC_IF_ERROR(sat_scene_submit_instance(
                        &scene,&chunk_instances[c],SAT_SCENE3D_SLOT_INHERIT,&cp[v0],0));
                }
                chunk_qend[c]=scene.faces.count;
                if (chunk_qend[c]>chunk_qfirst[c]) ++hud_chunks_drawn;
            }
#else
            SAT_PANIC_IF_ERROR(sat_scene_submit_instance(&scene,&castle.instance,SAT_SCENE3D_SLOT_INHERIT,cp,0));
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
        g_sm64ds_castle_stats.camera_x=camera.eye.x;g_sm64ds_castle_stats.camera_y=camera.eye.y;g_sm64ds_castle_stats.camera_z=camera.eye.z;
        g_sm64ds_castle_stats.target_x=camera.target.x;g_sm64ds_castle_stats.target_y=camera.target.y;g_sm64ds_castle_stats.target_z=camera.target.z;
        g_sm64ds_castle_stats.mario_facing=facing*ONE;g_sm64ds_castle_stats.camera_fov_y=camera.fov_y;
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
