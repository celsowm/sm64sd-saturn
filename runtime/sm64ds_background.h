#ifndef SM64DS_BACKGROUND_H
#define SM64DS_BACKGROUND_H

/* Camera-relative static skyboxes. Caller owns all buffers. */
#include <stdint.h>
#include <saturn/model3d.h>
#include <saturn/scene.h>
#ifdef __cplusplus
extern "C" {
#endif

#define SM64DS_BACKGROUND_PASS 0u
#define SM64DS_ACTOR_PASS 1u

typedef struct sm64ds_background_buffers {
    sat_vec3_t* vertices;
    uint16_t* indices; /* face_capacity * 4 elements */
    sat_vdp1_texture_t* textures;
    sat_scene3d_material_t* materials;
    uint16_t* face_materials;
    uint16_t vertex_capacity, face_capacity, texture_capacity;
} sm64ds_background_buffers_t;

typedef struct sm64ds_background {
    const sat_model_asset_t* asset;
    sat_mesh_t mesh;
    sat_mat4_t world;
    sat_scene3d_instance_t instance;
    sat_vec3_t local_min, local_max;
    uint8_t ready;
} sm64ds_background_t;

/* Call after sat_init; background indexed8 bank 0 is reserved for Mario.
 * Upload once; all faces must be textured. */
sat_result_t sm64ds_background_init(
    sm64ds_background_t* bg, const sat_model_asset_t* model,
    const sm64ds_background_buffers_t* buffers);

/* Call inside an active scene, using the scene camera's eye.
 * Preflight 16.16 overflow and remaining scene face capacity. */
sat_result_t sm64ds_background_submit(
    sm64ds_background_t* bg, sat_scene_t* scene, const sat_vec3_t* eye,
    sat_projected_vertex_t* projected_scratch, sat_vec3_t* world_scratch);

#ifdef __cplusplus
}
#endif
#endif
