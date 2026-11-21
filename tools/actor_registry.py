"""Static actor kinds the stage tools can bake, keyed by DS actor name.

Entries describe only how to turn the DS model into a Saturn asset. Behavior
lives in the runtime, per kind. Scale 0.5 is the castle props' actor scale.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ActorSpec:
    bmd: str
    scale: float = 0.5
    byte_budget: int = 6144
    max_size: int = 24
    max_depth: int = 280
    one_sided: bool = True
    behavior: int = 0          # 0 static, 1 chaser (see runtime/sm64ds_actors.h)
    speed: float = 0.0         # Saturn units per 60 Hz step
    range_: float = 0.0
    radius: float = 0.0
    fuse_steps: int = 0       # >0: light a fuse on contact, explode after this many steps
    blast: float = 0.0
    hp: int = 0               # boss: stomps to defeat
    top: float = 0.0          # boss: head height above its feet
    stun_steps: int = 0       # boss: stunned steps after a non-final stomp (0: 90)
    unlock_by: str = ''       # star: kind that must be defeated first
    star_bit: int = 0         # star: save bit this kind sets (1..8), 0 = none
    source: str = ''          # DS actor the placements come from (default: the key)
    only_star: int = 0        # >0: only the object list for exactly this star
    lift: float = 0.0         # raise placements by this many units
    coin_value: int = 0       # coin: coins granted per pickup


ACTORS = {
    'BOMBHEI': ActorSpec('data/enemy/bombhei/bombhei.bmd', scale=1.0, behavior=1, speed=0.5, range_=50.0, radius=5.0, fuse_steps=90, blast=14.0),
    'RED_BOMBHEI': ActorSpec('data/enemy/bombhei/red_bombhei.bmd', scale=1.0, behavior=1, speed=0.9, range_=70.0, radius=5.0, fuse_steps=60, blast=14.0),
    'KURIBO': ActorSpec('data/enemy/kuribo/kuribo_model.bmd', behavior=1, speed=0.35, range_=45.0, radius=5.0),
    'BOMBKING': ActorSpec('data/enemy/bombking/bomb_king.bmd', byte_budget=10240, behavior=2, speed=0.3,
                        range_=120.0, radius=10.0, hp=3, top=20.0, stun_steps=180),
    'NOKONOKO': ActorSpec('data/enemy/nokonoko/nokonoko.bmd'),
    'HATENA_BLOCK': ActorSpec('data/normal_obj/obj_hatena_box/hatena_box.bmd', one_sided=False),
    'COIN': ActorSpec('ARCHIVE/arc0.narc:5', behavior=4, radius=8.0, coin_value=1, byte_budget=3072),
    'RED_COIN': ActorSpec('ARCHIVE/arc0.narc:7', behavior=4, radius=8.0, coin_value=1, byte_budget=3072),
    # BoB's secret coins (the five floating coins on the lower course) use a
    # separate model handle and are worth five coins each.
    'SECRET_COIN': ActorSpec('ARCHIVE/ar1.narc:6', behavior=4, radius=8.0, coin_value=5, byte_budget=3072),
    'STAR1': ActorSpec('data/special_obj/hs_star/hs_star.bmd', behavior=3, radius=8.0, unlock_by='BOMBKING',
                       source='STARBASE', only_star=1, lift=24.0, one_sided=False, byte_budget=3072,
                       star_bit=1),
    # BoB's Chain Chomp (WANWAN) and rolling iron ball (IRONBALL) have no
    # standalone BMD in this ROM's NitroFS (the decomp names FAT ids from a
    # larger retail image). Bake them from existing art: a round bomb body
    # for the chomp head, a grey rock for the iron ball. The chain is drawn
    # procedurally (small spheres along a quadratic from post to head).
    'WANWAN': ActorSpec('data/enemy/bombhei/bombhei.bmd', scale=1.2, byte_budget=4096,
                        behavior=5, speed=1.2, range_=90.0, radius=12.0, one_sided=False),
    'IRONBALL': ActorSpec('data/enemy/choropu/rock.bmd', scale=1.5, byte_budget=2048,
                          behavior=6, speed=1.5, range_=200.0, radius=10.0, one_sided=False),
}
