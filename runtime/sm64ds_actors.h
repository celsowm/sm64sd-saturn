#ifndef SM64DS_ACTORS_H
#define SM64DS_ACTORS_H

/* Static posed actor kinds: one shared baked model, many placements.
 * Generated code (actor_<name>.c) owns every buffer; the runtime only binds
 * and draws them. Stage code lists its kinds in castle_actor_kinds[]. */
#include <stdint.h>
#include "sm64ds_background.h"
#include "sm64ds_play.h"

#ifdef __cplusplus
extern "C" {
#endif

enum { SM64DS_ACTOR_STATIC = 0, SM64DS_ACTOR_CHASER = 1, SM64DS_ACTOR_BOSS = 2, SM64DS_ACTOR_STAR = 3, SM64DS_ACTOR_COIN = 4, SM64DS_ACTOR_WANWAN = 5, SM64DS_ACTOR_IRONBALL = 6 };
enum { SM64DS_ACTOR_IDLE = 0, SM64DS_ACTOR_CHASING = 1, SM64DS_ACTOR_DEAD = 2, SM64DS_ACTOR_FUSE = 3, SM64DS_ACTOR_STUNNED = 4, SM64DS_ACTOR_HIDDEN = 5, SM64DS_ACTOR_HELD = 6, SM64DS_ACTOR_FLYING = 7 };

/* Result of one update: how many actors hit the player, the summed push
 * direction (horizontal, 16.16, away from the actors), coins collected and
 * the death/bounce/collect flags. */
typedef struct {
    uint32_t count;
    int32_t push_x, push_z;
    uint8_t bounce, stars, damage, coins;
    uint8_t star_index;      /* star kind's stage star number (1..) */
    uint8_t star_bit;        /* save bit for the collected star */
    uint8_t boss_defeated;   /* boss hp hit 0 this step */
} sm64ds_actor_hit_t;

typedef struct sm64ds_actor_kind {
    const char* name;
    const sat_model_asset_t* model;
    const sat_vec3_t* positions;
    const int16_t* yaw_deg;
    uint16_t count;
    uint8_t one_sided;
    uint16_t max_depth; /* world units; farther placements are skipped */
    sat_vec3_t *v, *w;
    uint16_t *idx, *fm;
    sat_vdp1_texture_t* tex;
    sat_scene3d_material_t* mat;
    sat_projected_vertex_t* proj;
    sat_scene3d_material_program_t* prog;
    sat_mat4_t* worlds;
    uint16_t vcap, fcap, tcap;
    /* Behavior: speed/range/radius in 16.16 world units. `pos` starts as a
     * copy of `positions`; st/tm/yaw are per placement. */
    uint8_t behavior;
    int32_t speed, range, radius;
    uint16_t fuse_steps;   /* 0: consumed on contact; else lights a fuse */
    int32_t blast;         /* explosion radius */
    uint8_t hp;            /* boss: stomps to defeat */
    int32_t top;           /* boss: height above its feet that counts as its head */
    const uint8_t* unlock; /* star: stays hidden until *unlock is nonzero.
                            * For a boss-owned star this points at the boss
                            * kind's `defeated` byte, set on defeat. */
    uint8_t coin_value;    /* coin: coins granted per pickup */
    uint8_t defeated;      /* boss: set once hp runs out */
    uint8_t hp_left;
    uint8_t stun_steps;    /* boss: stunned steps left on the current hit */
    uint8_t star_bit;      /* star: save bit this kind sets (1..8), 0 = none */
    sat_vec3_t* pos;
    int16_t* yaw_live;
    uint8_t* st;
    uint16_t* tm;
    int32_t* vx, *vy, *vz; /* boss: throw ballistics / held follow */
    uint8_t held_yaw;      /* boss: yaw Mario is facing while carrying */
    /* State owned by the runtime. */
    sm64ds_background_t prop;
    sat_scene3d_material_programs_t programs;
    sat_scene3d_instance_binding_t binding;
    uint16_t drawn;
} sm64ds_actor_kind_t;

sat_result_t sm64ds_actor_kind_init(sm64ds_actor_kind_t* kind);

/* Submit every placement in front of the camera. fwd/right are the camera's
 * horizontal basis. Returns the number submitted through kind->drawn.
 * player_feet (optional) culls placements farther than a body-height above
 * or below Mario. */
sat_result_t sm64ds_actor_kind_submit(
    sm64ds_actor_kind_t* kind, sat_scene_t* scene, const sat_vec3_t* eye,
    const sat_vec3_t* fwd, const sat_vec3_t* right, uint32_t face_limit,
    const sat_vec3_t* player_feet, uint16_t player_height);

/* One fixed 60 Hz step. A chaser that reaches the player either hits at
 * once (fuse_steps == 0) or lights its fuse and explodes after fuse_steps,
 * hitting the player if still within `blast`. Hit actors respawn later. */
void sm64ds_actor_kind_update(sm64ds_actor_kind_t* kind,
                              const sm64ds_collision_t* collision,
                              const sm64ds_player_t* player,
                              sm64ds_actor_hit_t* hit);
/* Grab/hold/throw against the boss kind. */
void sm64ds_actor_grab(sm64ds_actor_kind_t* kind, const sm64ds_player_t* player,
                        uint8_t grab, uint8_t throw, sm64ds_actor_hit_t* hit);
/* 1 while `kind` is carrying a placement. */
uint8_t sm64ds_actor_held(const sm64ds_actor_kind_t* kind);

#ifdef __cplusplus
}
#endif
#endif
