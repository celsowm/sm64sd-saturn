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
    uint8_t reserved;
} sm64ds_warp_arg_t;
