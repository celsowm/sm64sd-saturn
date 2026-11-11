/* Playable local-ROM castle grounds prototype. No render LOD in collision. */
#include <saturn/app.h>
#include <saturn/input.h>
#include <saturn/scene.h>
#include <saturn/skin3d.h>
#include <saturn/color.h>
#include <saturn/font.h>
#include <saturn/time.h>
#include "sm64ds_pose.h"
#include "sm64ds_background.h"
#include "sm64ds_play.h"
#include "mario_preview.h"
#include "mario_head.h"
#include "castle_scene.h"
#include "skybox_preview.h"

#define ONE SAT_FX16_ONE
#define N MARIO_PREVIEW_VERTEX_COUNT
#define F MARIO_PREVIEW_FACE_COUNT
#define T MARIO_PREVIEW_TEXTURE_COUNT
#define J MARIO_PREVIEW_JOINT_COUNT
#define CN CASTLE_VERTEX_COUNT
#define CF CASTLE_FACE_COUNT
#define CT CASTLE_TEXTURE_COUNT
#define BN SKYBOX_PREVIEW_VERTEX_COUNT
#define BF SKYBOX_PREVIEW_FACE_COUNT
#define BT SKYBOX_PREVIEW_TEXTURE_COUNT
#define HN MARIO_HEAD_VERTEX_COUNT
#define HF MARIO_HEAD_FACE_COUNT
#define HT MARIO_HEAD_TEXTURE_COUNT
#define CAP (F+CF+BF+HF)

static sat_vec3_t vertices[N],world_vertices[N];
static uint16_t indices[F*4],face_materials[F];
static sat_mesh_t mesh;
static sat_vdp1_texture_t textures[T];
static sat_scene3d_material_t materials[T];
static sat_projected_vertex_t projected[N];
static sat_scene3d_instance_t actor;
static sat_mat4_t actor_world;
static sat_skeleton_pose_joint_t pose[J];
static sat_vec3_t scales[J];
static sat_mat4_t bones[J];
static sat_aabb3_t bounds;
static sat_scene3d_face_t faces[CAP];
static uint32_t keys[CAP];
static uint16_t order[CAP];
static sat_scene_t scene;
static sat_ascii_font_t font;
static sm64ds_background_t castle,sky;
static sat_vec3_t cv[CN],cw[CN],bv[BN],bw[BN];
static uint16_t ci[CF*4],cm[CF],bi[BF*4],bm[BF];
/* Resident castle bindings are initialized once. Keep them in stock Low
 * WRAM so corrected material wrapping and detailed actor bakes fit High RAM. */
static sat_vdp1_texture_t ct[CT] __attribute__((section(".wram_l"),aligned(4)));
static sat_scene3d_material_t cmat[CT] __attribute__((section(".wram_l"),aligned(4)));
static sat_vdp1_texture_t bt[BT];
static sat_scene3d_material_t bmat[BT];
static sat_projected_vertex_t cp[CN],bp[BN];
static sm64ds_background_t head;
static sat_vec3_t hv[HN],hw[HN];
static uint16_t hi[HF*4],hm[HF];
static sat_vdp1_texture_t ht[HT];
static sat_scene3d_material_t hmat[HT];
static sat_projected_vertex_t hp[HN];
static sm64ds_player_t player;
static sat_camera3d_t camera;
static int yaw=0,paused=0,facing=180,close_camera=0;
static uint16_t clip=0;
static int32_t anim_time=0;

/* Stable debugger telemetry: all values are captured from real frames. */
volatile struct {
    uint32_t magic,frames,ticks,jumps,landings,wall_hits,resets;
    int32_t x,y,z,velocity_y,camera_x,camera_y,camera_z;
    uint32_t grounded,clip,commands,skipped,faces,paused;
} g_sm64ds_castle_stats={.magic=0x43415331};

