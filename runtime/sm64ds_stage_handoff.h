#pragma once

#include <stdint.h>

#include <saturn/core.h>
#include <saturn/font.h>
#include <saturn/loader.h>
#include <saturn/vdp1.h>
#include <saturn/vdp2.h>

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

/* A "NOW LOADING" progress screen for stage transitions (sat_exec). Uses
 * lib-saturn's sat_loading_screen_t progress bar plus a title/caption drawn
 * with an 8x8 indexed8 font. Call sm64ds_loading_init once after sat_init;
 * call sm64ds_loading_frame inside the transition (between begin/end frame).
 *
 * The bar draws with RGB555 colours via sat_draw_rect_screen, so no CRAM
 * bank juggling is needed for standard-resolution output. */
typedef struct {
    sat_loading_screen_t bar;
    sat_ascii_font_t font;
    uint8_t ready;
} sm64ds_loading_t;

/* Initialise the loading screen's font and bar. Safe to call before the CD
 * is mounted. The font palette lives in CRAM bank 6, which neither the
 * castle (HUD bank 3) nor the intro (2D bank 5, HUD bank 7) uses, so the
 * glyph colours never clobber a live stage palette. */
static inline void sm64ds_loading_init(sm64ds_loading_t* l) {
    if (l->ready) return;
    (void)sat_ascii_font_init_8x8_indexed8(&l->font, SAT_RGB555(31, 31, 31),
                                           SAT_RGB555(2, 3, 6), 6u);
    sat_loading_screen_default(&l->bar);
    l->bar.background = SAT_RGB555(2, 3, 6);
    l->bar.frame     = SAT_RGB555(31, 31, 31);
    l->bar.track     = SAT_RGB555(4, 8, 16);
    l->bar.fill      = SAT_RGB555(10, 24, 26);
    l->bar.x = 34; l->bar.y = 150; l->bar.width = 252u; l->bar.height = 9u;
    l->ready = 1u;
}

/* Draw one loading frame: dark background, title, the target stage name,
 * and the progress bar at `percent` (0..100). Call between sat_begin_frame
 * and sat_end_frame. */
static inline void sm64ds_loading_frame(sm64ds_loading_t* l,
                                        const char* title, const char* stage,
                                        uint16_t percent) {
    if (percent > 100u) percent = 100u;
    const uint16_t w = 320u, h = 224u;
    const int cx = (int)(w / 2u);
    (void)sat_draw_rect_screen(0, 0, (uint16_t)w, (uint16_t)h, l->bar.background);
    (void)sat_ascii_font_draw_text_screen_centered_indexed8(
        &l->font, title, cx, 96, 8, 0u, 0u);
    (void)sat_ascii_font_draw_text_screen_centered_indexed8(
        &l->font, stage, cx, 116, 8, 0u, 0u);
    (void)sat_loading_screen_draw_bar(&l->bar, percent);
}

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
