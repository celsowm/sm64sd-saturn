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
#include "mario_preview.h"

#define W 320
#define H 224
#define N MARIO_PREVIEW_VERTEX_COUNT
#define F MARIO_PREVIEW_FACE_COUNT
#define T MARIO_PREVIEW_TEXTURE_COUNT
#define J MARIO_PREVIEW_JOINT_COUNT

static sat_vec3_t g_vertices[N];
static uint16_t g_indices[F*4];
static sat_mesh_t g_mesh;
static sat_vdp1_texture_t g_textures[T];
static sat_scene3d_material_t g_materials[T];
static uint16_t g_face_materials[F];
static sat_projected_vertex_t g_screen[N];
static sat_vec3_t g_world_vertices[N];
static sat_scene3d_face_t g_scene_faces[F];
static uint32_t g_scene_keys[F];
static uint16_t g_scene_order[F];
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
    SAT_PANIC_IF_ERROR(sat_scene_init(&g_scene,g_scene_faces,g_scene_keys,g_scene_order,F));
    g_instance.mesh=&g_mesh;
    g_instance.materials=g_materials;
    g_instance.material_count=T;
    g_instance.face_materials=g_face_materials;
    g_instance.world=&g_world;
    g_instance.pass=0u;
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
        SAT_PANIC_IF_ERROR(sat_scene_begin(&g_scene,&camera,SAT_FX16_ONE,W,H,16u));
        SAT_PANIC_IF_ERROR(sat_scene_submit_instance(&g_scene,&g_instance,
             SAT_SCENE3D_SLOT_INHERIT,g_screen,g_world_vertices));
        SAT_PANIC_IF_ERROR(sat_scene_flush(&g_scene));
        SAT_PANIC_IF_ERROR(sat_end_frame());
        g_time+=SAT_FX16_ONE/(sat_fx16_t)sat_video_refresh_hz();
    }
}
