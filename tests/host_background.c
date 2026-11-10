/* Host mock test of camera-following skybox; not an SH-2 SDK link. */
#include <assert.h>
#include <stdint.h>
#include <string.h>
#include <limits.h>
#include "sm64ds_background.h"

static int uploads=0,submissions=0;
static sat_mat4_t submit_world;
static sat_scene3d_instance_t submitted;

sat_result_t sat_model_validate(const sat_model_asset_t* m) {
    return m && m->vertex_count && m->face_count && m->texture_count ? SAT_OK:SAT_ERR_INVALID_ARG;
}
sat_result_t sat_model_compute_bounds(const sat_model_asset_t* m,sat_vec3_t* lo,sat_vec3_t* hi) {
    *lo=*hi=m->vertices[0];
    for(uint16_t i=1;i<m->vertex_count;++i) {
        const sat_vec3_t v=m->vertices[i];
        if(v.x<lo->x)lo->x=v.x;
        if(v.x>hi->x)hi->x=v.x;
        if(v.y<lo->y)lo->y=v.y;
        if(v.y>hi->y)hi->y=v.y;
        if(v.z<lo->z)lo->z=v.z;
        if(v.z>hi->z)hi->z=v.z;
    }
    return SAT_OK;
}
sat_result_t sat_mesh_init(sat_mesh_t* mesh,sat_vec3_t* v,uint16_t vc,uint16_t* idx,uint16_t fc) {
    (void)vc;(void)fc;*mesh=(sat_mesh_t){.vertices=v,.indices=idx};return SAT_OK;
}
sat_result_t sat_model_copy_to_mesh(const sat_model_asset_t* m,sat_mesh_t* mesh) {
    memcpy(mesh->vertices,m->vertices,m->vertex_count*sizeof(sat_vec3_t));
    memcpy(mesh->indices,m->indices,m->face_count*4*sizeof(uint16_t));
    mesh->vertex_count=m->vertex_count;mesh->face_count=m->face_count;
    return SAT_OK;
}
sat_result_t sat_model_upload_textures(const sat_model_asset_t* m,sat_vdp1_texture_t* tex,uint16_t cap) {
    (void)cap;assert(m->palette_base!=0);++uploads;tex[0].valid=1;return SAT_OK;
}
sat_result_t sat_mat4_identity(sat_mat4_t* m) {
    memset(m,0,sizeof(*m));m->m[0]=m->m[5]=m->m[10]=m->m[15]=SAT_FX16_ONE;return SAT_OK;
}
sat_result_t sat_mat4_translate(sat_mat4_t* m,sat_fx16_t x,sat_fx16_t y,sat_fx16_t z) {
    sat_mat4_identity(m);m->m[3]=x;m->m[7]=y;m->m[11]=z;return SAT_OK;
}
sat_result_t sat_scene_submit_instance(sat_scene_t* scene,const sat_scene3d_instance_t* inst,uint8_t slot,
                                       sat_projected_vertex_t* p,sat_vec3_t* v) {
    (void)p;(void)v;assert(slot==SAT_SCENE3D_SLOT_INHERIT);
    assert(inst->pass==0 && !inst->cull_backfaces && inst->materials[0].texture->valid);
    ++submissions;submit_world=*inst->world;submitted=*inst;
    scene->faces.count+=inst->mesh->face_count;
    return SAT_OK;
}
static const sat_vec3_t verts[]={{-100*65536,0,-100*65536},{100*65536,0,-100*65536},
                                  {100*65536,0,100*65536},{-100*65536,0,100*65536}};
static const uint16_t indices[]={0,1,2,3};
static const uint16_t materials[]={0};
static const uint16_t palette[]={31,0};
static const uint8_t pixels[]={1,1,1,1,1,1,1,1};
static const sat_model_texture_asset_t tex_assets[]={{pixels,8,1,0,0,8}};
static sat_model_asset_t model={
    .vertices=verts,.vertex_count=4,.indices=indices,.face_count=1,
    .face_texture_indices=materials,.textures=tex_assets,.texture_count=1,
    .palettes_rgb555=palette,.palette_count=1,.palette_base=1
};

int main(void) {
    sat_vec3_t v[4];uint16_t idx[4];
    sat_vdp1_texture_t t[1]={0};sat_scene3d_material_t mat[1]={0};
    uint16_t face[1]={65535};sm64ds_background_t bg={0};
    sm64ds_background_buffers_t buf={v,idx,t,mat,face,4,1,1};
    assert(SM64DS_BACKGROUND_PASS<SM64DS_ACTOR_PASS);
    model.palette_base=0;
    assert(sm64ds_background_init(&bg,&model,&buf)==SAT_ERR_INVALID_ARG && !uploads);
    model.palette_base=1;buf.face_capacity=0;
    assert(sm64ds_background_init(&bg,&model,&buf)==SAT_ERR_CAPACITY && !uploads);
    buf.face_capacity=1;
    assert(sm64ds_background_init(&bg,&model,&buf)==SAT_OK && uploads==1);
    assert(face[0]==0 && t[0].valid && !memcmp(v,verts,sizeof(verts)));
    assert(!memcmp(idx,indices,sizeof(indices)));
    sat_projected_vertex_t projected[4];sat_vec3_t world_scratch[4];
    sat_scene_t scene={.faces={0,6},.active=1};
    const sat_vec3_t eye={30*65536,10*65536,20*65536};
    assert(sm64ds_background_submit(&bg,&scene,&eye,projected,world_scratch)==SAT_OK);
    assert(submissions==1 && scene.faces.count==1 && submitted.material_count==1);
    assert(submit_world.m[3]==eye.x && submit_world.m[7]==eye.y && submit_world.m[11]==eye.z);
    const sat_vec3_t moved={-3*65536,-2*65536,11*65536};
    assert(sm64ds_background_submit(&bg,&scene,&moved,projected,world_scratch)==SAT_OK);
    assert(submit_world.m[3]==moved.x && uploads==1 && submissions==2);
    const sat_mat4_t prior=bg.world;
    scene.faces.count=scene.faces.capacity;
    assert(sm64ds_background_submit(&bg,&scene,&eye,projected,world_scratch)==SAT_ERR_CAPACITY);
    assert(!memcmp(&prior,&bg.world,sizeof(prior)) && submissions==2);
    scene.faces.count=0;
    const sat_vec3_t overflow={INT32_MAX-2*65536,0,0};
    assert(sm64ds_background_submit(&bg,&scene,&overflow,projected,world_scratch)==SAT_ERR_CAPACITY);
    assert(!memcmp(&prior,&bg.world,sizeof(prior)) && submissions==2);
    scene.active=0;
    assert(sm64ds_background_submit(&bg,&scene,&eye,projected,world_scratch)==SAT_ERR_INVALID_ARG);
    return 0;
}
