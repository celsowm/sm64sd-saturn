#include "sm64ds_actors.h"
#include <saturn/core.h>
#include <saturn/math2d.h>
#include <saturn/model3d.h>

#define ONE SAT_FX16_ONE

static sat_result_t actor_world(sm64ds_actor_kind_t* k, uint32_t i) {
    sat_model_transform3d_t tr;
    sat_model_transform3d_identity(&tr);
    tr.position = k->pos[i];
    tr.rotation_deg.y = (int32_t)k->yaw_live[i] * ONE;
    return sat_model_transform3d_matrix(&tr, &k->worlds[i]);
}

sat_result_t sm64ds_actor_kind_init(sm64ds_actor_kind_t* k) {
    const sm64ds_background_buffers_t b = {k->v, k->idx, k->tex, k->mat, k->fm,
                                           k->vcap, k->fcap, k->tcap};
    sat_result_t r = sm64ds_background_init(&k->prop, k->model, &b);
    if (r != SAT_OK) return r;
    k->prop.instance.pass = SM64DS_ACTOR_PASS;
    k->prop.instance.cull_backfaces = k->one_sided ? SAT_SCENE3D_CULL_SCREEN : 0;
    for (uint32_t i = 0; i < k->count; ++i) {
        k->pos[i] = k->positions[i];
        k->yaw_live[i] = k->yaw_deg[i];
        k->st[i] = SM64DS_ACTOR_IDLE;
        k->tm[i] = 0;
        if (k->behavior == SM64DS_ACTOR_STAR) k->st[i] = SM64DS_ACTOR_HIDDEN;
        r = actor_world(k, i);
        if (r != SAT_OK) return r;
    }
    r = sat_scene3d_material_programs_init(&k->programs, k->mat, k->tcap, k->prog, k->tcap);
    if (r != SAT_OK) return r;
    r = sat_scene3d_instance_binding_init(&k->binding, &k->prop.mesh, k->mat, k->tcap, k->fm);
    if (r != SAT_OK) return r;
    k->binding.programs = &k->programs;
    k->prop.instance.validated_binding = &k->binding;
    return SAT_OK;
}

sat_result_t sm64ds_actor_kind_submit(
    sm64ds_actor_kind_t* k, sat_scene_t* scene, const sat_vec3_t* eye,
    const sat_vec3_t* fwd, const sat_vec3_t* right, uint32_t face_limit,
    const sat_vec3_t* player_feet, uint16_t player_height) {
    k->drawn = 0;
    if (k->behavior == SM64DS_ACTOR_BOSS && k->hp_left == 0 && !k->defeated && k->hp) k->hp_left = k->hp;
    for (uint32_t i = 0; i < k->count; ++i) {
        if (k->st[i] == SM64DS_ACTOR_DEAD || k->st[i] == SM64DS_ACTOR_HIDDEN) continue;
        if (k->st[i] == SM64DS_ACTOR_FUSE && (k->tm[i] & 8u)) continue;   /* flash while the fuse burns */
        const sat_vec3_t pos = k->pos[i];
        if (player_feet) {
            /* Coarse vertical cull against Mario's 12-unit body. */
            const int32_t ddy = pos.y - player_feet->y;
            if (ddy > (int32_t)player_height + 24 * ONE || ddy < -24 * ONE) continue;
        }
        const int32_t dx = pos.x - eye->x, dz = pos.z - eye->z;
        const int32_t depth = sat_fx16_mul(dx, fwd->x) + sat_fx16_mul(dz, fwd->z);
        if (depth < 2 * ONE || depth > (int32_t)k->max_depth * ONE) continue;
        const int32_t lat = sat_fx16_mul(dx, right->x) + sat_fx16_mul(dz, right->z);
        if (sat_fx16_abs(lat) > depth + 16 * ONE) continue;
        if (scene->faces.count + k->fcap > face_limit) continue;   /* scene full: drop this one */
        k->prop.world = k->worlds[i];
        const sat_result_t r = sat_scene_submit_instance(
            scene, &k->prop.instance, SAT_SCENE3D_SLOT_INHERIT, k->proj, k->w);
        if (r != SAT_OK) return r;
        ++k->drawn;
    }
    return SAT_OK;
}

#define ACTIVE_RANGE (120 * ONE)
#define RESPAWN_STEPS 300u
#define HURT_STEPS 45u

/* Update/draw culling: a placement farther than this from Mario is skipped in
 * both update and submit. Actors that far away cannot touch him and are not
 * worth a matrix build per 60 Hz step. */
