/* SM64DS Sega Saturn Intro Binary (0.BIN):
 *   Act I  — Boot Splash + Interactive 3D Title Screen (Mario Face Demo + Star + VDP2 Clouds + TITLE.ADX)
 *   Act II — Princess Peach's Letter (Parchment Card + 3D Animated Peach + PEACH.ADX + Voice Clips)
 *   Handoff — sat_exec_keep_display("EXT.BIN", entrance = SM64DS_ENTRANCE_INTRO)
 */
#include <stdint.h>

#include <saturn/asset.h>
#include <saturn/audio.h>
#include <saturn/cd_block.h>
#include <saturn/cd_mount.h>
#include <saturn/cdfs.h>
#include <saturn/color.h>
#include <saturn/core.h>
#include <saturn/disc_stream.h>
#include <saturn/exec.h>
#include <saturn/font.h>
#include <saturn/hud.h>
#include <saturn/input.h>
#include <saturn/math3d.h>
#include <saturn/mesh3d.h>
#include <saturn/model3d.h>
#include <saturn/music.h>
#include <saturn/music_codecs.h>
#include <saturn/render3d.h>
#include <saturn/scene.h>
#include <saturn/scene3d.h>
#include <saturn/skeleton3d.h>
#include <saturn/skin3d.h>
#include <saturn/time.h>
#include <saturn/vdp1.h>
#include <saturn/vdp2.h>
#include <saturn/vdp2_color_offset.h>
#include <saturn/vdp2_layers.h>
#include <saturn/video.h>

#include "intro_2d.h"
#include "intro_audio.h"
#include "intro_star.h"
#include "mario_face.h"
#include "peach_actor.h"
#include "sm64ds_background.h"
#include "sm64ds_pose.h"
#include "sm64ds_stage_handoff.h"

/* Strip unused PCM/IMA/resident codecs to save High WRAM; stream CRI ADX from CD. */
SAT_MUSIC_CODECS_ADX_FROM_DISC_ONLY;

#define ONE SAT_FX16_ONE
#define INTRO_SCENE_CAP 1600u
#define INTRO_HUD_RESERVE 120u
#define INTRO_VDP2_BG_ADDR 0x00000u
#define INTRO_2D_PAL_BANK 5u
#define INTRO_HUD_PAL_BANK 7u

#define INTRO_MUSIC_TITLE_LOGICAL "music/title"
#define INTRO_MUSIC_PEACH_LOGICAL "music/peach"
#define INTRO_MUSIC_TITLE_SOURCE  "disc/" SM64DS_AUDIO_TITLE_DISC_PATH
#define INTRO_MUSIC_PEACH_SOURCE  "disc/" SM64DS_AUDIO_PEACH_DISC_PATH

typedef enum {
    INTRO_STATE_SPLASH = 0,
    INTRO_STATE_TITLE = 1,
    INTRO_STATE_PEACH = 2,
    INTRO_STATE_EXEC = 3
} intro_state_t;

volatile struct {
    uint32_t magic;
    uint32_t frame;
    uint32_t state;
    uint32_t state_ticks;
    uint32_t vram_free;
    uint32_t music_playing;
    uint32_t music_refills;
    uint32_t music_underruns;
    uint32_t exec_attempts;
} g_sm64ds_intro_stats = { .magic = 0x494E5431u };

/* CD & exec objects MUST stay in High WRAM (sat_exec stages in Low WRAM). */
static sat_cd_block_t cd_block;
static sat_cd_device_t cd_device;
static sat_cdfs_volume_t cd_volume;
static sat_disc_stream_t disc_stream;
static sat_cdfs_file_source_t music_sources[2];
static sat_cdfs_source_desc_t music_source_descs[2];
static sat_asset_desc_t music_asset_descs[2];
static sat_asset_t music_assets[2];
static sat_music_t active_music;
static uint8_t cd_mounted = 0u;
static uint8_t music_open = 0u;

static uint8_t music_workspace[SAT_MUSIC_DISC_WORKSPACE_BYTES(16384u, 2u)]
    __attribute__((section(".wram_l"), aligned(4)));

/* Resident SCSP SFX & Peach voice handles */
static sat_sound_t sfx_nintendo;
static sat_sound_t sfx_mario_hello;
static sat_sound_t sfx_start;
static sat_sound_t sfx_star;
static sat_sound_t sfx_peach[INTRO_PEACH_VOICE_COUNT];

/* 3D Scene & actor storage (placed in .wram_l where safe to keep High WRAM lean) */
static sat_scene_t scene;
static sat_scene3d_face_t scene_faces[INTRO_SCENE_CAP] __attribute__((section(".wram_l")));
static sat_fx16_t scene_keys[INTRO_SCENE_CAP] __attribute__((section(".wram_l")));
static uint16_t scene_order[INTRO_SCENE_CAP] __attribute__((section(".wram_l")));
static sat_scene3d_projected_face_t scene_projected[INTRO_SCENE_CAP] __attribute__((section(".wram_l")));

/* Mario Face Demo (29 bones) */
static sat_vec3_t mf_verts[MARIO_FACE_VERTEX_COUNT];
static sat_vec3_t mf_wverts[MARIO_FACE_VERTEX_COUNT] __attribute__((section(".wram_l")));
static sat_projected_vertex_t mf_proj[MARIO_FACE_VERTEX_COUNT] __attribute__((section(".wram_l")));
static uint16_t mf_indices[MARIO_FACE_FACE_COUNT * 4u];
static sat_vdp1_texture_t mf_textures[MARIO_FACE_TEXTURE_COUNT];
static sat_scene3d_material_t mf_materials[MARIO_FACE_TEXTURE_COUNT + 1u];
static uint16_t mf_face_mats[MARIO_FACE_FACE_COUNT];
static sat_mesh_t mf_mesh;
static sat_skeleton_pose_joint_t mf_pose[MARIO_FACE_JOINT_COUNT];
static sat_vec3_t mf_scales[MARIO_FACE_JOINT_COUNT];
static sat_mat4_t mf_bones[MARIO_FACE_JOINT_COUNT];
static sat_mat4_t mf_world;
static sat_aabb3_t mf_bounds;
static sat_scene3d_instance_t mf_inst;

