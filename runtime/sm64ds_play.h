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
    /* Bitmask of CLPS attribute indices (<32) marked traction=3 (unclimbable/slippery). */
    uint32_t slippery_attrs;
    /* Bitmask of CLPS attribute indices (<32) whose word0 carries the water
     * bit (0x20): those floors are the water surface, not solid ground. */
    uint32_t water_attrs;
    uint8_t climb_enabled;
} sm64ds_collision_t;

#define SM64DS_PLAYER_MAX_HEALTH 8

typedef struct {
    sat_vec3_t feet, spawn;
    int32_t velocity_y;
    uint32_t ticks, jumps, landings, wall_hits, resets;
    uint8_t grounded, moving, running;
    uint8_t swimming;         /* 1 while in the swim state (St_Swim) */
    uint8_t climbing;        /* 1 while mantling a terrace wall */
    uint8_t climb_cooldown;  /* steps before another climb can start */
    sat_vec3_t climb_top;    /* world position of the ledge to mantle onto */
    uint16_t climb_steps;    /* steps spent in the current climb (timeout) */
    uint32_t climb_count;    /* total climbs started (telemetry) */
    int32_t knock_x, knock_z; /* per-step push from hits; decays */
    uint8_t health, max_health;
    uint8_t invuln;           /* hurt i-frames left, in 60 Hz steps */
    uint8_t dead;             /* 1 while the death timer runs */
    uint16_t death_timer;     /* steps until respawn at `spawn` */
    uint16_t coins;           /* collected this life; every 50 heals 1 */
    uint8_t held_yaw;         /* boss: facing to throw along while carrying */
    /* Swimming, after the DS St_Swim_Main. The caller sets the inputs before
     * each step. Angles use the DS 0x10000-per-turn units. While swimming the
     * step turns `yaw` itself; otherwise the caller keeps it at the facing. */
    int8_t swim_turn, swim_pitch; /* d-pad: 1 = right; 1 = back (rise) */
    uint8_t swim_stroke_held;     /* stroke button held */
    uint8_t swim_phase, swim_timer, swim_released, swim_wall;
    uint16_t yaw;
    int16_t pitch, yaw_speed;     /* pitch: nose down is positive */
    int32_t swim_speed;           /* along the pitch, 16.16 per step */
    int32_t water_y;              /* surface of the water being swum */
    uint16_t air_ticks;           /* steps spent deep, toward a lost health point */
    uint16_t heal_ticks;          /* steps at the surface, toward a healed one */
} sm64ds_player_t;

/* Fixed 60 Hz prototype locomotion. Distances are in the exported world.
 * Original KCL is retained; DS player state/CLPS behavior is not emulated. */
int sm64ds_floor(const sm64ds_collision_t *, int32_t x, int32_t z,
                 int32_t ceiling, int32_t *height);
/* As above, also returns the normal of the selected highest floor. */
int sm64ds_floor_normal(const sm64ds_collision_t *, int32_t x, int32_t z,
                        int32_t ceiling, int32_t *height, sat_vec3_t *normal);
/* The lowest water surface at or above `from` at x/z (CLPS water bit). */
int sm64ds_water_surface(const sm64ds_collision_t *, int32_t x, int32_t z,
                         int32_t from, int32_t *height);
/* Upward translation needed to keep transformed body vertices above a floor
 * plane. The caller decides whether that plane is appropriate for the pose. */
int32_t sm64ds_ground_pose_lift(const sat_vec3_t *vertices,uint16_t count,
                                 const sat_mat4_t *world,const sat_vec3_t *point,
                                 const sat_vec3_t *normal);
void sm64ds_player_reset(sm64ds_player_t *);
void sm64ds_player_step(sm64ds_player_t *, const sm64ds_collision_t *,
                        int32_t dx, int32_t dz, uint8_t jump, uint8_t run);
/* Damage with knockback. Ignored while dead or in hurt i-frames. A hit that
 * empties health starts the death timer; the next step() respawns at `spawn`
 * with full health. */
void sm64ds_player_hurt(sm64ds_player_t *, uint8_t damage,
                        int32_t push_x, int32_t push_z);
/* Restore health up to the maximum. Ignored while dead. */
void sm64ds_player_heal(sm64ds_player_t *, uint8_t amount);
/* Add coins. Every 50 coins restores one health point (SM64 rule). Coins
 * survive a death and are not cleared by reset(). */
void sm64ds_player_add_coins(sm64ds_player_t *, uint16_t amount);
int32_t sm64ds_camera_fraction(const sm64ds_collision_t *,
                               const sat_vec3_t *from, const sat_vec3_t *to);
/* Choose the first usable alternative, keeping the previous alternative until
 * the requested direction has more clearance. Distances use 16.16 units. */
uint8_t sm64ds_camera_select(const int32_t *clearance, uint8_t count,
                             uint8_t previous, int32_t minimum, int32_t restore);