#define ACTOR_UPDATE_RANGE (200 * ONE)
/* Pickups (coins, stars) only matter within a body's reach; spinning them
 * from 200 units away is pure waste. */
#define PICKUP_UPDATE_RANGE (48 * ONE)

/* Cheap early-out shared by every per-placement update loop: skip placements
 * farther than `range` from Mario (XZ only). Actors that far away cannot touch
 * him, and skipping them avoids a matrix build per 60 Hz step. */
static int actor_out_of_range(const sat_vec3_t* pos, const sat_vec3_t* feet,
                              int32_t range) {
    const int32_t dx = pos->x - feet->x, dz = pos->z - feet->z;
    return dx > range || dx < -range || dz > range || dz < -range;
}

/* Where the last boss fell. A star kind with `star_bit` spawns there when it
 * unlocks, matching the DS (the star appears at the boss's defeat spot). */
static sat_vec3_t s_boss_death_pos;
static uint8_t s_boss_death_valid;

static void push_away(sm64ds_actor_hit_t* hit, int32_t dx, int32_t dz, int32_t dist) {
    /* dx/dz point from the actor to the player; push along them. */
    ++hit->count;
    if (!hit->damage) hit->damage = 1;
    if (dist > 0) {
        hit->push_x += (int32_t)(((int64_t)dx * ONE) / dist);
        hit->push_z += (int32_t)(((int64_t)dz * ONE) / dist);
    }
}

static void update_boss(sm64ds_actor_kind_t* k, const sm64ds_collision_t* col,
                        const sm64ds_player_t* pl, sm64ds_actor_hit_t* hit) {
    if (k->defeated) return;
    for (uint32_t i = 0; i < k->count; ++i) {
        if (k->st[i] == SM64DS_ACTOR_DEAD) continue;
        if (k->st[i] == SM64DS_ACTOR_STUNNED) {
            /* Stunned: a stomp on the stunned boss still counts. */
            if (--k->tm[i] == 0) k->st[i] = SM64DS_ACTOR_IDLE;
            const sat_vec3_t* feet = &pl->feet;
            const int32_t dx = feet->x - k->pos[i].x, dz = feet->z - k->pos[i].z;
            const int32_t dy = feet->y - k->pos[i].y;
            const int32_t ax = dx >> 8, az = dz >> 8;
            const int32_t dist = (int32_t)sat_isqrt32((uint32_t)(ax * ax + az * az)) << 8;
            if (dist < k->radius && dy > k->top && pl->velocity_y < 0) {
                hit->bounce = 1;
                if (--k->hp_left == 0) {
                    k->defeated = 1;
                    k->st[i] = SM64DS_ACTOR_DEAD;
                    hit->boss_defeated = 1;
                    s_boss_death_pos = k->pos[i];
                    s_boss_death_valid = 1;
                    if (k->unlock) *(uint8_t*)k->unlock = 1;
                } else {
                    k->st[i] = SM64DS_ACTOR_STUNNED;
                    k->tm[i] = k->stun_steps ? k->stun_steps : 90;
                }
            }
            continue;
        }
        if (k->st[i] == SM64DS_ACTOR_FLYING) {   /* thrown: ballistics */
            k->pos[i].x += k->vx[i];
            k->pos[i].z += k->vz[i];
            k->vy[i] -= ONE / 8;
            k->pos[i].y += k->vy[i];
            int32_t h;
            if (k->vy[i] <= 0 && sm64ds_floor(col, k->pos[i].x, k->pos[i].z,
                                              k->pos[i].y + ONE / 4, &h) &&
                k->pos[i].y <= h + ONE / 8) {
                k->pos[i].y = h; k->vy[i] = 0; k->vx[i] = 0; k->vz[i] = 0;
                k->st[i] = SM64DS_ACTOR_STUNNED;
                k->tm[i] = k->stun_steps ? k->stun_steps : 90;
                /* A thrown boss hurts other actors nearby (chain reaction). */
                if (k->hp_left > 0 && k->radius > 0) hit->bounce = hit->bounce;
            }
            k->yaw_live[i] = (int16_t)((k->yaw_live[i] + 10) % 360);
            (void)actor_world(k, i);
            continue;
        }
        if (k->st[i] == SM64DS_ACTOR_HELD) {     /* carried: follow Mario */
            const sat_vec3_t* feet = &pl->feet;
            const int32_t h = feet->y + 20 * ONE;
            k->pos[i].x = feet->x;
            k->pos[i].z = feet->z;
            k->pos[i].y = h;
            k->yaw_live[i] = pl->held_yaw;
            (void)actor_world(k, i);
            continue;
        }
        const sat_vec3_t* feet = &pl->feet;
        const int32_t dx = feet->x - k->pos[i].x, dz = feet->z - k->pos[i].z;
        const int32_t dy = feet->y - k->pos[i].y;
        if (dx > ACTIVE_RANGE || dx < -ACTIVE_RANGE || dz > ACTIVE_RANGE || dz < -ACTIVE_RANGE) continue;
        const int32_t ax = dx >> 8, az = dz >> 8;
        const int32_t dist = (int32_t)sat_isqrt32((uint32_t)(ax * ax + az * az)) << 8;
        if (dist < k->radius && dy > -8 * ONE && dy < k->top + 12 * ONE) {
            if (dy > k->top && pl->velocity_y < 0) {          /* stomped from above */
                hit->bounce = 1;
                if (--k->hp_left == 0) {
                    k->defeated = 1;
                    k->st[i] = SM64DS_ACTOR_DEAD;
                    hit->boss_defeated = 1;
                    s_boss_death_pos = k->pos[i];
                    s_boss_death_valid = 1;
                    if (k->unlock) *(uint8_t*)k->unlock = 1;
                } else {
                    k->st[i] = SM64DS_ACTOR_STUNNED;
                    k->tm[i] = k->stun_steps ? k->stun_steps : 90;
                }
            } else if (!pl->invuln) {                        /* bumped from the side */
                push_away(hit, dx, dz, dist);
            }
            continue;
        }
        if (dist >= k->range || dist == 0) { k->st[i] = SM64DS_ACTOR_IDLE; continue; }
        k->st[i] = SM64DS_ACTOR_CHASING;
        const int32_t nx = k->pos[i].x + (int32_t)(((int64_t)dx * k->speed) / dist);
        const int32_t nz = k->pos[i].z + (int32_t)(((int64_t)dz * k->speed) / dist);
        int32_t h;
        /* King Bob-omb rolls down the hill after Mario, so he may drop far in
         * one step (unlike the small chasers). Clamp only absurd teleports. */
        if (sm64ds_floor(col, nx, nz, k->pos[i].y + 8 * ONE, &h) &&
            h - k->pos[i].y < 6 * ONE && k->pos[i].y - h < 96 * ONE) {
            k->pos[i].x = nx; k->pos[i].z = nz; k->pos[i].y = h;
        }
        k->yaw_live[i] = (int16_t)(((int32_t)sat_atan2_16(dx, dz) * 360) >> 16);
        (void)actor_world(k, i);
    }
}