/* Intro Power Star (1 bone) */
static sat_vec3_t st_verts[INTRO_STAR_VERTEX_COUNT];
static sat_vec3_t st_wverts[INTRO_STAR_VERTEX_COUNT];
static sat_projected_vertex_t st_proj[INTRO_STAR_VERTEX_COUNT];
static uint16_t st_indices[INTRO_STAR_FACE_COUNT * 4u];
static sat_vdp1_texture_t st_textures[INTRO_STAR_TEXTURE_COUNT];
static sat_scene3d_material_t st_materials[INTRO_STAR_TEXTURE_COUNT + 1u];
static uint16_t st_face_mats[INTRO_STAR_FACE_COUNT];
static sat_mesh_t st_mesh;
static sat_skeleton_pose_joint_t st_pose[INTRO_STAR_JOINT_COUNT];
static sat_vec3_t st_scales[INTRO_STAR_JOINT_COUNT];
static sat_mat4_t st_bones[INTRO_STAR_JOINT_COUNT];
static sat_mat4_t st_world;
static sat_aabb3_t st_bounds;
static sat_scene3d_instance_t st_inst;

/* Princess Peach (21 bones) */
static sat_vec3_t pe_verts[PEACH_ACTOR_VERTEX_COUNT];
static sat_vec3_t pe_wverts[PEACH_ACTOR_VERTEX_COUNT] __attribute__((section(".wram_l")));
static sat_projected_vertex_t pe_proj[PEACH_ACTOR_VERTEX_COUNT] __attribute__((section(".wram_l")));
static uint16_t pe_indices[PEACH_ACTOR_FACE_COUNT * 4u];
static sat_vdp1_texture_t pe_textures[PEACH_ACTOR_TEXTURE_COUNT];
static sat_scene3d_material_t pe_materials[PEACH_ACTOR_TEXTURE_COUNT + 1u];
static uint16_t pe_face_mats[PEACH_ACTOR_FACE_COUNT];
static sat_mesh_t pe_mesh;
static sat_skeleton_pose_joint_t pe_pose[PEACH_ACTOR_JOINT_COUNT];
static sat_vec3_t pe_scales[PEACH_ACTOR_JOINT_COUNT];
static sat_mat4_t pe_bones[PEACH_ACTOR_JOINT_COUNT];
static sat_mat4_t pe_world;
static sat_aabb3_t pe_bounds;
static sat_scene3d_instance_t pe_inst;

/* 2D VDP1 Sprite Textures & HUD Font */
static sat_vdp1_texture_t tex_banner_title;
static sat_vdp1_texture_t tex_banner_nintendo;
static sat_vdp1_texture_t tex_banner_start;
static sat_vdp1_texture_t tex_peach_card;
static sat_ascii_font_t hud_font;
static sat_hud_t hud;

/* VDP2 Palettes */
static uint16_t vdp2_pal_splash[256];
static uint16_t vdp2_pal_title[256];
static uint16_t vdp2_pal_peach[256];

#define INTRO_MUST(expr) do { \
    sat_result_t _st = (expr); \
    if (_st != SAT_OK) { \
        (void)sat_vdp2_color_offset_disable(SAT_VDP2_LAYER_ALL); \
        (void)sat_vdp2_layers_commit(); \
        SAT_PANIC_IF_ERROR(_st); \
    } \
} while (0)

static void fill_u8(uint8_t* dst, uint8_t val, uint32_t n) {
    for (uint32_t i = 0u; i < n; ++i) dst[i] = val;
}

static void zero_u16(uint16_t* dst, uint32_t n) {
    for (uint32_t i = 0u; i < n; ++i) dst[i] = 0u;
}

static sat_result_t service_cd_audio(void* context) {
    (void)context;
    return sat_audio_update();
}

static void init_actor_model(
    const sat_model_asset_t* asset,
    sat_mesh_t* mesh,
    sat_vec3_t* verts,
    uint16_t* indices,
    sat_vdp1_texture_t* textures,
    sat_scene3d_material_t* materials,
    uint16_t* face_mats,
    sat_mat4_t* world,
    sat_scene3d_instance_t* inst,
    uint16_t untextured_rgb555
) {
    SAT_PANIC_IF_ERROR(sat_mesh_init(mesh, verts, asset->vertex_count, indices, asset->face_count));
    SAT_PANIC_IF_ERROR(sat_model_copy_to_mesh(asset, mesh));
    SAT_PANIC_IF_ERROR(sat_model_upload_textures(asset, textures, asset->texture_count));
    for (uint16_t i = 0u; i < asset->texture_count; ++i) {
        materials[i] = (sat_scene3d_material_t){
            .kind = SAT_SCENE3D_INDEXED_TEXTURED,
            .rgb555 = sm64ds_texture_fallback(asset, i),
            .texture = &textures[i],
            .color_calc_slot = SAT_INDEXED_SOLID_OPAQUE,
            .sprite_flags = 0u
        };
    }
    materials[asset->texture_count] = (sat_scene3d_material_t){
        .kind = SAT_SCENE3D_RGB,
        .rgb555 = untextured_rgb555,
        .texture = 0,
        .color_calc_slot = SAT_INDEXED_SOLID_OPAQUE,
        .sprite_flags = 0u
    };
    for (uint16_t i = 0u; i < asset->face_count; ++i) {
        uint16_t ti = asset->face_texture_indices[i];
        face_mats[i] = (ti < asset->texture_count) ? ti : asset->texture_count;
    }
    *inst = (sat_scene3d_instance_t){
        .mesh = mesh,
        .materials = materials,
        .material_count = (uint16_t)(asset->texture_count + 1u),
        .face_materials = face_mats,
        .world = world,
        .pass = 0u,
        .cull_backfaces = SAT_SCENE3D_CULL_SCREEN
    };
}

