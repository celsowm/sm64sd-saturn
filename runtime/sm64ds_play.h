#pragma once
#include <stdint.h>
#include <saturn/math3d.h>

typedef struct {
    sat_vec3_t origin, normal, edges[3], min, max;
    int32_t extent;
    uint16_t attribute;
} sm64ds_prism_t;

typedef struct {
    const sm64ds_prism_t *prisms;
    const uint32_t *offsets;
    const uint16_t *indices;
    uint16_t count, nx, nz;
    int32_t origin_x, origin_z;
} sm64ds_collision_t;

typedef struct {
    sat_vec3_t feet, spawn;
    int32_t velocity_y;
    uint32_t ticks, jumps, landings, wall_hits, resets;
    uint8_t grounded, moving, running;
} sm64ds_player_t;

/* Fixed 60 Hz prototype locomotion. Distances are in the exported world.
 * Original KCL is retained; DS player state/CLPS behavior is not emulated. */
int sm64ds_floor(const sm64ds_collision_t *, int32_t x, int32_t z,
                 int32_t ceiling, int32_t *height);
void sm64ds_player_reset(sm64ds_player_t *);
void sm64ds_player_step(sm64ds_player_t *, const sm64ds_collision_t *,
                        int32_t dx, int32_t dz, uint8_t jump, uint8_t run);
int32_t sm64ds_camera_fraction(const sm64ds_collision_t *,
                               const sat_vec3_t *from, const sat_vec3_t *to);
