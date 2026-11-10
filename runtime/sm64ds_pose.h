#ifndef SM64DS_POSE_H
#define SM64DS_POSE_H
#include <stdint.h>
#include <saturn/skeleton3d.h>
#include <saturn/math3d.h>
#ifdef __cplusplus
extern "C" {
#endif
/* Optional BCA scale channels. NULL frames mean scale=(1,1,1). */
typedef struct sm64ds_scale_clip {
    const sat_vec3_t *frames;    /* frame-major [frame_count*joint_count] */
    uint16_t frame_count;
    uint16_t joint_count;
} sm64ds_scale_clip_t;

/* Sample scale with the same 16.16 clock/rate/loop policy as sat_clip_sample.
 * The independent array makes it possible to preserve animated BCA scale
 * without changing LibSaturn's scale-less sat_skeleton_pose_joint_t ABI. */
sat_result_t sm64ds_clip_sample_scale(
    const sm64ds_scale_clip_t *scale, const sat_skeleton_clip_t *clip,
    sat_fx16_t time, sat_vec3_t *out, uint16_t capacity);

/* Build dynamic T*R*S matrices in parent-first order; these are directly
 * accepted by sat_skin_update_mesh. Rebuild rather than scaling an already
 * composited world matrix (which breaks child joint translations). */
sat_result_t sm64ds_pose_world_matrices(
    const sat_skeleton_asset_t *skeleton,
    const sat_skeleton_pose_joint_t *pose,
    const sat_vec3_t *scales,
    sat_mat4_t *world, uint16_t capacity);
#ifdef __cplusplus
}
#endif
#endif