static void skin(void) {
    const sat_skeleton_clip_t *c=&mario_preview_clips[clip];
    SAT_PANIC_IF_ERROR(sat_clip_sample(c,anim_time,pose,J));
    SAT_PANIC_IF_ERROR(sm64ds_clip_sample_scale(&mario_preview_scale_clips[clip],c,anim_time,scales,J));
    SAT_PANIC_IF_ERROR(sm64ds_pose_world_matrices(&mario_preview_skeleton,pose,scales,bones,J));
    SAT_PANIC_IF_ERROR(sat_skin_update_mesh(&mario_preview_skin,bones,J,&mesh,0,&bounds));
}
static void reset(void) {
    sm64ds_player_reset(&player);yaw=0;facing=180;anim_time=0;
}
static void update_camera(void) {
    camera.target=(sat_vec3_t){player.feet.x,player.feet.y+8*ONE,player.feet.z};
    int32_t s=sat_sin_deg(yaw*ONE),c=sat_cos_deg(yaw*ONE);
    int32_t distance=(close_camera?35:65)*ONE;
    sat_vec3_t desired={camera.target.x+sat_fx16_mul(s,distance),camera.target.y+distance*30/65,
                       camera.target.z+sat_fx16_mul(c,distance)};
    int32_t t=sm64ds_camera_fraction(&castle_collision,&camera.target,&desired);
    camera.eye=(sat_vec3_t){camera.target.x+sat_fx16_mul(desired.x-camera.target.x,t),
        camera.target.y+sat_fx16_mul(desired.y-camera.target.y,t),
        camera.target.z+sat_fx16_mul(desired.z-camera.target.z,t)};
    SAT_PANIC_IF_ERROR(sat_camera3d_update(&camera));
}
static void simulation(const sat_pad_state_t *pad,uint8_t jump) {
    if(pad->held&SAT_PAD_L)yaw=(yaw+358)%360;
    if(pad->held&SAT_PAD_R)yaw=(yaw+2)%360;
    int x=((pad->held&SAT_PAD_RIGHT)!=0)-((pad->held&SAT_PAD_LEFT)!=0);
    int z=((pad->held&SAT_PAD_DOWN)!=0)-((pad->held&SAT_PAD_UP)!=0);
    int32_t speed=(pad->held&SAT_PAD_B)?ONE*3/2:ONE*3/4;
    if(x&&z)speed=sat_fx16_mul(speed,46341);
    int32_t s=sat_sin_deg(yaw*ONE),c=sat_cos_deg(yaw*ONE);
    int32_t dx=sat_fx16_mul(x*c+z*s,speed),dz=sat_fx16_mul(z*c-x*s,speed);
    if(x||z) {
        int heading=z<0?(x<0?225:x>0?135:180):z>0?(x<0?315:x>0?45:0):(x<0?270:90);
        facing=(heading+yaw)%360;
    }
    sm64ds_player_step(&player,&castle_collision,dx,dz,jump,(pad->held&SAT_PAD_B)!=0);
    uint16_t next=!player.grounded?3:player.moving?(player.running?2:1):0;
    if(next!=clip) {clip=next;anim_time=0;}
    anim_time+=ONE/60;
}

