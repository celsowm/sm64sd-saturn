"""Build conservative candidate planes from the generated fixed-point mesh."""
import math


def support_planes(vertices, faces):
    """Return (face index, upward 16.16 normal) for walkable planar faces.

    The world transform of this castle mesh is identity. Reject nonplanar
    quads and degenerate or steep faces; runtime still checks which side of
    each plane contains the camera and every actor vertex.
    """
    points = [tuple(round(v*65536) for v in p) for p in vertices]
    result = []
    for index, face in enumerate(faces):
        p0, p1, p2, p3 = (points[v] for v in face)
        a = [p1[i]-p0[i] for i in range(3)]
        b = [p2[i]-p0[i] for i in range(3)]
        n = [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]
        length = math.sqrt(sum(v*v for v in n))
        if not length or abs(n[1]) < length*0.4:
            continue
        if face[2] != face[3]:
            dist = abs(sum(n[i]*(p3[i]-p0[i]) for i in range(3))) / length
            diag = math.sqrt(sum((p2[i]-p0[i])**2 for i in range(3)))
            if dist > 65536*0.35 or dist > diag*0.02:
                continue
        direction = 1 if n[1]>0 else -1
        result.append((index, tuple(round(direction*v*65536/length) for v in n)))
    return result