/* Grab/hold/throw the boss: `grab` edge-triggered picks up a stunned or idle
 * boss in front of Mario; `throw` releases it with an arc and counts one hit
 * (three throws beat the three-star boss). */
void sm64ds_actor_grab(sm64ds_actor_kind_t* k, const sm64ds_player_t* pl, uint8_t grab, uint8_t throw, sm64ds_actor_hit_t* hit) {
    if (k->behavior != SM64DS_ACTOR_BOSS || k->defeated) return;
    for (uint32_t i = 0; i < k->count; ++i) {
        if (k->st[i] == SM64DS_ACTOR_DEAD) continue;
        const sat_vec3_t* feet = &pl->feet;
        const int32_t dx = k->pos[i].x - feet->x, dz = k->pos[i].z - feet->z;
        const int32_t ax = dx >> 8, az = dz >> 8;
        const int32_t dist = (int32_t)sat_isqrt32((uint32_t)(ax * ax + az * az)) << 8;
        if (k->st[i] == SM64DS_ACTOR_HELD) {
            if (throw) {
                /* Launch along Mario's facing, with an upward arc. */
                const int32_t s = sat_sin_deg(pl->held_yaw * ONE);
                const int32_t c = sat_cos_deg(pl->held_yaw * ONE);
                k->vx[i] = sat_fx16_mul(s, 6 * ONE);
                k->vz[i] = sat_fx16_mul(c, 6 * ONE);
                k->vy[i] = 5 * ONE;
                k->pos[i].x = feet->x + sat_fx16_mul(s, 12 * ONE);
                k->pos[i].z = feet->z + sat_fx16_mul(c, 12 * ONE);
                k->pos[i].y = feet->y + 16 * ONE;
                k->st[i] = SM64DS_ACTOR_FLYING;
                if (--k->hp_left == 0) {
                    k->defeated = 1;
                    k->st[i] = SM64DS_ACTOR_DEAD;
                    hit->boss_defeated = 1;
                    s_boss_death_pos = k->pos[i];
                    s_boss_death_valid = 1;
                    /* The star kind waits on this byte (`.unlock`). */
                    if (k->unlock) *(uint8_t*)k->unlock = 1;
                }
                (void)actor_world(k, i);
                return;
            }
            continue;
        }
        if (grab && (k->st[i] == SM64DS_ACTOR_STUNNED || k->st[i] == SM64DS_ACTOR_IDLE) &&
            dist < k->radius + 8 * ONE && pl->feet.y + 8 * ONE > k->pos[i].y &&
            pl->feet.y - 8 * ONE < k->pos[i].y + k->top) {
            k->st[i] = SM64DS_ACTOR_HELD;
            k->vy[i] = k->vx[i] = k->vz[i] = 0;
            return;
        }
    }
}

