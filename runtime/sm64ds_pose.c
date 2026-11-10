#include "sm64ds_pose.h"
#include <saturn/transform3d.h>

static sat_fx16_t blend_fx(sat_fx16_t a, sat_fx16_t b, uint32_t t) {
    return (sat_fx16_t)((int64_t)a + (((int64_t)b - a) * t >> 16));
}

sat_result_t sm64ds_clip_sample_scale(
    const sm64ds_scale_clip_t *scale, const sat_skeleton_clip_t *clip,
    sat_fx16_t time, sat_vec3_t *out, uint16_t capacity) {
    if (!scale || !clip || !out || clip->joint_count == 0 ||
        clip->frame_count == 0 || clip->rate_den == 0 || clip->rate_num == 0 ||
        capacity < clip->joint_count || time < 0 ||
        scale->joint_count != clip->joint_count)
        return SAT_ERR_INVALID_ARG;
    const uint16_t n = clip->joint_count;
    if (!scale->frames) {
        for (uint16_t j=0;j<n;++j) {
            out[j].x=SAT_FX16_ONE; out[j].y=SAT_FX16_ONE; out[j].z=SAT_FX16_ONE;
        }
        return SAT_OK;
    }
    if (scale->frame_count != clip->frame_count)
        return SAT_ERR_INVALID_ARG;
    uint64_t ticks=((uint64_t)(uint32_t)time * clip->rate_num) / clip->rate_den;
    uint32_t frame=(uint32_t)(ticks >> 16);
    uint32_t fraction=(uint32_t)(ticks & 0xffffu);
    if ((clip->flags & SAT_CLIP_FLAG_LOOP)!=0u) {
        frame %= clip->frame_count;
    } else if (frame >= clip->frame_count-1u) {
        frame=clip->frame_count-1u; fraction=0u;
    }
    const uint32_t next=(frame+1u<clip->frame_count) ? frame+1u :
                        (((clip->flags & SAT_CLIP_FLAG_LOOP)!=0u) ? 0u : frame);
    const sat_vec3_t *a=&scale->frames[frame*n], *b=&scale->frames[next*n];
    for (uint16_t j=0;j<n;++j) {
        out[j].x=blend_fx(a[j].x,b[j].x,fraction);
        out[j].y=blend_fx(a[j].y,b[j].y,fraction);
        out[j].z=blend_fx(a[j].z,b[j].z,fraction);
    }
    return SAT_OK;
}

sat_result_t sm64ds_pose_world_matrices(
    const sat_skeleton_asset_t *skeleton,
    const sat_skeleton_pose_joint_t *pose,
    const sat_vec3_t *scales,
    sat_mat4_t *world, uint16_t capacity) {
    if (!skeleton || !skeleton->joints || !pose || !scales || !world ||
        skeleton->joint_count==0 || capacity<skeleton->joint_count)
        return SAT_ERR_INVALID_ARG;
    for (uint16_t i=0;i<skeleton->joint_count;++i) {
        const uint16_t p=skeleton->joints[i].parent;
        if (p!=SAT_TRANSFORM3D_ROOT && p>=i)
            return SAT_ERR_INVALID_ARG;
        sat_mat4_t rigid, scale, local;
        sat_quat16_to_mat4(&rigid,&pose[i].rotation,&pose[i].translation);
        sat_result_t st=sat_mat4_scale(&scale,scales[i].x,scales[i].y,scales[i].z);
        if (st!=SAT_OK) return st;
        st=sat_mat4_multiply(&local,&rigid,&scale);
        if (st!=SAT_OK) return st;
        if (p!=SAT_TRANSFORM3D_ROOT) {
            st=sat_mat4_multiply(&world[i],&world[p],&local);
            if (st!=SAT_OK) return st;
        } else {
            world[i]=local;
        }
    }
    return SAT_OK;
}