static void play_sfx(sat_sound_t sound, uint16_t volume) {
    sat_sound_play_params_t p = {
        .volume = volume,
        .pan = 0,
        .priority = 12u,
        .flags = 0u,
        .pitch = ONE,
        .start_tick = 0u
    };
    (void)sat_sound_play(sound, &p, 0);
}

static void load_sfx_clip(sat_sound_t* out, const sm64ds_sfx_clip_t* clip) {
    sat_sound_desc_t desc = {0};
    desc.samples = clip->samples;
    desc.sample_count = clip->sample_count;
    desc.sample_rate = clip->sample_rate;
    desc.format = SAT_AUDIO_PCM_S8;
    desc.loop = 0u;
    SAT_PANIC_IF_ERROR(sat_sound_create(out, &desc));
}

static void init_audio_and_cd(void) {
    SAT_PANIC_IF_ERROR(sat_audio_init());
    load_sfx_clip(&sfx_nintendo, &intro_sfx_nintendo);
    load_sfx_clip(&sfx_mario_hello, &intro_sfx_mario_hello);
    load_sfx_clip(&sfx_start, &intro_sfx_start);
    load_sfx_clip(&sfx_star, &intro_sfx_star);
    for (uint32_t i = 0u; i < INTRO_PEACH_VOICE_COUNT; ++i) {
        load_sfx_clip(&sfx_peach[i], &intro_sfx_peach[i]);
    }

    if (sat_cd_mount_default(&cd_block, service_cd_audio, 0, &cd_device, 0u, &cd_volume) != SAT_OK) {
        return;
    }
    if (sat_disc_stream_init(&disc_stream, &cd_block) != SAT_OK) {
        return;
    }
    cd_mounted = 1u;

    music_source_descs[0] = (sat_cdfs_source_desc_t){
        SM64DS_AUDIO_TITLE_DISC_PATH, INTRO_MUSIC_TITLE_SOURCE, SM64DS_AUDIO_TITLE_BYTES
    };
    music_source_descs[1] = (sat_cdfs_source_desc_t){
        SM64DS_AUDIO_PEACH_DISC_PATH, INTRO_MUSIC_PEACH_SOURCE, SM64DS_AUDIO_PEACH_BYTES
    };
    if (sat_cdfs_register_source_manifest(&cd_volume, music_source_descs, 2u, music_sources) != SAT_OK) {
        return;
    }

    music_asset_descs[0] = (sat_asset_desc_t){0};
    music_asset_descs[1] = (sat_asset_desc_t){0};
    music_asset_descs[0].logical_path = INTRO_MUSIC_TITLE_LOGICAL;
    music_asset_descs[0].source_path = INTRO_MUSIC_TITLE_SOURCE;
    music_asset_descs[0].size = music_sources[0].file.size;
    music_asset_descs[0].sample_rate = SM64DS_AUDIO_TITLE_SAMPLE_RATE;
    music_asset_descs[0].sample_count = SM64DS_AUDIO_TITLE_SAMPLE_COUNT;
    music_asset_descs[0].channels = SM64DS_AUDIO_TITLE_CHANNELS;
    music_asset_descs[0].format = SM64DS_AUDIO_TITLE_FORMAT;
    music_asset_descs[0].kind = SAT_ASSET_STREAM;

    music_asset_descs[1].logical_path = INTRO_MUSIC_PEACH_LOGICAL;
    music_asset_descs[1].source_path = INTRO_MUSIC_PEACH_SOURCE;
    music_asset_descs[1].size = music_sources[1].file.size;
    music_asset_descs[1].sample_rate = SM64DS_AUDIO_PEACH_SAMPLE_RATE;
    music_asset_descs[1].sample_count = SM64DS_AUDIO_PEACH_SAMPLE_COUNT;
    music_asset_descs[1].channels = SM64DS_AUDIO_PEACH_CHANNELS;
    music_asset_descs[1].format = SM64DS_AUDIO_PEACH_FORMAT;
    music_asset_descs[1].kind = SAT_ASSET_STREAM;

    (void)sat_asset_register_manifest(music_asset_descs, 2u, music_assets);
}

static void music_stop_and_close(void) {
    if (music_open != 0u) {
        (void)sat_music_stop(active_music);
        (void)sat_music_close(active_music);
        music_open = 0u;
    }
}

static void music_start_track(const char* logical_path) {
    music_stop_and_close();
    if (cd_mounted == 0u) return;
    sat_music_desc_t desc = {
        .asset = logical_path,
        .disc = &disc_stream,
        .workspace = music_workspace,
        .workspace_bytes = sizeof(music_workspace),
        .ring_frames = 16384u
    };
    if (sat_music_open(&active_music, &desc) == SAT_OK) {
        if (sat_music_play(active_music) == SAT_OK) {
            music_open = 1u;
        } else {
            (void)sat_music_close(active_music);
        }
    }
}

static uint16_t blend_bgr555(uint16_t a, uint16_t b, int32_t t, int32_t max_t) {
    int32_t ra = (int32_t)(a & 31u), ga = (int32_t)((a >> 5) & 31u), ba = (int32_t)((a >> 10) & 31u);
    int32_t rb = (int32_t)(b & 31u), gb = (int32_t)((b >> 5) & 31u), bb = (int32_t)((b >> 10) & 31u);
    uint16_t r = (uint16_t)(ra + ((rb - ra) * t) / max_t);
    uint16_t g = (uint16_t)(ga + ((gb - ga) * t) / max_t);
    uint16_t bl = (uint16_t)(ba + ((bb - ba) * t) / max_t);
    return SAT_BGR555(r, g, bl);
}

