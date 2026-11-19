"""Choose higher-resolution static face bakes within a fixed pixel budget."""
import heapq
import math
from .textures import bake_face, index_bakes, index_bakes_lut4
from .stitch_bakes import stitch_bakes


def adaptive_bakes(textures, uvs, *, high_face_limit=32, byte_budget=96*1024,
                   samples=1, priorities=None, stitch_faces=None,
                   stitch_origins=None, stitch_sources=(), stitch_cross_sources=()):
    """Select 16x16 bakes that best recover color detail lost at 8x8.

    Candidate error compares the 16x16 source sample with nearest upscaled
    8x8, optionally weighted by per-face importance. Both sizes can use
    filtered sampling and share a palette selected from the 8x8 reference.
    Budget is evaluated after palette quantization and deduplication;
    if the chosen set does not fit, drop the lowest scoring candidates. Stable
    face-index tie breaking keeps asset builds deterministic.
    """
    if len(textures)!=len(uvs) or high_face_limit<0 or byte_budget<=0 or (priorities is not None and len(priorities)!=len(uvs)):
        raise ValueError('invalid adaptive bake input')
    if priorities is not None and any(p<0 for p in priorities):raise ValueError('negative face priority')
    low=[bake_face(tex,uv,8,samples=samples) for tex,uv in zip(textures,uvs)]
    candidates=[]
    for i,(tex,uv) in enumerate(zip(textures,uvs)):
        high=bake_face(tex,uv,16,samples=samples)
        error=0
        for y in range(16):
            for x in range(16):
                a=high.rgba[y*16+x];b=low[i].rgba[(y//2)*8+x//2]
                error+=sum((a[k]-b[k])**2 for k in range(4))
        score=error*(priorities[i] if priorities is not None else 1)
        if score:candidates.append((score,i,high))
    candidates.sort(key=lambda x:(-x[0],x[1]))
    chosen=candidates[:high_face_limit]
    while True:
        bakes=list(low)
        for _,i,high in chosen:bakes[i]=high
        if stitch_sources or stitch_cross_sources:
            bakes=stitch_bakes(stitch_faces,stitch_origins,bakes,stitch_sources,stitch_cross_sources)
        indexed,palette,face_textures=index_bakes(bakes,reference_bakes=low)
        cost=sum(len(t.pixels) for t in indexed)
        if cost<=byte_budget:return indexed,palette,face_textures,[i for _,i,_ in chosen]
        if not chosen:raise ValueError(f'8x8 castle bakes exceed {byte_budget} bytes')
        if stitch_sources or stitch_cross_sources:
            # Stitching can change several neighboring tiles per removal.
            chosen=chosen[:len(chosen)//2]
        else:
            # A removed 16x16 tile frees at most 256 bytes. Retry with the
            # closest prefix that could fit, accounting for tile sharing.
            remove=(cost-byte_budget+255)//256
            chosen=chosen[:max(0,len(chosen)-remove)]


_W_SIZES = (8, 16, 24, 32, 48, 64)
_H_SIZES = (8, 12, 16, 24, 32, 48, 64)


def _quantize_dim(span: float, options: tuple[int, ...], max_size: int) -> int:
    cap = min(max_size, options[-1])
    for s in options:
        if s >= cap:
            return cap
        if span <= s * 1.15:
            return s
    return cap


def _uv_spans(uv) -> tuple[float, float]:
    du = max(
        math.hypot(uv[1][0] - uv[0][0], uv[1][1] - uv[0][1]),
        math.hypot(uv[2][0] - uv[3][0], uv[2][1] - uv[3][1]),
    )
    dv = max(
        math.hypot(uv[3][0] - uv[0][0], uv[3][1] - uv[0][1]),
        math.hypot(uv[2][0] - uv[1][0], uv[2][1] - uv[1][1]),
    )
    return du, dv


def _size_ladder(du: float, dv: float, max_size: int) -> list[tuple[int, int]]:
    """Build an aspect-matched ladder of VDP1-legal (w, h) sizes from (8, 8) up."""
    tw = _quantize_dim(max(8.0, du), _W_SIZES, max_size)
    th = _quantize_dim(max(8.0, dv), _H_SIZES, max_size)
    ladder = [(8, 8)]
    # Step up along whichever axis is more undersampled until (tw, th) is reached.
    cw, ch = 8, 8
    while (cw, ch) != (tw, th):
        need_w = (du / cw) if cw < tw else 0.0
        need_h = (dv / ch) if ch < th else 0.0
        if need_w >= need_h and cw < tw:
            cw = next(s for s in _W_SIZES if s > cw)
        elif ch < th:
            ch = next(s for s in _H_SIZES if s > ch)
        else:
            break
        if (cw, ch) != ladder[-1]:
            ladder.append((cw, ch))
    return ladder


def _lut_groups(materials, colors):
    groups = []
    for i, mat in enumerate(materials):
        if colors is None:
            groups.append((mat, 2))
        else:
            c = colors[i]
            lum = sum(p[0] * 3.0 + p[1] * 4.0 + p[2] * 2.0 for p in c) / 36.0
            bucket = 0 if lum < 13.0 else (1 if lum < 24.0 else 2)
            groups.append((mat, bucket))
    return groups


def _lut4_vram_bytes(textures, lut_count: int) -> int:
    return lut_count * 32 + sum((len(t.pixels) + 7) & ~7 for t in textures)


def _tile_variance(tile) -> float:
    opaque = [p for p in tile.rgba if p[3] >= 128]
    if len(opaque) <= 1:
        return 0.0
    n = len(opaque)
    mr = sum(p[0] for p in opaque) / n
    mg = sum(p[1] for p in opaque) / n
    mb = sum(p[2] for p in opaque) / n
    var = sum((p[0] - mr) ** 2 + (p[1] - mg) ** 2 + (p[2] - mb) ** 2 for p in opaque) / n
    # Also reward alpha cutout edges (windows, fences, shadows).
    has_cutout = len(opaque) < len(tile.rgba)
    return math.sqrt(var) + (40.0 if has_cutout else 0.0)


def adaptive_lut4_bakes(sources, uvs, materials, *, colors=None, byte_budget=220 * 1024,
                        samples=4, priorities=None, face_areas=None, max_size=48):
    """Allocate non-square VDP1 LUT4 bakes matched to UV span, visual variance and budget.

    Uses per-(material, luminance-bucket) 16-color LUTs so every material and shade
    band gets dedicated RGB555 colors at half the VRAM cost of indexed8.
    """
    n = len(sources)
    if len(uvs) != n or len(materials) != n or byte_budget <= 0:
        raise ValueError('invalid adaptive LUT4 bake input')
    if colors is not None and len(colors) != n:
        raise ValueError('colors length must match face count')
    if priorities is not None and len(priorities) != n:
        raise ValueError('priorities length must match face count')
    if face_areas is not None and len(face_areas) != n:
        raise ValueError('face_areas length must match face count')

    groups = _lut_groups(materials, colors)
    n_luts = len(set(groups))
    lut_overhead = n_luts * 32

    # Probe visual detail once at 16x16 (or 1-sample fast probe) to measure variance & cutouts.
    ladders = []
    weights = []
    for i in range(n):
        du, dv = _uv_spans(uvs[i])
        col = colors[i] if colors is not None else None
        probe = bake_face(sources[i], uvs[i], 16, samples=1, colors=col)
        var = _tile_variance(probe)
        if var < 2.0:
            ladders.append([(8, 8)])
            weights.append(0.0)
            continue
        lad = _size_ladder(du, dv, max_size)
        ladders.append(lad)
        prio = float(priorities[i]) if priorities is not None else 1.0
        area_w = min(4.0, math.sqrt(max(1.0, face_areas[i]) / 120.0)) if face_areas is not None else 1.0
        # Dampen variance so subtle textured surfaces (grass, path, stone) still
        # earn crisp resolutions alongside high-contrast brick walls.
        weights.append((var ** 0.6) * max(0.5, area_w) * (1.0 + 0.15 * math.log1p(prio)))

    # Initial selection: start every face at ladder[0] = (8, 8), then greedily
    # upgrade faces with the highest (detail gain / byte cost) via a min-heap.
    tier = [0] * n
    spans = [_uv_spans(uvs[i]) for i in range(n)]

    def step_entry(i: int, step: int):
        du, dv = spans[i]
        w0, h0 = ladders[i][step]
        w1, h1 = ladders[i][step + 1]
        err0 = max(1.0, du / w0) * max(1.0, dv / h0)
        err1 = max(1.0, du / w1) * max(1.0, dv / h1)
        gain = max(0.1, err0 - err1) * weights[i]
        delta_bytes = ((w1 * h1 // 2 + 7) & ~7) - ((w0 * h0 // 2 + 7) & ~7)
        score = gain / max(8, delta_bytes)
        return (-score, i, step, delta_bytes)

    heap = []
    for i in range(n):
        if weights[i] > 0.0 and len(ladders[i]) > 1:
            heapq.heappush(heap, step_entry(i, 0))

    # Estimate raw budget assuming ~15% dedup headroom, then verify exact deduped VRAM.
    est_used = lut_overhead + n * 32
    est_cap = int(byte_budget * 1.15)
    applied = []
    while heap:
        neg_score, i, step, delta = heapq.heappop(heap)
        if est_used + delta <= est_cap:
            tier[i] = step + 1
            est_used += delta
            applied.append((neg_score, i, step))
            if tier[i] + 1 < len(ladders[i]):
                heapq.heappush(heap, step_entry(i, tier[i]))

    # Bake selected sizes (cache by (i, w, h) so trimming never re-bakes).
    bake_cache = {}
    def get_bake(i):
        w, h = ladders[i][tier[i]]
        key = (i, w, h)
        if key not in bake_cache:
            col = colors[i] if colors is not None else None
            bake_cache[key] = bake_face(sources[i], uvs[i], w, height=h, samples=samples, colors=col)
        return bake_cache[key]

    while True:
        bakes = [get_bake(i) for i in range(n)]
        textures, luts, lut_count, face_textures = index_bakes_lut4(bakes, groups=groups)
        cost = _lut4_vram_bytes(textures, lut_count)
        if cost <= byte_budget:
            sizes = [ladders[i][tier[i]] for i in range(n)]
            return textures, luts, lut_count, face_textures, sizes
        if not applied:
            raise ValueError(f'8x8 LUT4 castle bakes require {cost} bytes > {byte_budget} budget')
        # Roll back the lowest-scoring upgrades proportionally to the overshoot.
        excess = cost - byte_budget
        rolled = 0
        while applied and rolled < excess:
            _, idx, prev_step = applied.pop()
            w_cur, h_cur = ladders[idx][tier[idx]]
            w_prev, h_prev = ladders[idx][prev_step]
            tier[idx] = prev_step
            rolled += max(32, (w_cur * h_cur - w_prev * h_prev) // 2)

