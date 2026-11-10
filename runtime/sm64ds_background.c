#include "sm64ds_background.h"
#include <limits.h>
#include <stddef.h>

sat_result_t sm64ds_background_init(
    sm64ds_background_t* bg, const sat_model_asset_t* model,
    const sm64ds_background_buffers_t* buffers) {
    if (!bg || !model || !buffers || !buffers->vertices || !buffers->indices ||
        !buffers->textures || !buffers->materials || !buffers->face_materials)
        return SAT_ERR_INVALID_ARG;
    const sat_result_t valid = sat_model_validate(model);
    if (valid != SAT_OK) return valid;
    if (model->texture_count == 0 || model->palette_count == 0 ||
        model->palette_base == 0) return SAT_ERR_INVALID_ARG;
    if (buffers->vertex_capacity < model->vertex_count ||
        buffers->face_capacity < model->face_count ||
        buffers->texture_capacity < model->texture_count) return SAT_ERR_CAPACITY;
    for (uint16_t i = 0; i < model->face_count; ++i)
        if (model->face_texture_indices[i] == SAT_MESH_TEXTURE_NONE)
            return SAT_ERR_UNSUPPORTED;

    *bg = (sm64ds_background_t){0};
    sat_result_t st = sat_model_compute_bounds(model,&bg->local_min,&bg->local_max);
    if (st != SAT_OK) return st;
    st = sat_mesh_init(&bg->mesh,buffers->vertices,buffers->vertex_capacity,
                       buffers->indices,buffers->face_capacity);
    if (st != SAT_OK) return st;
    st = sat_model_copy_to_mesh(model,&bg->mesh);
    if (st != SAT_OK) return st;
    st = sat_model_upload_textures(model,buffers->textures,buffers->texture_capacity);
    if (st != SAT_OK) return st;
    for (uint16_t i=0; i<model->texture_count; ++i) {
        buffers->materials[i] = (sat_scene3d_material_t){0};
        buffers->materials[i].kind = SAT_SCENE3D_INDEXED_TEXTURED;
        buffers->materials[i].texture = &buffers->textures[i];
        buffers->materials[i].color_calc_slot = SAT_INDEXED_SOLID_OPAQUE;
    }
    for (uint16_t i=0; i<model->face_count; ++i)
        buffers->face_materials[i] = model->face_texture_indices[i];
    st = sat_mat4_identity(&bg->world);
    if (st != SAT_OK) return st;
    bg->instance = (sat_scene3d_instance_t){0};
    bg->instance.mesh = &bg->mesh;
    bg->instance.materials = buffers->materials;
    bg->instance.material_count = model->texture_count;
    bg->instance.face_materials = buffers->face_materials;
    bg->instance.world = &bg->world;
    bg->instance.pass = SM64DS_BACKGROUND_PASS;
    bg->instance.cull_backfaces = 0;
    bg->asset = model;
    bg->ready = 1;
    return SAT_OK;
}

sat_result_t sm64ds_background_submit(
    sm64ds_background_t* bg, sat_scene_t* scene, const sat_vec3_t* eye,
    sat_projected_vertex_t* projected_scratch, sat_vec3_t* world_scratch) {
    if (!bg || !bg->ready || !scene || !scene->active ||
        !eye || !projected_scratch || !world_scratch)
        return SAT_ERR_INVALID_ARG;
    if ((uint32_t)scene->faces.count + bg->asset->face_count > scene->faces.capacity)
        return SAT_ERR_CAPACITY;
    const int32_t axis[3]={eye->x,eye->y,eye->z};
    const int32_t low[3]={bg->local_min.x,bg->local_min.y,bg->local_min.z};
    const int32_t high[3]={bg->local_max.x,bg->local_max.y,bg->local_max.z};
    for (uint8_t i=0;i<3;++i)
        if ((int64_t)axis[i]+low[i]<INT32_MIN ||
            (int64_t)axis[i]+high[i]>INT32_MAX)
            return SAT_ERR_CAPACITY;
    const sat_result_t st=sat_mat4_translate(&bg->world,eye->x,eye->y,eye->z);
    if (st != SAT_OK) return st;
    return sat_scene_submit_instance(scene,&bg->instance,SAT_SCENE3D_SLOT_INHERIT,
                                     projected_scratch,world_scratch);
}