static void build_vdp2_palettes(void) {
    /* Splash palette: clean bright white with soft cool bottom tint */
    for (uint32_t i = 0u; i < 256u; ++i) {
        vdp2_pal_splash[i] = SAT_BGR555(31, 31, 31);
    }
    for (uint32_t i = 1u; i <= 64u; ++i) {
        vdp2_pal_splash[i] = blend_bgr555(SAT_BGR555(31, 31, 31), SAT_BGR555(28, 30, 31), (int32_t)(i - 1u), 63);
    }

    /* Title palette: rich SM64DS sky-blue gradient (1..64) + ROM cloud palette (64..79) */
    zero_u16(vdp2_pal_title, 256u);
    for (uint32_t i = 1u; i <= 63u; ++i) {
        vdp2_pal_title[i] = blend_bgr555(SAT_BGR555(6, 15, 30), SAT_BGR555(18, 26, 31), (int32_t)(i - 1u), 62);
    }
    for (uint32_t i = 0u; i < 16u; ++i) {
        vdp2_pal_title[64u + i] = intro_cloud_palette[i] & 0x7FFFu;
    }

    /* Peach's Letter palette: warm dreamy lavender-gold sky (1..64) + warm cream clouds (64..79) */
    zero_u16(vdp2_pal_peach, 256u);
    for (uint32_t i = 1u; i <= 63u; ++i) {
        vdp2_pal_peach[i] = blend_bgr555(SAT_BGR555(19, 17, 29), SAT_BGR555(31, 25, 27), (int32_t)(i - 1u), 62);
    }
    for (uint32_t i = 0u; i < 16u; ++i) {
        uint16_t c = intro_cloud_palette[i] & 0x7FFFu;
        vdp2_pal_peach[64u + i] = blend_bgr555(c, SAT_BGR555(31, 28, 29), 3, 10);
    }
}

static uint8_t sample_cloud_4bpp(uint16_t x, uint16_t y) {
    uint32_t idx = ((uint32_t)y * INTRO_CLOUD_ATLAS_W + (uint32_t)x) >> 1;
    uint8_t byte = intro_cloud_atlas_4bpp[idx];
    return (x & 1u) ? (uint8_t)(byte & 0x0Fu) : (uint8_t)((byte >> 4) & 0x0Fu);
}

typedef struct {
    int16_t dst_x, dst_y;
    uint16_t src_x, src_y, w, h;
} cloud_stamp_t;

static void init_vdp2_sky_backdrop(void) {
    build_vdp2_palettes();

    /* Stamp the 4 volumetric ROM clouds from intro_cloud_atlas_4bpp across a seamless 512x256 VDP2 bitmap. */
    static const cloud_stamp_t stamps[] = {
        /* Large main cloud (src 0,0 -> 184x76) */
        {  16,  18,   0,  0, 184, 76 },
        { 270, 126,   0,  0, 184, 76 },
        /* Top-right puffy cloud (src 184,0 -> 72x42) */
        { 226,  24, 184,  0,  72, 42 },
        { 430,  36, 184,  0,  72, 42 },
        /* Mid-right cloud (src 160,38 -> 96x58) */
        { 334,  58, 160, 38,  96, 58 },
        {  96, 142, 160, 38,  96, 58 },
        /* Bottom-left cloud (src 0,78 -> 124x50) */
        {  10, 104,   0, 78, 124, 50 },
        { 206, 166,   0, 78, 124, 50 },
    };

    static uint8_t row_buf[512];
    for (uint16_t y = 0u; y < 256u; ++y) {
        uint8_t sky_idx = (uint8_t)(1u + ((uint32_t)(y < 224u ? y : 223u) * 62u) / 223u);
        fill_u8(row_buf, sky_idx, 512u);
        for (uint32_t s = 0u; s < (uint32_t)(sizeof(stamps) / sizeof(stamps[0])); ++s) {
            const cloud_stamp_t* st = &stamps[s];
            if ((int32_t)y < st->dst_y || (int32_t)y >= st->dst_y + (int32_t)st->h) continue;
            uint16_t sy = (uint16_t)(st->src_y + (uint16_t)((int32_t)y - st->dst_y));
            for (uint16_t dx = 0u; dx < st->w; ++dx) {
                uint8_t ci = sample_cloud_4bpp((uint16_t)(st->src_x + dx), sy);
                if (ci != 0u) {
                    uint16_t wx = (uint16_t)((st->dst_x + (int32_t)dx) & 511);
                    row_buf[wx] = (uint8_t)(64u + ci);
                }
            }
        }
        /* Write 512 bytes (256 big-endian 16-bit words) into VDP2 VRAM */
        SAT_PANIC_IF_ERROR(sat_vdp2_vram_write_words(
            (INTRO_VDP2_BG_ADDR >> 1) + (uint32_t)y * 256u,
            (const uint16_t*)(const void*)row_buf,
            256u
        ));
    }

    SAT_PANIC_IF_ERROR(sat_vdp2_palette_upload(vdp2_pal_splash, 256u, 0u));

    sat_vdp2_layer_config_t cfg;
    sat_vdp2_layer_config_default(SAT_VDP2_NBG0, &cfg);
    cfg.bitmap = 1u;
    cfg.color_mode = SAT_VDP2_COLOR_MODE_256;
    cfg.bitmap_size = SAT_VDP2_BITMAP_512X256;
    cfg.priority = 2u;
    cfg.transparent = 0u;
    cfg.palette = 0u;
    cfg.plane_address[0] = INTRO_VDP2_BG_ADDR;
    SAT_PANIC_IF_ERROR(sat_vdp2_layer_configure(&cfg));
    SAT_PANIC_IF_ERROR(sat_vdp2_sprite_set_priority(4u));
    SAT_PANIC_IF_ERROR(sat_vdp2_color_offset_enable(SAT_VDP2_LAYER_ALL, SAT_VDP2_COLOR_OFFSET_A));
}

static int16_t cur_fade_offset = 1000;
static void set_fade_offset(int16_t v) {
    if (v < -255) v = -255;
    if (v > 255) v = 255;
    if (v == cur_fade_offset) return;
    cur_fade_offset = v;
    sat_vdp2_color_offset_t off = { v, v, v };
    (void)sat_vdp2_color_offset_set(SAT_VDP2_COLOR_OFFSET_A, &off);
}

