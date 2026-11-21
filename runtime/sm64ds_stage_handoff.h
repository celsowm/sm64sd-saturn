#pragma once

#include <stdint.h>

/* Shared sat_exec handoff payload passed between 0.BIN (intro), EXT.BIN (Castle Grounds),
 * and C1F.BIN (Castle 1F). Fits well within SAT_EXEC_ARG_MAX (64 bytes). */
#define SM64DS_WARP_MAGIC 0x534D3634u

#define SM64DS_ENTRANCE_DEFAULT 0u
#define SM64DS_ENTRANCE_RETURN  1u
#define SM64DS_ENTRANCE_INTRO   2u

typedef struct {
    uint32_t magic;
    uint8_t entrance;
    uint8_t hud_mode;
    uint8_t close_camera;
    uint8_t stars;          /* stars collected in the previous stage */
    uint8_t star_bits;      /* bit per course star (save bit) */
    uint8_t reserved;
} sm64ds_warp_arg_t;

/* Generated per stage (castle_scene.c). Entrance ids are indexes into the
 * stage's entrance table: 0 default, 1 return from the other castle stage,
 * 2 intro (castle only), 3+ returns from courses. */
typedef struct {
    int32_t x, z, floor_ceiling;
    int16_t yaw, facing;
} sm64ds_entrance_t;

/* Trigger box (16.16 feet position) to another stage binary. A box with
 * min > max never triggers; the L+R+Z hotkey always uses warps[0]. When
 * needs_air is set the player must be off the ground (jump into a painting). */
typedef struct {
    int32_t min[3], max[3];
    const char *bin;
    uint8_t entrance, needs_air;
} sm64ds_warp_t;

/* Everything the runtime needs to know about the stage it was built for.
 * Generated into castle_scene.c as `castle_stage`. entrances[0] is the
 * default spawn. */
typedef struct {
    const char *name;
    uint8_t id, bg_rgb[3];
    int16_t default_cam_dist, close_cam_dist;
    int16_t far_cull;      /* world units; terrain chunks farther than this are skipped (0: off) */
    int32_t kill_y;
    uint8_t entrance_count, warp_count;
    const sm64ds_entrance_t *entrances;
    const sm64ds_warp_t *warps;
} sm64ds_stage_desc_t;