uint8_t sm64ds_actor_held(const sm64ds_actor_kind_t* k) {
    if (k->behavior != SM64DS_ACTOR_BOSS) return 0;
    for (uint32_t i = 0; i < k->count; ++i)
        if (k->st[i] == SM64DS_ACTOR_HELD) return 1;
    return 0;
}

static void update_star(sm64ds_actor_kind_t* k, const sm64ds_collision_t* col,
                        const sm64ds_player_t* pl, sm64ds_actor_hit_t* hit) {
    /* The boss unlock pointer is the boss kind's `defeated` byte (generated
     * `.unlock`); the boss update sets it when hp reaches 0. A star with no
     * unlock (star_bit only) is always visible. */
    const int unlocked = !k->unlock || *k->unlock;
    const int32_t far = (int32_t)k->max_depth * ONE;
    for (uint32_t i = 0; i < k->count; ++i) {
        if (k->st[i] == SM64DS_ACTOR_DEAD) continue;           /* collected */
        if (k->st[i] == SM64DS_ACTOR_HIDDEN) {
            if (!unlocked) continue;
            k->st[i] = SM64DS_ACTOR_IDLE;
        }
        if (k->star_bit && k->tm[i] == 0) {
            /* Dropped at the boss defeat spot, once. */
            if (s_boss_death_valid) {
                k->pos[i] = s_boss_death_pos;
                k->pos[i].y += (int32_t)(8*ONE);
            }
            k->tm[i] = 1;
            (void)actor_world(k, i);
        }
        /* A dropped star homes slowly toward Mario so he can always reach it
         * on foot (the DS star bobs in place; this is a port concession). */
        if (k->star_bit && k->tm[i] == 1) {
            const int32_t hdx = pl->feet.x - k->pos[i].x;
            const int32_t hdz = pl->feet.z - k->pos[i].z;
            const int32_t adx = hdx < 0 ? -hdx : hdx;
            const int32_t adz = hdz < 0 ? -hdz : hdz;
            if (adx > 4 * ONE || adz > 4 * ONE) {
                k->pos[i].x += adx > adz ? (hdx < 0 ? -ONE / 2 : ONE / 2) : 0;
                k->pos[i].z += adz >= adx ? (hdz < 0 ? -ONE / 2 : ONE / 2) : 0;
                int32_t fh;
                if (sm64ds_floor(col, k->pos[i].x, k->pos[i].z,
                                 k->pos[i].y + 8 * ONE, &fh) &&
                    fh - k->pos[i].y < 6 * ONE && k->pos[i].y - fh < 24 * ONE)
                    k->pos[i].y = fh;
                (void)actor_world(k, i);
            }
        }
        const int32_t dx = pl->feet.x - k->pos[i].x, dz = pl->feet.z - k->pos[i].z;
        const int32_t dy = pl->feet.y - k->pos[i].y;
        if (dx < k->radius && dx > -k->radius && dz < k->radius && dz > -k->radius &&
            dy < 32 * ONE && dy > -24 * ONE) {
            k->st[i] = SM64DS_ACTOR_DEAD;
            ++hit->stars;
            /* Star 1 of Bob-omb Battlefield opens the exit: the castle side
             * learns the course is cleared through the warp arg's star bits
             * (see sm64ds_warp_arg_t::star_bits). */
            hit->star_index = 1;
            hit->star_bit = 1u << (k->star_bit ? (k->star_bit - 1u) : 0u);
        }
        k->yaw_live[i] = (int16_t)((k->yaw_live[i] + 3) % 360);   /* spin */
        (void)actor_world(k, i);
    }
}

