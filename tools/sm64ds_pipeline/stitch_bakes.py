"""Experimentally harmonize baked texels along shared split-triangle edges."""
from collections import defaultdict
from .textures import BakedTexture


def stitch_bakes(faces, origins, bakes, source_faces, cross_sources=()):
    """Average shared edge texels within selected original source faces.

    Only opaque triangular bakes with exactly shared vertex indices are
    touched. Adjacent texel intervals are unioned even at different bake
    resolutions. Interior texels retain their original sampled colors.
    """
    if not (len(faces) == len(origins) == len(bakes)):
        raise ValueError('face, origin and bake arrays must have equal length')
    selected = set(source_faces)
    pairs = {tuple(sorted(pair)) for pair in cross_sources}
    if any(len(pair) != 2 or pair[0] == pair[1] for pair in pairs):
        raise ValueError('cross-source pairs must contain two different source faces')
    included = selected | {source for pair in pairs for source in pair}
    if included - set(origins):
        raise ValueError('stitch source is absent from generated faces')
    edges = defaultdict(list)
    for face_index, (face, origin, bake) in enumerate(zip(faces, origins, bakes)):
        if origin not in included or len(face) != 4 or face[2] != face[3]:
            continue
        if bake.width != bake.height:
            raise ValueError('edge stitching requires square bakes')
        n = bake.width
        # Pixel sequences follow A->B, B->C, C->A respectively.
        sequences = ([(x, 0) for x in range(n)], [(n-1, y) for y in range(n)],
                     [(0, y) for y in range(n-1, -1, -1)])
        for (a, b), sequence in zip(((face[0], face[1]), (face[1], face[2]),
                                      (face[2], face[0])), sequences):
            if a == b:
                continue
            if a > b:
                sequence = list(reversed(sequence))
            if origin in selected:
                edges[(('same', origin), min(a, b), max(a, b))].append((face_index, sequence))
            for pair in pairs:
                if origin in pair:
                    edges[(('cross', *pair), min(a, b), max(a, b))].append((face_index, sequence))

    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        a, b = find(a), find(b)
        if a != b:
            parent[b] = a

    for participants in edges.values():
        if len(participants) != 2:
            continue
        (fa, aa), (fb, bb) = participants
        if origins[fa] != origins[fb] and tuple(sorted((origins[fa], origins[fb]))) not in pairs:
            continue
        if origins[fa] == origins[fb] and origins[fa] not in selected:
            continue
        na, nb = len(aa), len(bb)
        if any(bakes[f].rgba[y*bakes[f].width+x][3] != 255
               for f, seq in participants for x, y in seq):
            continue
        for i, (ax, ay) in enumerate(aa):
            for j, (bx, by) in enumerate(bb):
                if i*nb < (j+1)*na and j*na < (i+1)*nb:
                    union((fa, ay*na+ax), (fb, by*nb+bx))


    groups = defaultdict(list)
    for node in parent:
        groups[find(node)].append(node)
    output = [list(b.rgba) for b in bakes]
    for nodes in groups.values():
        rgba = tuple((sum(bakes[f].rgba[p][channel] for f, p in nodes)+len(nodes)//2)//len(nodes)
                     for channel in range(4))
        for face_index, pixel in nodes:
            output[face_index][pixel] = rgba
    return [BakedTexture(b.width, b.height, tuple(pixels)) for b, pixels in zip(bakes, output)]