static void set_vdp2_palette(const uint16_t* pal) {
    (void)sat_vdp2_palette_upload(pal, 256u, 0u);
}

static void exec_castle_grounds(uint8_t entrance, int keep_display) {
    g_sm64ds_intro_stats.exec_attempts++;
    music_stop_and_close();
    if (cd_mounted == 0u) {
        if (sat_cd_mount_default(&cd_block, 0, 0, &cd_device, 0u, &cd_volume) == SAT_OK) {
            cd_mounted = 1u;
        }
    }
    if (cd_mounted != 0u) {
        sm64ds_warp_arg_t arg = {
            .magic = SM64DS_WARP_MAGIC,
            .entrance = entrance,
            .hud_mode = 0u,
            .close_camera = 1u,
            .reserved = 0u
        };
        if (keep_display) {
            (void)sat_exec_keep_display(&cd_volume, "EXT.BIN", &arg, sizeof(arg));
        } else {
            (void)sat_exec(&cd_volume, "EXT.BIN", &arg, sizeof(arg));
        }
    }
}

static void pose_mario_face(int32_t anim_time) {
    const sat_skeleton_clip_t* c = &mario_face_clips[0];
    INTRO_MUST(sat_clip_sample(c, anim_time, mf_pose, MARIO_FACE_JOINT_COUNT));
    INTRO_MUST(sm64ds_clip_sample_scale(&mario_face_scale_clips[0], c, anim_time, mf_scales, MARIO_FACE_JOINT_COUNT));
    INTRO_MUST(sm64ds_pose_world_matrices(&mario_face_skeleton, mf_pose, mf_scales, mf_bones, MARIO_FACE_JOINT_COUNT));
    INTRO_MUST(sat_skin_update_mesh(&mario_face_skin, mf_bones, MARIO_FACE_JOINT_COUNT, &mf_mesh, 0, &mf_bounds));
}

static void pose_intro_star(int32_t anim_time) {
    const sat_skeleton_clip_t* c = &intro_star_clips[0];
    INTRO_MUST(sat_clip_sample(c, anim_time, st_pose, INTRO_STAR_JOINT_COUNT));
    INTRO_MUST(sm64ds_clip_sample_scale(&intro_star_scale_clips[0], c, anim_time, st_scales, INTRO_STAR_JOINT_COUNT));
    INTRO_MUST(sm64ds_pose_world_matrices(&intro_star_skeleton, st_pose, st_scales, st_bones, INTRO_STAR_JOINT_COUNT));
    INTRO_MUST(sat_skin_update_mesh(&intro_star_skin, st_bones, INTRO_STAR_JOINT_COUNT, &st_mesh, 0, &st_bounds));
}

static void pose_peach(int32_t anim_time) {
    const sat_skeleton_clip_t* c = &peach_actor_clips[0];
    INTRO_MUST(sat_clip_sample(c, anim_time, pe_pose, PEACH_ACTOR_JOINT_COUNT));
    INTRO_MUST(sm64ds_clip_sample_scale(&peach_actor_scale_clips[0], c, anim_time, pe_scales, PEACH_ACTOR_JOINT_COUNT));
    INTRO_MUST(sm64ds_pose_world_matrices(&peach_actor_skeleton, pe_pose, pe_scales, pe_bones, PEACH_ACTOR_JOINT_COUNT));
    INTRO_MUST(sat_skin_update_mesh(&peach_actor_skin, pe_bones, PEACH_ACTOR_JOINT_COUNT, &pe_mesh, 0, &pe_bounds));
}

