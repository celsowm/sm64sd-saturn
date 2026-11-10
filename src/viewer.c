/* SM64DS -> Sega Saturn first scene: real LibSaturn model+skin+scene APIs.
 * Requires private mario_preview.c/.h produced from a user-owned ROM.
 * This is a technical viewer, NOT the gameplay port or hardware acceptance.
 */
#include <stdint.h>
#include <saturn/app.h>
#include <saturn/input.h>
#include <saturn/model3d.h>
#include <saturn/skin3d.h>
#include <saturn/skeleton3d.h>
#include <saturn/orbit_camera3d.h>
#include <saturn/scene.h>
#include <saturn/color.h>
#include <saturn/vdp1.h>
#include "sm64ds_pose.h"
#include "sm64ds_background.h"
#ifndef SM64DS_ENABLE_SKYBOX
#define SM64DS_ENABLE_SKYBOX 0
#endif
#if SM64DS_ENABLE_SKYBOX
#include "skybox_preview.h"
#define BG_N SKYBOX_PREVIEW_VERTEX_COUNT
#define BG_F SKYBOX_PREVIEW_FACE_COUNT
#define BG_T SKYBOX_PREVIEW_TEXTURE_COUNT
#else
#define BG_N 0u
#define BG_F 0u
#define BG_T 0u
#endif
#include "mario_preview.h"

#define W 320
#define H 224
#define N MARIO_PREVIEW_VERTEX_COUNT
#define F MARIO_PREVIEW_FACE_COUNT
#define T MARIO_PREVIEW_TEXTURE_COUNT
#define J MARIO_PREVIEW_JOINT_COUNT
#define SCENE_F (F+BG_F)
/* Policy budget only; LibSaturn allocator is authoritative about VRAM. */
#define VIEWER_TEXTURE_BUDGET_BYTES (192u*1024u)

static sat_vec3_t g_vertices[N];
static uint16_t g_indices[F*4];
static sat_mesh_t g_mesh;
static sat_vdp1_texture_t g_textures[T];
static sat_scene3d_material_t g_materials[T];
static uint16_t g_face_materials[F];
static sat_projected_vertex_t g_screen[N];
static sat_vec3_t g_world_vertices[N];
static sat_scene3d_face_t g_scene_faces[SCENE_F];
static uint32_t g_scene_keys[SCENE_F];
static uint16_t g_scene_order[SCENE_F];
static sat_scene_t g_scene;
static sat_scene3d_instance_t g_instance;
static sat_mat4_t g_world;
static sat_orbit_camera3d_t g_orbit;
static sat_skeleton_pose_joint_t g_pose[J];
static sat_vec3_t g_scales[J];
static sat_mat4_t g_bones[J];
static sat_aabb3_t g_bounds;
static uint16_t g_clip=0;
static sat_fx16_t g_time=0;
#if SM64DS_ENABLE_SKYBOX
static sm64ds_background_t g_background;
static sat_vec3_t g_bg_vertices[BG_N];
static uint16_t g_bg_indices[BG_F*4u];
static sat_vdp1_texture_t g_bg_textures[BG_T];
static sat_scene3d_material_t g_bg_materials[BG_T];
static uint16_t g_bg_face_materials[BG_F];
static sat_projected_vertex_t g_bg_projected[BG_N];
static sat_vec3_t g_bg_world_vertices[BG_N];
#endif

/* Inspect g_sm64ds_viewer_stats in Ymir debugger after a REAL frame.
 * A zero profile tick count is not a measured zero when unavailable. */
volatile struct {
    uint32_t magic, frames, submitted_faces, world_commands;
    uint32_t commands_used, commands_capacity, skipped_faces;
    uint32_t culled_faces, clipped_faces, fallback_faces;
    uint32_t profile_ticks_available, projection_ticks, painter_ticks, emission_ticks;
} g_sm64ds_viewer_stats = {.magic=0x534b5931u};

