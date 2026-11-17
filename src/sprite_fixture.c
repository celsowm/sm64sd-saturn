/* ROM-free distorted-sprite triangle UV fixture. Coordinates are screen based
 * in the comments and VDP1-local in the actual command. */
#include <saturn/app.h>
#include <saturn/color.h>
#include <saturn/vdp1.h>
#include "sprite_fixture_data.h"

int main(void) {
    const sat_video_config_t video={320,224,SAT_VIDEO_AUTO,0};
    SAT_PANIC_IF_ERROR(sat_init(&video));
    SAT_PANIC_IF_ERROR(sat_vdp1_set_frame_mode(SAT_VDP1_FRAME_ON_SUBMIT));
    sat_vdp1_texture_t texture={0};
    SAT_PANIC_IF_ERROR(sat_tex_upload_indexed8(&texture,fixture_pixels,32,32,fixture_palette,1));
    /* A=(40,32), B=(232,32), C=D=(40,192). */
    const sat_distorted_sprite_cmd_t sprite={.x={-120,72,-120,-120},
        .y={-80,-80,80,80},.texture=&texture};
    for (;;) {
        SAT_PANIC_IF_ERROR(sat_wait_vblank());
        SAT_PANIC_IF_ERROR(sat_set_clear_color(SAT_RGB555(0,0,31)));
        SAT_PANIC_IF_ERROR(sat_begin_frame());
        SAT_PANIC_IF_ERROR(sat_draw_sprite_distorted(&sprite));
        SAT_PANIC_IF_ERROR(sat_end_frame());
    }
}
