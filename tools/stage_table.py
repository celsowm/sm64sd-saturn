"""One row per DS stage: only the facts the ROM cannot supply.

Level overlay, area count, object lists, collision and model files all come
from the ROM (sm64ds_pipeline.level). `enabled` rows are built into discs;
the rest are still converted for the all-stages report.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Stage:
    name: str                 # data/stage/<name>/
    bin: str                  # disc file name, 8 chars max
    title: str
    profile: str = 'outdoor'  # outdoor | indoor | arena | skip
    enabled: bool = False
    convert: dict = field(default_factory=dict)
    painting: str = ''        # castle_1f painting model for this course (data/picture/<x>.bmd)
    far_cull: int = 0         # world units: skip terrain chunks farther than this (0: off)
    actors: tuple = ()        # DS actor names baked as static kinds (actor_registry.ACTORS)


def _s(name, bin, title, profile='outdoor', **kw):
    return Stage(name, bin, title, profile, **kw)


STAGES = [
    _s('main_castle', 'CASTLE', 'Castle Grounds', enabled=True),
    _s('castle_1f', 'CASTLE1F', 'Castle 1F', 'indoor', enabled=True),
    _s('main_garden', 'GARDEN', 'Castle Courtyard', enabled=True),
    _s('castle_b1', 'CASTLEB1', 'Castle Basement', 'indoor'),
    _s('castle_2f', 'CASTLE2F', 'Castle 2F/3F', 'indoor'),
    _s('bombhei_map', 'BOB', 'Bob-omb Battlefield', enabled=True, painting='for_bh', far_cull=320,
       actors=('BOMBHEI', 'RED_BOMBHEI', 'KURIBO', 'BOMBKING', 'STAR1', 'HATENA_BLOCK',
               'COIN', 'RED_COIN', 'SECRET_COIN', 'WANWAN', 'IRONBALL')),
    _s('battan_king_map', 'WF', "Whomp's Fortress", enabled=True, painting='for_bk',
       actors=('COIN', 'RED_COIN', 'KURIBO', 'RED_BOMBHEI', 'HATENA_BLOCK')),
    _s('kaizoku_irie', 'JRB', 'Jolly Roger Bay', enabled=True, painting='for_ki',
       far_cull=320,
       actors=('COIN', 'RED_COIN', 'KURIBO', 'RED_BOMBHEI', 'HATENA_BLOCK')),
    _s('kaizoku_ship', 'JRBSHIP', 'Jolly Roger Bay ship', 'indoor'),
    _s('snow_mt', 'CCM', 'Cool, Cool Mountain', painting='for_sm'),
    _s('snow_slider', 'CCMSLIDE', 'Cool, Cool Mountain slide'),
    _s('teresa_house', 'BBH', "Big Boo's Haunt", 'indoor'),
    _s('cave', 'HMC', 'Hazy Maze Cave', 'indoor'),
    _s('fire_land', 'LLL', 'Lethal Lava Land'),
    _s('fire_mt', 'LLLVOLC', 'Lethal Lava Land volcano', 'indoor'),
    _s('desert_land', 'SSL', 'Shifting Sand Land'),
    _s('desert_py', 'SSLPYR', 'Shifting Sand Land pyramid', 'indoor'),
    _s('water_land', 'DDD', 'Dire, Dire Docks'),
    _s('snow_land', 'SL', 'Snowman\'s Land'),
    _s('snow_kama', 'SLIGLOO', 'Snowman\'s Land igloo', 'indoor'),
    _s('water_city', 'WDW', 'Wet-Dry World'),
    _s('high_mt', 'TTM', 'Tall, Tall Mountain'),
    _s('high_slider', 'TTMSLIDE', 'Tall, Tall Mountain slide'),
    _s('tibi_deka_d', 'THIHUGE', 'Tiny-Huge Island (huge)'),
    _s('tibi_deka_t', 'THITINY', 'Tiny-Huge Island (tiny)'),
    _s('tibi_deka_in', 'THIIN', 'Tiny-Huge Island interior', 'indoor'),
    _s('clock_tower', 'TTC', 'Tick Tock Clock'),
    _s('rainbow_cruise', 'RR', 'Rainbow Ride'),
    _s('suisou', 'SA', 'Secret Aquarium', 'arena'),
    _s('habatake', 'WINGCAP', 'Wing cap tower', 'arena'),
    _s('horisoko', 'VANISH', 'Vanish cap (to confirm)', 'arena'),
    _s('metal_switch', 'METALCAP', 'Metal cap', 'arena'),
    _s('rainbow_mario', 'RAINBOW', 'Over the Rainbows (to confirm)', 'arena'),
    _s('koopa1_map', 'BITDW', 'Bowser in the Dark World'),
    _s('koopa1_boss', 'BOWSER1', 'Bowser 1 arena', 'arena'),
    _s('koopa2_map', 'BITFS', 'Bowser in the Fire Sea'),
    _s('koopa2_boss', 'BOWSER2', 'Bowser 2 arena', 'arena'),
    _s('koopa3_map', 'BITS', 'Bowser in the Sky'),
    _s('koopa3_boss', 'BOWSER3', 'Bowser 3 arena', 'arena'),
    _s('ex_m_map', 'EXM', 'Mario secret stage (to confirm)'),
    _s('ex_mario', 'EXMROOM', 'Mario cap room (to confirm)', 'arena'),
    _s('ex_l_map', 'EXL', 'Luigi secret stage (to confirm)', 'indoor'),
    _s('ex_luigi', 'EXLROOM', 'Luigi cap room (to confirm)', 'arena'),
    _s('ex_w_map', 'EXW', 'Wario secret stage (to confirm)'),
    _s('ex_wario', 'EXWROOM', 'Wario cap room (to confirm)', 'arena'),
    _s('playroom', 'PLAYROOM', 'Playroom (to identify)', 'indoor'),
    _s('test_map', 'TEST', 'Developer test map', 'skip'),
    _s('test_map_b', 'TESTB', 'Developer test map B', 'skip'),
]

BY_NAME = {s.name: s for s in STAGES}
assert len(BY_NAME) == len(STAGES) == 48
assert len({s.bin for s in STAGES}) == 48 and all(len(s.bin) <= 8 for s in STAGES)


def castle_1f_entrance(stage_name):
    """Entrance id in Castle 1F for returning from an enabled painting course.

    0 default, 1 return, 2 intro, then one per enabled painting course in
    table order. The courtyard is not a course (no painting), so it is not
    counted."""
    courses = [s.name for s in STAGES
               if s.enabled and s.painting and s.name != 'main_garden']
    return 3 + courses.index(stage_name)
