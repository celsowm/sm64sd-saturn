#pragma once
#include "model3d.h"
typedef enum { SAT_SCENE3D_RGB=0,SAT_SCENE3D_INDEXED_SOLID=1,SAT_SCENE3D_INDEXED_TEXTURED=2 } sat_scene3d_material_kind_t;
typedef struct {
 sat_scene3d_material_kind_t kind; uint16_t rgb555;
 const sat_vdp1_texture_t* texture; void* tiled; uint8_t color_calc_slot;
 const uint16_t* vertex_gouraud; uint16_t sprite_flags;
} sat_scene3d_material_t;
typedef struct {
 const sat_mesh_t* mesh; const sat_scene3d_material_t* materials;
 uint16_t material_count; const uint16_t* face_materials;
 const sat_mat4_t* world; uint16_t pass; uint8_t cull_backfaces;
 const void* bounds;
} sat_scene3d_instance_t;
typedef struct { uint16_t count,capacity; } sat_scene3d_faces_t;
typedef struct { sat_scene3d_faces_t faces; uint8_t active; } sat_scene_t;
#define SAT_SCENE3D_SLOT_INHERIT 255u
#define SAT_INDEXED_SOLID_OPAQUE 255u
sat_result_t sat_scene_submit_instance(sat_scene_t*,const sat_scene3d_instance_t*,uint8_t,sat_projected_vertex_t*,sat_vec3_t*);
