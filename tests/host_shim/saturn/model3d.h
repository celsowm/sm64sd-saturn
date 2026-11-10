#pragma once
/* Host-only ABI-shaped shim; NOT an SDK header or binary ABI acceptance. */
#include <stdint.h>
typedef int32_t sat_fx16_t;
#define SAT_FX16_ONE ((sat_fx16_t)65536)
typedef enum { SAT_OK=0,SAT_ERR_INVALID_ARG=-1,SAT_ERR_CAPACITY=-3,SAT_ERR_UNSUPPORTED=-4 } sat_result_t;
typedef struct { sat_fx16_t x,y,z; } sat_vec3_t;
typedef struct { sat_fx16_t m[16]; } sat_mat4_t;
typedef struct { int16_t x,y; sat_fx16_t w; } sat_projected_vertex_t;
typedef struct {
 const uint8_t *pixels; uint16_t width,height,palette_slot,flags; uint32_t pixel_count;
} sat_model_texture_asset_t;
typedef struct {
 const sat_vec3_t *vertices; uint16_t vertex_count;
 const uint16_t *indices; uint16_t face_count;
 const uint16_t *face_texture_indices;
 const sat_model_texture_asset_t *textures; uint16_t texture_count;
 const uint16_t *palettes_rgb555; uint16_t palette_count,palette_base,reserved;
 const uint16_t *shade_palette_rgb555; uint16_t shade_palette_count;
 const uint8_t *face_base_shades; const uint16_t *luts_rgb555; uint16_t lut_count;
} sat_model_asset_t;
typedef struct { uint16_t vertex_count,face_count; sat_vec3_t *vertices; uint16_t *indices; } sat_mesh_t;
typedef struct { int valid; } sat_vdp1_texture_t;
#define SAT_MESH_TEXTURE_NONE 65535u
sat_result_t sat_model_validate(const sat_model_asset_t*);
sat_result_t sat_model_compute_bounds(const sat_model_asset_t*,sat_vec3_t*,sat_vec3_t*);
sat_result_t sat_mesh_init(sat_mesh_t*,sat_vec3_t*,uint16_t,uint16_t*,uint16_t);
sat_result_t sat_model_copy_to_mesh(const sat_model_asset_t*,sat_mesh_t*);
sat_result_t sat_model_upload_textures(const sat_model_asset_t*,sat_vdp1_texture_t*,uint16_t);
sat_result_t sat_mat4_identity(sat_mat4_t*);
sat_result_t sat_mat4_translate(sat_mat4_t*,sat_fx16_t,sat_fx16_t,sat_fx16_t);