int main(void) {
    const sat_video_config_t video={320,224,SAT_VIDEO_AUTO,0};
    SAT_PANIC_IF_ERROR(sat_init(&video));
    /* This scene takes several fields to draw. Keep the completed picture
     * visible until VDP1 reaches END instead of swapping a partial list. */
    SAT_PANIC_IF_ERROR(sat_vdp1_set_frame_mode(SAT_VDP1_FRAME_ON_SUBMIT));
    uint32_t bytes=sat_model_vram_estimate_bytes(&mario_preview_model)+
        sat_model_vram_estimate_bytes(&castle_model)+sat_model_vram_estimate_bytes(&skybox_preview_model)+
        sat_model_vram_estimate_bytes(&mario_head_model);
    if(bytes>440u*1024u)SAT_PANIC_IF_ERROR(SAT_ERR_CAPACITY);
    SAT_PANIC_IF_ERROR(sat_mesh_init(&mesh,vertices,N,indices,F));
    SAT_PANIC_IF_ERROR(sat_model_copy_to_mesh(&mario_preview_model,&mesh));
    SAT_PANIC_IF_ERROR(sat_model_upload_textures(&mario_preview_model,textures,T));
    for(uint16_t i=0;i<T;++i) {
        materials[i].kind=SAT_SCENE3D_INDEXED_TEXTURED;materials[i].texture=&textures[i];
        materials[i].color_calc_slot=SAT_INDEXED_SOLID_OPAQUE;
    }
    for(uint16_t i=0;i<F;++i)face_materials[i]=mario_preview_model.face_texture_indices[i];
    const sm64ds_background_buffers_t cb={cv,ci,ct,cmat,cm,CN,CF,CT};
    const sm64ds_background_buffers_t bb={bv,bi,bt,bmat,bm,BN,BF,BT};
    const sm64ds_background_buffers_t hb={hv,hi,ht,hmat,hm,HN,HF,HT};
    SAT_PANIC_IF_ERROR(sm64ds_background_init(&castle,&castle_model,&cb));
    SAT_PANIC_IF_ERROR(sm64ds_background_init(&sky,&skybox_preview_model,&bb));
    SAT_PANIC_IF_ERROR(sm64ds_background_init(&head,&mario_head_model,&hb));
    head.instance.pass=SM64DS_ACTOR_PASS;head.instance.cull_backfaces=1;
    castle.instance.pass=SM64DS_ACTOR_PASS;
    castle.instance.cull_backfaces=1;
    actor=(sat_scene3d_instance_t){.mesh=&mesh,.materials=materials,.material_count=T,
        .face_materials=face_materials,.world=&actor_world,.pass=SM64DS_ACTOR_PASS,.cull_backfaces=1};
    SAT_PANIC_IF_ERROR(sat_scene_init(&scene,faces,keys,order,CAP));
    SAT_PANIC_IF_ERROR(sat_ascii_font_init_8x8_indexed8(&font,SAT_COLOR_WHITE,0,3));
    player.spawn=(sat_vec3_t){0,100*ONE,256*ONE};
    int32_t floor;
    if(!sm64ds_floor(&castle_collision,player.spawn.x,player.spawn.z,512*ONE,&floor))
        SAT_PANIC_IF_ERROR(SAT_ERR_INVALID_ARG);
    player.spawn.y=floor;reset();
    camera.up=(sat_vec3_t){0,ONE,0};camera.fov_y=60*ONE;
    camera.aspect=sat_fx16_div(320*ONE,224*ONE);camera.near_z=ONE;camera.far_z=1600*ONE;
    uint32_t previous=sat_time_ms(),accumulator=0;
    uint16_t jump_pending=0;
    while(1) {
        SAT_PANIC_IF_ERROR(sat_wait_vblank());
        sat_pad_state_t pad={0};SAT_PANIC_IF_ERROR(sat_pad_poll(&pad));
        uint32_t now=sat_time_ms(),elapsed=now-previous;previous=now;
        if(elapsed>250)elapsed=250;
        if(pad.pressed&SAT_PAD_START)paused=!paused;
        if(pad.pressed&SAT_PAD_C)reset();
        if(pad.pressed&SAT_PAD_X)close_camera=!close_camera;
        jump_pending|=pad.pressed&SAT_PAD_A;
        if(!paused) {
            accumulator+=elapsed*60;
            while(accumulator>=1000) {simulation(&pad,jump_pending!=0);jump_pending=0;accumulator-=1000;}
        } else {accumulator=0;jump_pending=0;}
        skin();
        sat_model_transform3d_t transform;
        sat_model_transform3d_identity(&transform);
        transform.position=player.feet;transform.position.y-=bounds.center.y-bounds.half.y;
        transform.rotation_deg.y=facing*ONE;
        SAT_PANIC_IF_ERROR(sat_model_transform3d_matrix(&transform,&actor_world));
        SAT_PANIC_IF_ERROR(sat_mat4_multiply(&head.world,&actor_world,&bones[15]));
        update_camera();
        SAT_PANIC_IF_ERROR(sat_set_clear_color(SAT_RGB555(12,20,30)));
        SAT_PANIC_IF_ERROR(sat_begin_frame());
        SAT_PANIC_IF_ERROR(sat_scene_begin(&scene,&camera,camera.near_z,320,224,112));
        SAT_PANIC_IF_ERROR(sm64ds_background_submit(&sky,&scene,&camera.eye,bp,bw));
        SAT_PANIC_IF_ERROR(sat_scene_submit_instance(&scene,&castle.instance,SAT_SCENE3D_SLOT_INHERIT,cp,cw));
        SAT_PANIC_IF_ERROR(sat_scene_submit_instance(&scene,&actor,SAT_SCENE3D_SLOT_INHERIT,projected,world_vertices));
        SAT_PANIC_IF_ERROR(sat_scene_submit_instance(&scene,&head.instance,SAT_SCENE3D_SLOT_INHERIT,hp,hw));
        SAT_PANIC_IF_ERROR(sat_scene_flush_trusted(&scene));
        SAT_PANIC_IF_ERROR(sat_ascii_font_draw_text_screen_indexed8(&font,
            paused?"PAUSED - START TO CONTINUE":"D-PAD MOVE  A JUMP  B RUN",8,8,8,3,0));
        SAT_PANIC_IF_ERROR(sat_ascii_font_draw_text_screen_indexed8(&font,"L/R CAM  X ZOOM  C RESET  START PAUSE",8,208,8,3,0));
        sat_scene_stats_t stats={0};sat_scene_stats(&scene,&stats);
        ++g_sm64ds_castle_stats.frames;g_sm64ds_castle_stats.ticks=player.ticks;
        g_sm64ds_castle_stats.jumps=player.jumps;g_sm64ds_castle_stats.landings=player.landings;
        g_sm64ds_castle_stats.wall_hits=player.wall_hits;g_sm64ds_castle_stats.resets=player.resets;
        g_sm64ds_castle_stats.x=player.feet.x;g_sm64ds_castle_stats.y=player.feet.y;g_sm64ds_castle_stats.z=player.feet.z;
        g_sm64ds_castle_stats.velocity_y=player.velocity_y;g_sm64ds_castle_stats.grounded=player.grounded;
        g_sm64ds_castle_stats.camera_x=camera.eye.x;g_sm64ds_castle_stats.camera_y=camera.eye.y;g_sm64ds_castle_stats.camera_z=camera.eye.z;
        g_sm64ds_castle_stats.clip=clip;g_sm64ds_castle_stats.commands=stats.commands_used;
        g_sm64ds_castle_stats.skipped=stats.skipped_faces;g_sm64ds_castle_stats.faces=stats.submitted_faces;
        g_sm64ds_castle_stats.paused=paused;
        SAT_PANIC_IF_ERROR(sat_end_frame());
    }
}