static void record_scene_stats(void) {
    sat_scene_stats_t stats={0};
    if(sat_scene_stats(&g_scene,&stats)==SAT_OK) {
        ++g_sm64ds_viewer_stats.frames;
        g_sm64ds_viewer_stats.submitted_faces=stats.submitted_faces;
        g_sm64ds_viewer_stats.world_commands=stats.world_commands;
        g_sm64ds_viewer_stats.commands_used=stats.commands_used;
        g_sm64ds_viewer_stats.commands_capacity=stats.commands_capacity;
        g_sm64ds_viewer_stats.skipped_faces=stats.skipped_faces;
        g_sm64ds_viewer_stats.culled_faces=stats.culled_faces;
        g_sm64ds_viewer_stats.clipped_faces=stats.clipped_faces;
        g_sm64ds_viewer_stats.fallback_faces=stats.fallback_faces;
    }
    sat_scene3d_profile_t profile={0};
    if(sat_scene3d_profile_get(&profile)==SAT_OK) {
        g_sm64ds_viewer_stats.profile_ticks_available=1u;
        g_sm64ds_viewer_stats.projection_ticks=profile.projection_ticks;
        g_sm64ds_viewer_stats.painter_ticks=profile.painter_ticks;
        g_sm64ds_viewer_stats.emission_ticks=profile.emission_ticks;
    } else g_sm64ds_viewer_stats.profile_ticks_available=0u;
}

static sat_result_t sample_and_skin(void) {
    const sat_skeleton_clip_t* clip=&mario_preview_clips[g_clip];
    sat_result_t st=sat_clip_sample(clip,g_time,g_pose,J);
    if(st!=SAT_OK)return st;
    st=sm64ds_clip_sample_scale(&mario_preview_scale_clips[g_clip],clip,g_time,g_scales,J);
    if(st!=SAT_OK)return st;
    st=sm64ds_pose_world_matrices(&mario_preview_skeleton,g_pose,g_scales,g_bones,J);
    if(st!=SAT_OK)return st;
    return sat_skin_update_mesh(&mario_preview_skin,g_bones,J,&g_mesh,0,&g_bounds);
}