static void update_coin(sm64ds_actor_kind_t* k, const sm64ds_player_t* pl, sm64ds_actor_hit_t* hit) {
    const sat_vec3_t* feet = &pl->feet;
    for (uint32_t i = 0; i < k->count; ++i) {
        if (k->st[i] == SM64DS_ACTOR_DEAD) continue;           /* collected */
        if (actor_out_of_range(&k->pos[i], feet, PICKUP_UPDATE_RANGE)) continue;   /* spin only nearby */
        const int32_t dx = feet->x - k->pos[i].x, dz = feet->z - k->pos[i].z;
        const int32_t dy = feet->y - k->pos[i].y;
        if (dx < k->radius && dx > -k->radius && dz < k->radius && dz > -k->radius &&
            dy < 20 * ONE && dy > -12 * ONE) {
            k->st[i] = SM64DS_ACTOR_DEAD;
            hit->coins = (uint8_t)(hit->coins + (k->coin_value ? k->coin_value : 1));
            continue;
        }
        k->yaw_live[i] = (int16_t)((k->yaw_live[i] + 6) % 360);   /* spin */
        (void)actor_world(k, i);
    }
}

static void update_wanwan(sm64ds_actor_kind_t* k, const sm64ds_collision_t* col,
                          const sm64ds_player_t* pl, sm64ds_actor_hit_t* hit) {
    for (uint32_t i = 0; i < k->count; ++i) {
        if (k->st[i] == SM64DS_ACTOR_DEAD) continue;
        const int32_t dx = pl->feet.x - k->pos[i].x, dz = pl->feet.z - k->pos[i].z;
        const int32_t dy = pl->feet.y - k->pos[i].y;
        const int32_t ax = dx >> 8, az = dz >> 8;
        const int32_t dist = (int32_t)sat_isqrt32((uint32_t)(ax * ax + az * az)) << 8;
        if (dist < k->radius && dy < 24 * ONE && dy > -16 * ONE) {
            if (!pl->invuln) push_away(hit, dx, dz, dist);
            continue;
        }
        if (dist >= k->range || dist == 0) { k->st[i] = SM64DS_ACTOR_IDLE; continue; }
        k->st[i] = SM64DS_ACTOR_CHASING;
        /* Chain Chomp lunges straight at Mario, ignoring floors (it flies). */
        const int32_t nx = k->pos[i].x + (int32_t)(((int64_t)dx * k->speed) / dist);
        const int32_t nz = k->pos[i].z + (int32_t)(((int64_t)dz * k->speed) / dist);
        int32_t h;
        if (sm64ds_floor(col, nx, nz, k->pos[i].y + 16 * ONE, &h) &&
            h - k->pos[i].y < 24 * ONE && k->pos[i].y - h < 32 * ONE) {
            k->pos[i].x = nx; k->pos[i].z = nz; k->pos[i].y = h;
        } else {
            k->pos[i].x = nx; k->pos[i].z = nz;   /* airborne lunge */
        }
        k->yaw_live[i] = (int16_t)(((int32_t)sat_atan2_16(dx, dz) * 360) >> 16);
        (void)actor_world(k, i);
    }
}

static void update_ironball(sm64ds_actor_kind_t* k, const sm64ds_collision_t* col,
                            const sm64ds_player_t* pl, sm64ds_actor_hit_t* hit) {
    (void)col;
    const sat_vec3_t* feet = &pl->feet;
    for (uint32_t i = 0; i < k->count; ++i) {
        if (k->st[i] == SM64DS_ACTOR_DEAD) continue;
        if (actor_out_of_range(&k->pos[i], feet, PICKUP_UPDATE_RANGE)) continue;
        const int32_t dx = feet->x - k->pos[i].x, dz = feet->z - k->pos[i].z;
        const int32_t dy = feet->y - k->pos[i].y;
        const int32_t ax = dx >> 8, az = dz >> 8;
        const int32_t dist = (int32_t)sat_isqrt32((uint32_t)(ax * ax + az * az)) << 8;
        if (dist < k->radius && dy < 20 * ONE && dy > -16 * ONE) {
            if (!pl->invuln) push_away(hit, dx, dz, dist);
            continue;
        }
        if (dist >= k->range || dist == 0) continue;
        /* Rolling: constant velocity toward Mario, no floor follow (the
         * spawner aims it down the path). */
        if (k->tm[i] == 0) k->tm[i] = 1;   /* mark as active */
        k->st[i] = SM64DS_ACTOR_CHASING;
        const int32_t nx = k->pos[i].x + (int32_t)(((int64_t)dx * k->speed) / dist);
        const int32_t nz = k->pos[i].z + (int32_t)(((int64_t)dz * k->speed) / dist);
        k->pos[i].x = nx; k->pos[i].z = nz;
        k->yaw_live[i] = (int16_t)((k->yaw_live[i] + 12) % 360);   /* spin */
        (void)actor_world(k, i);
    }
}

