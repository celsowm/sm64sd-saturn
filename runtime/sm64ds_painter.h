#ifndef SM64DS_PAINTER_H
#define SM64DS_PAINTER_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Native screen coordinates and positive 16.16 camera depth. */
typedef struct {
    int16_t x, y;
    int32_t depth;
} sm64ds_painter_vertex_t;

typedef enum {
    SM64DS_PAINTER_DISJOINT,
    SM64DS_PAINTER_A_BEHIND,
    SM64DS_PAINTER_A_IN_FRONT,
    SM64DS_PAINTER_AMBIGUOUS
} sm64ds_painter_relation_t;

/* Classify two projected triangles over their screen-space intersection.
 * A crossing, nearly equal depths, invalid input, or degenerate triangle
 * is ambiguous. This geometric test does not account for VDP1 coverage,
 * clipped faces, sort interactions with third faces, or textured quads. */
sm64ds_painter_relation_t sm64ds_painter_compare_triangles(
    const sm64ds_painter_vertex_t a[3], const sm64ds_painter_vertex_t b[3]);

/* True only if an edge separates both projected triangles by more than the
 * requested pixel padding. Degenerate triangles conservatively return 0.
 * Depth is ignored; callers must separately handle near-plane clipping. */
int sm64ds_painter_triangles_separated(const sm64ds_painter_vertex_t a[3],
                                       const sm64ds_painter_vertex_t b[3],
                                       uint16_t padding);

typedef struct { uint32_t low, high; uint8_t shift; } sm64ds_painter_bucket_plan_t;
/* Mirror LibSaturn's grouped painter bucket width for one pass. Returns 0
 * for missing groups or the SDK's >8-group global fallback. The plan remains
 * valid only while group counts and depth extrema remain unchanged. */
int sm64ds_painter_bucket_plan(const uint32_t *keys,uint16_t count,uint8_t group,
                               sm64ds_painter_bucket_plan_t *out);

#ifdef __cplusplus
}
#endif

#endif