int main(void) {
    const sat_video_config_t video={W,H,SAT_VIDEO_AUTO,0u};
    SAT_PANIC_IF_ERROR(sat_init(&video));
    SAT_PANIC_IF_ERROR(sat_model_validate(&mario_preview_model));
    uint32_t texture_bytes=sat_model_vram_estimate_bytes(&mario_preview_model);
#if SM64DS_ENABLE_SKYBOX
    SAT_PANIC_IF_ERROR(sat_model_validate(&skybox_preview_model));
    texture_bytes += sat_model_vram_estimate_bytes(&skybox_preview_model);
#endif
    if(texture_bytes>VIEWER_TEXTURE_BUDGET_BYTES)
        SAT_PANIC_IF_ERROR(SAT_ERR_CAPACITY);
    SAT_PANIC_IF_ERROR(sat_skeleton_validate(&mario_preview_skeleton));
    SAT_PANIC_IF_ERROR(sat_skin_validate(&mario_preview_skin));
    for(uint16_t i=0;i<MARIO_PREVIEW_CLIP_COUNT;++i)
        SAT_PANIC_IF_ERROR(sat_clip_validate(&mario_preview_clips[i],&mario_preview_skeleton));
    SAT_PANIC_IF_ERROR(sat_mesh_init(&g_mesh,g_vertices,N,g_indices,F));
    SAT_PANIC_IF_ERROR(sat_model_copy_to_mesh(&mario_preview_model,&g_mesh));
    SAT_PANIC_IF_ERROR(sat_skin_validate_mesh(&mario_preview_skin,&g_mesh));
    SAT_PANIC_IF_ERROR(sat_model_upload_textures(&mario_preview_model,g_textures,T));
    for(uint16_t i=0;i<T;++i) {
        g_materials[i].kind=SAT_SCENE3D_INDEXED_TEXTURED;
        g_materials[i].texture=&g_textures[i];
        g_materials[i].color_calc_slot=SAT_INDEXED_SOLID_OPAQUE;
    }
    for(uint16_t i=0;i<F;++i)
        g_face_materials[i]=mario_preview_model.face_texture_indices[i];
    SAT_PANIC_IF_ERROR(sat_scene_init(&g_scene,g_scene_faces,g_scene_keys,g_scene_order,SCENE_F));
#if SM64DS_ENABLE_SKYBOX
    const sm64ds_background_buffers_t bg_buffers={
        .vertices=g_bg_vertices, .indices=g_bg_indices,
        .textures=g_bg_textures, .materials=g_bg_materials,
        .face_materials=g_bg_face_materials,
        .vertex_capacity=BG_N, .face_capacity=BG_F, .texture_capacity=BG_T
    };
    SAT_PANIC_IF_ERROR(sm64ds_background_init(
        &g_background,&skybox_preview_model,&bg_buffers));
#endif
    g_instance.mesh=&g_mesh;
    g_instance.materials=g_materials;
    g_instance.material_count=T;
    g_instance.face_materials=g_face_materials;
    g_instance.world=&g_world;
    g_instance.pass=SM64DS_ACTOR_PASS;
    g_instance.cull_backfaces=1u;
    SAT_PANIC_IF_ERROR(sat_mat4_identity(&g_world));
    SAT_PANIC_IF_ERROR(sample_and_skin());

    sat_vec3_t mn={g_bounds.center.x-g_bounds.half.x,
                   g_bounds.center.y-g_bounds.half.y,g_bounds.center.z-g_bounds.half.z};
    sat_vec3_t mx={g_bounds.center.x+g_bounds.half.x,
                   g_bounds.center.y+g_bounds.half.y,g_bounds.center.z+g_bounds.half.z};
    sat_orbit_camera3d_fit_t fit={0};
    fit.min_extent=SAT_FX16_ONE;
    fit.min_distance_floor=sat_fx16_from_int(8);
    fit.initial_distance_factor=sat_fx16_from_int(3);
    fit.min_distance_factor=SAT_FX16_ONE;
    fit.max_distance_factor=sat_fx16_from_int(8);
    fit.near_plane_floor=SAT_FX16_ONE;
    fit.fov_y=sat_fx16_from_int(60);
    fit.aspect=sat_fx16_div(sat_fx16_from_int(W),sat_fx16_from_int(H));
    fit.far_z=sat_fx16_from_int(1500);
    fit.pitch_min_deg=-75;fit.pitch_max_deg=75;
    SAT_PANIC_IF_ERROR(sat_orbit_camera3d_fit_bounds(&g_orbit,&mn,&mx,&fit));

    while(1) {
        sat_pad_state_t pad={0};
        SAT_PANIC_IF_ERROR(sat_wait_vblank());
        SAT_PANIC_IF_ERROR(sat_pad_poll(&pad));
        if((pad.pressed & SAT_PAD_C)!=0u) {g_clip=(g_clip+1)%MARIO_PREVIEW_CLIP_COUNT;g_time=0;}
        SAT_PANIC_IF_ERROR(sat_orbit_camera3d_apply_pad(&g_orbit,&pad,SAT_PAD_A));
        SAT_PANIC_IF_ERROR(sample_and_skin());
        SAT_PANIC_IF_ERROR(sat_set_clear_color(SAT_COLOR_BLACK));
        SAT_PANIC_IF_ERROR(sat_begin_frame());
        sat_camera3d_t camera={0};
        camera.eye=g_orbit.eye;
        camera.target=g_orbit.target;
        camera.up=(sat_vec3_t){0,SAT_FX16_ONE,0};
        camera.view_proj=g_orbit.view_proj;
        camera.fov_y=g_orbit.fov_y;
        camera.aspect=g_orbit.aspect;
        camera.near_z=g_orbit.near_z;
        camera.far_z=g_orbit.far_z;
        SAT_PANIC_IF_ERROR(sat_scene_begin(&g_scene,&camera,g_orbit.near_z,W,H,16u));
#if SM64DS_ENABLE_SKYBOX
        /* Two passes; one painter flush. Backdrop never occludes Mario. */
        SAT_PANIC_IF_ERROR(sm64ds_background_submit(&g_background,&g_scene,
            &camera.eye,g_bg_projected,g_bg_world_vertices));
#endif
        SAT_PANIC_IF_ERROR(sat_scene_submit_instance(&g_scene,&g_instance,
             SAT_SCENE3D_SLOT_INHERIT,g_screen,g_world_vertices));
        /* Both texture bindings remain immutable and resident. */
        SAT_PANIC_IF_ERROR(sat_scene_flush_trusted(&g_scene));
        record_scene_stats();
        SAT_PANIC_IF_ERROR(sat_end_frame());
        g_time+=SAT_FX16_ONE/(sat_fx16_t)sat_video_refresh_hz();
    }
}