int main(void) {
    const sat_video_config_t video = { 320u, 224u, SAT_VIDEO_AUTO, 0u };
    SAT_PANIC_IF_ERROR(sat_init(&video));
    SAT_PANIC_IF_ERROR(sat_vdp1_set_frame_mode(SAT_VDP1_FRAME_ON_SUBMIT));

    /* Upload 3D models & 2D sprites into VDP1 VRAM */
    init_actor_model(
        &mario_face_model, &mf_mesh, mf_verts, mf_indices,
        mf_textures, mf_materials, mf_face_mats, &mf_world, &mf_inst, SAT_RGB555(26, 20, 16)
    );
    init_actor_model(
        &intro_star_model, &st_mesh, st_verts, st_indices,
        st_textures, st_materials, st_face_mats, &st_world, &st_inst, SAT_RGB555(2, 2, 3)
    );
    init_actor_model(
        &peach_actor_model, &pe_mesh, pe_verts, pe_indices,
        pe_textures, pe_materials, pe_face_mats, &pe_world, &pe_inst, SAT_RGB555(30, 22, 24)
    );

    SAT_PANIC_IF_ERROR(sat_palette_upload_indexed8(intro_2d_palette, INTRO_2D_PAL_BANK));
    SAT_PANIC_IF_ERROR(sat_tex_upload_indexed8_pixels(
        &tex_banner_title, intro_banner_title_pixels, INTRO_BANNER_TITLE_W, INTRO_BANNER_TITLE_H, INTRO_2D_PAL_BANK));
    SAT_PANIC_IF_ERROR(sat_tex_upload_indexed8_pixels(
        &tex_banner_nintendo, intro_banner_nintendo_pixels, INTRO_BANNER_NINTENDO_W, INTRO_BANNER_NINTENDO_H, INTRO_2D_PAL_BANK));
    SAT_PANIC_IF_ERROR(sat_tex_upload_indexed8_pixels(
        &tex_banner_start, intro_banner_start_pixels, INTRO_BANNER_START_W, INTRO_BANNER_START_H, INTRO_2D_PAL_BANK));
    SAT_PANIC_IF_ERROR(sat_tex_upload_indexed8_pixels(
        &tex_peach_card, intro_peach_letter_card_pixels, INTRO_PEACH_LETTER_CARD_W, INTRO_PEACH_LETTER_CARD_H, INTRO_2D_PAL_BANK));

    SAT_PANIC_IF_ERROR(sat_ascii_font_init_8x8_indexed8(&hud_font, SAT_COLOR_WHITE, SAT_COLOR_BLACK, INTRO_HUD_PAL_BANK));
    SAT_PANIC_IF_ERROR(sat_hud_init(&hud, &hud_font, SAT_COLOR_WHITE, 8u));
    g_sm64ds_intro_stats.vram_free = sat_vdp1_vram_free_bytes();

    SAT_PANIC_IF_ERROR(sat_scene_init(&scene, scene_faces, scene_keys, scene_order, INTRO_SCENE_CAP));
    SAT_PANIC_IF_ERROR(sat_scene3d_faces_use_projected_storage(&scene.faces, scene_projected, INTRO_SCENE_CAP));

    init_vdp2_sky_backdrop();
    init_audio_and_cd();

    /* Fixed 3D camera facing Mario's front (+Z in SM64DS BMD coordinates) */
    sat_camera3d_t camera = {0};
    camera.up = (sat_vec3_t){ 0, ONE, 0 };
    camera.aspect = sat_fx16_div(320 * ONE, 224 * ONE);
    camera.fov_y = 42 * ONE;
    camera.near_z = ONE / 2;
    camera.far_z = 200 * ONE;
    camera.eye = (sat_vec3_t){ 0, ONE / 2, 16 * ONE };
    camera.target = (sat_vec3_t){ 0, ONE / 4, 0 };
    SAT_PANIC_IF_ERROR(sat_camera3d_update(&camera));

    intro_state_t state = INTRO_STATE_SPLASH;
    const uint16_t* pending_vdp2_pal = 0;
    uint32_t state_ticks = 0u;
    uint8_t title_leaving = 0u;
    uint8_t title_leave_ticks = 0u;
    uint8_t quick_skip = 0u;
    uint8_t peach_leaving = 0u;
    uint8_t peach_leave_ticks = 0u;
    uint8_t peach_voice_fired = 0u;

    int32_t head_yaw = 0;
    int32_t head_pitch = 0;
    int32_t head_nod = 0;
    int32_t scroll_x = 0;
    int32_t anim_time_mf = 0;
    int32_t anim_time_st = 0;
    int32_t anim_time_pe = 0;

    uint64_t last_ticks = sat_time_ticks();
    const uint32_t tick_hz = sat_time_frequency_hz();
    const uint32_t sim_step_ticks = tick_hz >= 30u ? (tick_hz / 30u) : 1u;
    uint64_t sim_accum = 0u;

    /* Splash entry cue */
    set_fade_offset(-255);
    play_sfx(sfx_nintendo, 235u);

    for (;;) {
        sat_pad_state_t pad = {0};
        (void)sat_pad_poll(&pad);

        uint64_t now = sat_time_ticks();
        uint64_t dt = now - last_ticks;
        last_ticks = now;
        if (dt > sim_step_ticks * 4u) dt = sim_step_ticks * 4u;
        sim_accum += dt;

        /* Service ADX CD stream & SCSP sound ring every frame */
        if (music_open != 0u) {
            (void)sat_music_update(active_music);
            sat_audio_stream_stats_t st = {0};
            if (sat_music_stats(active_music, &st) == SAT_OK) {
                g_sm64ds_intro_stats.music_playing = st.playing;
                g_sm64ds_intro_stats.music_refills = st.refill_count;
                g_sm64ds_intro_stats.music_underruns = st.underrun_count;
            }
        }
        (void)sat_audio_update();

        /* Edge-triggered inputs (processed per display frame so taps are never missed) */
        const uint16_t pressed = pad.pressed;
        if (state == INTRO_STATE_SPLASH) {
            if ((pressed & (SAT_PAD_START | SAT_PAD_A)) != 0u && state_ticks > 6u) {
                state = INTRO_STATE_TITLE;
                state_ticks = 0u;
                pending_vdp2_pal = vdp2_pal_title;
                set_fade_offset(255);
                music_start_track(INTRO_MUSIC_TITLE_LOGICAL);
            }
        } else if (state == INTRO_STATE_TITLE && title_leaving == 0u) {
            if ((pressed & (SAT_PAD_START | SAT_PAD_A)) != 0u) {
                play_sfx(sfx_start, 240u);
                title_leaving = 1u;
                title_leave_ticks = 0u;
                quick_skip = 0u;
            } else if ((pressed & SAT_PAD_Z) != 0u) {
                play_sfx(sfx_start, 220u);
                title_leaving = 1u;
                title_leave_ticks = 0u;
                quick_skip = 1u;
            } else if ((pressed & (SAT_PAD_B | SAT_PAD_C)) != 0u) {
                play_sfx((pressed & SAT_PAD_B) ? sfx_mario_hello : sfx_star, 230u);
                head_nod = 14 * ONE;
            }
        } else if (state == INTRO_STATE_PEACH && peach_leaving == 0u) {
            if ((pressed & (SAT_PAD_START | SAT_PAD_A)) != 0u && state_ticks > 12u) {
                peach_leaving = 1u;
                peach_leave_ticks = 0u;
            }
        }

        /* Deterministic 30 Hz choreography & animation update */
        while (sim_accum >= sim_step_ticks) {
            sim_accum -= sim_step_ticks;
            ++state_ticks;

            if (state == INTRO_STATE_SPLASH) {
                if (state_ticks <= 12u) {
                    set_fade_offset((int16_t)(-255 + (int32_t)(state_ticks * 255u) / 12));
                } else if (state_ticks == 20u) {
                    play_sfx(sfx_mario_hello, 240u);
                } else if (state_ticks >= 58u && state_ticks <= 72u) {
                    set_fade_offset((int16_t)(((int32_t)(state_ticks - 58u) * 255) / 14));
                } else if (state_ticks > 72u) {
                    state = INTRO_STATE_TITLE;
                    state_ticks = 0u;
                    pending_vdp2_pal = vdp2_pal_title;
                    set_fade_offset(255);
                    music_start_track(INTRO_MUSIC_TITLE_LOGICAL);
                }
            } else if (state == INTRO_STATE_TITLE) {
                scroll_x = (scroll_x + (ONE / 2)) & ((512 * ONE) - 1);
                anim_time_mf += ONE / 30;
                if (anim_time_mf >= ((int32_t)mario_face_clips[0].frame_count * ONE) / 30) {
                    anim_time_mf = 0;
                }
                anim_time_st += ONE / 30;
                int32_t st_max = ((int32_t)(intro_star_clips[0].frame_count - 1u) * ONE) / 30;
                if (anim_time_st > st_max) {
                    anim_time_st = st_max;
                }

                /* Interactive D-pad Mario head tilt with smooth spring return */
                int32_t target_yaw = 0;
                int32_t target_pitch = 0;
                if (pad.held & SAT_PAD_LEFT)  target_yaw = -28 * ONE;
                if (pad.held & SAT_PAD_RIGHT) target_yaw =  28 * ONE;
                if (pad.held & SAT_PAD_UP)    target_pitch = -18 * ONE;
                if (pad.held & SAT_PAD_DOWN)  target_pitch =  18 * ONE;
                head_yaw += (target_yaw - head_yaw) / 5;
                head_pitch += (target_pitch - head_pitch) / 5;
                if (head_nod > 0) head_nod = (head_nod * 4) / 5;

                if (title_leaving != 0u) {
                    ++title_leave_ticks;
                    if (quick_skip != 0u) {
                        int16_t f = (int16_t)(-((int32_t)title_leave_ticks * 255) / 8);
                        set_fade_offset(f);
                        if (title_leave_ticks >= 9u) {
                            exec_castle_grounds(SM64DS_ENTRANCE_DEFAULT, 0);
                            /* Fallback if EXT.BIN absent */
                            title_leaving = 0u;
                            set_fade_offset(0);
                        }
                    } else {
                        int16_t f = (int16_t)(((int32_t)title_leave_ticks * 255) / 14);
                        set_fade_offset(f);
                        if (title_leave_ticks >= 15u) {
                            state = INTRO_STATE_PEACH;
                            state_ticks = 0u;
                            title_leaving = 0u;
                            peach_leaving = 0u;
                            peach_leave_ticks = 0u;
                            peach_voice_fired = 0u;
                            anim_time_pe = 0;
                            pending_vdp2_pal = vdp2_pal_peach;
                            set_fade_offset(255);
                            music_start_track(INTRO_MUSIC_PEACH_LOGICAL);
                        }
                    }
                } else if (state_ticks <= 14u) {
                    set_fade_offset((int16_t)(255 - ((int32_t)state_ticks * 255) / 14));
                } else {
                    set_fade_offset(0);
                }
            } else if (state == INTRO_STATE_PEACH) {
                scroll_x = (scroll_x + (ONE / 4)) & ((512 * ONE) - 1);
                anim_time_pe += ONE / 30;
                if (anim_time_pe >= ((int32_t)peach_actor_clips[0].frame_count * ONE) / 30) {
                    anim_time_pe = 0;
                }

                /* Trigger Peach's 6 authentic ROM letter voice clips on calibrated beats */
                static const uint16_t voice_ticks[INTRO_PEACH_VOICE_COUNT] = {
                    16u, 44u, 84u, 128u, 158u, 198u
                };
                if (peach_leaving == 0u && peach_voice_fired < INTRO_PEACH_VOICE_COUNT &&
                    state_ticks >= voice_ticks[peach_voice_fired]) {
                    play_sfx(sfx_peach[peach_voice_fired], 250u);
                    ++peach_voice_fired;
                }

                if (peach_leaving == 0u && state_ticks >= 224u) {
                    peach_leaving = 1u;
                    peach_leave_ticks = 0u;
                }

                if (peach_leaving != 0u) {
                    ++peach_leave_ticks;
                    set_fade_offset((int16_t)(((int32_t)peach_leave_ticks * 255) / 16));
                    if (peach_leave_ticks >= 18u) {
                        exec_castle_grounds(SM64DS_ENTRANCE_INTRO, 1);
                        /* Standalone disc fallback: loop cleanly back to Title */
                        state = INTRO_STATE_TITLE;
                        state_ticks = 0u;
                        peach_leaving = 0u;
                        pending_vdp2_pal = vdp2_pal_title;
                        set_fade_offset(255);
                        music_start_track(INTRO_MUSIC_TITLE_LOGICAL);
                    }
                } else if (state_ticks <= 14u) {
                    set_fade_offset((int16_t)(255 - ((int32_t)state_ticks * 255) / 14));
                } else {
                    set_fade_offset(0);
                }
            }
        }

        /* Queue VDP2 scroll (committed tear-free in VBlank right after sat_end_frame) */
        (void)sat_vdp2_layer_set_scroll(SAT_VDP2_NBG0, scroll_x, 0);

        /* Begin VDP1 frame with transparent erase so VDP2 sky/clouds show through */
        INTRO_MUST(sat_vdp1_set_erase_transparent());
        INTRO_MUST(sat_begin_frame());
        INTRO_MUST(sat_scene_begin(&scene, &camera, camera.near_z, 320u, 224u, INTRO_HUD_RESERVE));

        if (state == INTRO_STATE_TITLE) {
            pose_mario_face(anim_time_mf);
            pose_intro_star(anim_time_st);

            /* Mario Face Demo centered cleanly between title logo and PRESS START */
            sat_model_transform3d_t tr;
            sat_model_transform3d_identity(&tr);
            int32_t idle_sway = sat_sin_deg((int32_t)((state_ticks * 3u) % 360u) * ONE);
            int32_t idle_bob = sat_sin_deg((int32_t)((state_ticks * 5u) % 360u) * ONE);
            int32_t mf_scale = (ONE * 4) / 5;
            tr.position = (sat_vec3_t){
                -sat_fx16_mul(mf_bounds.center.x, mf_scale),
                -(ONE / 4) - sat_fx16_mul(mf_bounds.center.y, mf_scale) + (idle_bob / 8),
                -sat_fx16_mul(mf_bounds.center.z, mf_scale)
            };
            tr.rotation_deg = (sat_vec3_t){
                head_pitch + (head_nod / 2),
                head_yaw + ((idle_sway * 10) >> 16) * ONE,
                0
            };
            tr.scale = (sat_vec3_t){ mf_scale, mf_scale, mf_scale };
            INTRO_MUST(sat_model_transform3d_matrix(&tr, &mf_world));

            /* Orbiting golden Power Star */
            sat_model_transform3d_t str;
            sat_model_transform3d_identity(&str);
            int32_t orbit_ang = (int32_t)((state_ticks * 4u) % 360u) * ONE;
            int32_t ox = (sat_cos_deg(orbit_ang) * 5);
            int32_t oz = (sat_sin_deg(orbit_ang) * 3);
            int32_t oy = (ONE * 3) / 2 + (sat_sin_deg((int32_t)((state_ticks * 7u) % 360u) * ONE) / 2);
            str.position = (sat_vec3_t){ ox, oy, oz };
            str.rotation_deg = (sat_vec3_t){ 0, (int32_t)((state_ticks * 9u) % 360u) * ONE, 0 };
            str.scale = (sat_vec3_t){ (ONE * 9) / 10, (ONE * 9) / 10, (ONE * 9) / 10 };
            INTRO_MUST(sat_model_transform3d_matrix(&str, &st_world));

            INTRO_MUST(sat_scene_submit_instance(&scene, &mf_inst, SAT_SCENE3D_SLOT_INHERIT, mf_proj, mf_wverts));
            INTRO_MUST(sat_scene_submit_instance(&scene, &st_inst, SAT_SCENE3D_SLOT_INHERIT, st_proj, st_wverts));
        } else if (state == INTRO_STATE_PEACH) {
            pose_peach(anim_time_pe);

            /* Princess Peach mathematically centered crown-to-hem on the right half */
            sat_model_transform3d_t ptr;
            sat_model_transform3d_identity(&ptr);
            int32_t float_y = sat_sin_deg((int32_t)((state_ticks * 4u) % 360u) * ONE);
            int32_t rise_t = state_ticks < 24u ? (int32_t)(24u - state_ticks) : 0;
            int32_t pe_scale = ONE / 3;
            ptr.position = (sat_vec3_t){
                (ONE * 7) / 2 - sat_fx16_mul(pe_bounds.center.x, pe_scale),
                (ONE / 4) - sat_fx16_mul(pe_bounds.center.y, pe_scale) - (rise_t * ONE) / 12 + (float_y / 3),
                -sat_fx16_mul(pe_bounds.center.z, pe_scale)
            };
            ptr.rotation_deg = (sat_vec3_t){ 0, -24 * ONE, 0 };
            ptr.scale = (sat_vec3_t){ pe_scale, pe_scale, pe_scale };
            INTRO_MUST(sat_model_transform3d_matrix(&ptr, &pe_world));

            INTRO_MUST(sat_scene_submit_instance(&scene, &pe_inst, SAT_SCENE3D_SLOT_INHERIT, pe_proj, pe_wverts));
        }

        INTRO_MUST(sat_scene_flush_trusted(&scene));

        /* Overlay 2D banners & prompts (sat_draw_sprite_screen takes sprite CENTER coordinates) */
        if (state == INTRO_STATE_SPLASH) {
            (void)sat_draw_sprite_screen(
                &tex_banner_nintendo,
                160,
                96,
                INTRO_BANNER_NINTENDO_W,
                INTRO_BANNER_NINTENDO_H,
                0u
            );
            (void)sat_hud_text(&hud, "SEGA SATURN PORT", 96, 126);
        } else if (state == INTRO_STATE_TITLE) {
            (void)sat_draw_sprite_screen(
                &tex_banner_title,
                160,
                26,
                INTRO_BANNER_TITLE_W,
                INTRO_BANNER_TITLE_H,
                0u
            );
            if (((state_ticks / 15u) & 1u) == 0u || title_leaving != 0u) {
                (void)sat_draw_sprite_screen(
                    &tex_banner_start,
                    160,
                    186,
                    INTRO_BANNER_START_W,
                    INTRO_BANNER_START_H,
                    0u
                );
            }
            (void)sat_hud_text(&hud, "D-PAD:TURN   Z:SKIP TO CASTLE", 44, 208);
        } else if (state == INTRO_STATE_PEACH) {
            /* Slide Peach's parchment letter smoothly into place on the left */
            uint32_t slide = state_ticks < 18u ? (18u - state_ticks) * 6u : 0u;
            (void)sat_draw_sprite_screen(
                &tex_peach_card,
                (int16_t)(12 + (int)(INTRO_PEACH_LETTER_CARD_W / 2u) - (int)slide),
                (int16_t)(24 + (int)(INTRO_PEACH_LETTER_CARD_H / 2u)),
                INTRO_PEACH_LETTER_CARD_W,
                INTRO_PEACH_LETTER_CARD_H,
                0u
            );
            (void)sat_hud_text(&hud, "START: SKIP", 220, 208);
        }

        INTRO_MUST(sat_end_frame());
        /* Commit VDP2 palette, scroll, and color-offset tear-free in VBlank */
        sat_wait_vblank();
        if (pending_vdp2_pal != 0) {
            set_vdp2_palette(pending_vdp2_pal);
            pending_vdp2_pal = 0;
        }
        (void)sat_vdp2_layers_commit();

        g_sm64ds_intro_stats.frame++;
        g_sm64ds_intro_stats.state = (uint32_t)state;
        g_sm64ds_intro_stats.state_ticks = state_ticks;
    }
}