void sm64ds_actor_kind_update(sm64ds_actor_kind_t* k, const sm64ds_collision_t* col,
                              const sm64ds_player_t* pl, sm64ds_actor_hit_t* hit) {
    if (k->behavior == SM64DS_ACTOR_BOSS) { update_boss(k, col, pl, hit); return; }
    if (k->behavior == SM64DS_ACTOR_STAR) { update_star(k, col, pl, hit); return; }
    if (k->behavior == SM64DS_ACTOR_COIN) { update_coin(k, pl, hit); return; }
    if (k->behavior == SM64DS_ACTOR_WANWAN) { update_wanwan(k, col, pl, hit); return; }
    if (k->behavior == SM64DS_ACTOR_IRONBALL) { update_ironball(k, col, pl, hit); return; }
    const sat_vec3_t* feet = &pl->feet;
        if (k->behavior != SM64DS_ACTOR_CHASER) return;
        for (uint32_t i = 0; i < k->count; ++i) {
            if (k->st[i] == SM64DS_ACTOR_DEAD) {
                if (--k->tm[i] == 0) {
                    k->pos[i] = k->positions[i];
                    k->yaw_live[i] = k->yaw_deg[i];
                    k->st[i] = SM64DS_ACTOR_IDLE;
                    (void)actor_world(k, i);
                }
                continue;
            }
            if (actor_out_of_range(&k->pos[i], feet, ACTOR_UPDATE_RANGE)) { k->st[i] = SM64DS_ACTOR_IDLE; continue; }
        const int32_t dx = feet->x - k->pos[i].x, dz = feet->z - k->pos[i].z;
        const int32_t dy = feet->y - k->pos[i].y;
        const int near_y = dy < 12 * ONE && dy > -12 * ONE;
        if (k->st[i] == SM64DS_ACTOR_FUSE) {
            if (--k->tm[i] == 0) {
                const int32_t ex = dx >> 8, ez = dz >> 8;
                const int32_t d = (int32_t)sat_isqrt32((uint32_t)(ex * ex + ez * ez)) << 8;
                if (d < k->blast && near_y && !pl->invuln) push_away(hit, dx, dz, d);
                k->st[i] = SM64DS_ACTOR_DEAD;
                k->tm[i] = RESPAWN_STEPS;
            }
            continue;
        }
        if (dx > ACTIVE_RANGE || dx < -ACTIVE_RANGE || dz > ACTIVE_RANGE || dz < -ACTIVE_RANGE) continue;
        const int32_t ax = dx >> 8, az = dz >> 8;           /* 8.8 for the square */
        const int32_t dist = (int32_t)sat_isqrt32((uint32_t)(ax * ax + az * az)) << 8;
        if (dist < k->radius && near_y) {
            if (!pl->invuln) {
                if (k->fuse_steps) {
                    k->st[i] = SM64DS_ACTOR_FUSE;
                    k->tm[i] = k->fuse_steps;
                } else {
                    push_away(hit, dx, dz, dist);
                    k->st[i] = SM64DS_ACTOR_DEAD;
                    k->tm[i] = RESPAWN_STEPS;
                }
            }
            continue;
        }
        if (dist >= k->range || dist == 0) { k->st[i] = SM64DS_ACTOR_IDLE; continue; }
        k->st[i] = SM64DS_ACTOR_CHASING;
        const int32_t nx = k->pos[i].x + (int32_t)(((int64_t)dx * k->speed) / dist);
        const int32_t nz = k->pos[i].z + (int32_t)(((int64_t)dz * k->speed) / dist);
        int32_t h;
        if (sm64ds_floor(col, nx, nz, k->pos[i].y + 8 * ONE, &h) &&
            h - k->pos[i].y < 6 * ONE && k->pos[i].y - h < 24 * ONE) {
            k->pos[i].x = nx; k->pos[i].z = nz; k->pos[i].y = h;
        }
        k->yaw_live[i] = (int16_t)(((int32_t)sat_atan2_16(dx, dz) * 360) >> 16);
        (void)actor_world(k, i);
    }
}
