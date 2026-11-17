"""Choose higher-resolution static face bakes within a fixed pixel budget."""
from .textures import bake_face, index_bakes


def adaptive_bakes(textures, uvs, *, high_face_limit=32, byte_budget=96*1024,
                   samples=1, priorities=None):
    """Select 16x16 bakes that best recover color detail lost at 8x8.

    Candidate error compares the 16x16 source sample with nearest upscaled
    8x8, optionally weighted by per-face importance. Both sizes can use
    filtered sampling and share a palette selected from the 8x8 reference.
    Budget is evaluated after palette quantization and deduplication;
    if the chosen set does not fit, reduce the number of candidates. Stable
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
        indexed,palette,face_textures=index_bakes(bakes,reference_bakes=low)
        cost=sum(len(t.pixels) for t in indexed)
        if cost<=byte_budget:return indexed,palette,face_textures,[i for _,i,_ in chosen]
        if not chosen:raise ValueError(f'8x8 castle bakes exceed {byte_budget} bytes')
        chosen=chosen[:len(chosen)//2]
