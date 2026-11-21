/* VDP2 panorama sky; textually included by castle.c. */
#if SM64DS_VDP2_SKY
/* The sky is a cylindrical panorama (sky_panorama.h) on NBG0, behind the
 * sprite layer, instead of a camera-following VDP1 mesh: the mesh's huge
 * faces all took the flush's clipping fallback, about a third of a frame.
 * The scroll follows the camera's yaw and pitch, and is written in the
 * VBlank that swaps in the list it was computed for. */
#define SKY_PALETTE_BANK 3u
#define SKY_BAND_BYTES ((uint32_t)SKY_PANORAMA_WIDTH*SKY_PANORAMA_BAND_ROWS)
#define VDP2_REG16(offset) (*(volatile uint16_t*)(0x25F80000u+(offset)))
static uint8_t sky_band[SKY_BAND_BYTES] __attribute__((section(".wram_l"),aligned(4)));
static int32_t sky_half_w,sky_half_h;     /* screen half size in bitmap pixels, 16.16 */
typedef struct { uint32_t serial; int32_t x,y; } sky_scroll_t;
static volatile sky_scroll_t sky_pending[4];

static uint8_t sky_pixel(void *user,uint16_t x,uint16_t y) {
    (void)user;
    int32_t row=(int32_t)y-(int32_t)SKY_PANORAMA_BAND_FIRST;
    if (row<0) row=0;
    if (row>=(int32_t)SKY_PANORAMA_BAND_ROWS) row=(int32_t)SKY_PANORAMA_BAND_ROWS-1;
    return sky_band[(uint32_t)row*SKY_PANORAMA_WIDTH+x];
}

static uint32_t sky_isqrt64(uint64_t v) {
    uint64_t root=0,bit=(uint64_t)1<<62;
    while (bit>v) bit>>=2;
    while (bit) {
        if (v>=root+bit) { v-=root+bit; root=(root>>1)+bit; }
        else root>>=1;
        bit>>=2;
    }
    return (uint32_t)root;
}

/* Top-left bitmap dot (16.16) for the current camera. Column u looks along
 * azimuth -2*pi*u/width, so screen x and bitmap x grow together; row v looks
 * at tan(elevation) = (horizon - v) / focal. */
static void sky_scroll_for_camera(int32_t *out_x,int32_t *out_y) {
    const int32_t fx=camera.target.x-camera.eye.x;
    const int32_t fy=camera.target.y-camera.eye.y;
    const int32_t fz=camera.target.z-camera.eye.z;
    const uint16_t theta=sat_atan2_16(fx,fz);
    const int32_t column=(int32_t)((uint32_t)(uint16_t)(0u-theta)*SKY_PANORAMA_WIDTH);
    *out_x=(column-sky_half_w)&(int32_t)(SKY_PANORAMA_WIDTH*ONE-1);
    const uint32_t flat=sky_isqrt64((uint64_t)((int64_t)fx*fx+(int64_t)fz*fz));
    int64_t tan_pitch=flat?((int64_t)fy*ONE)/(int64_t)flat:(fy>0?4*ONE:-4*ONE);
    if (tan_pitch>4*ONE) tan_pitch=4*ONE;
    if (tan_pitch<-4*ONE) tan_pitch=-4*ONE;
    *out_y=(int32_t)((int64_t)SKY_PANORAMA_HORIZON_ROW*ONE-
                     ((int64_t)SKY_PANORAMA_FOCAL_FX16*tan_pitch)/ONE)-sky_half_h;
}

/* VBlank of the swap that shows list `serial`: NBG0 scroll registers
 * (SCXIN0/SCXDN0/SCYIN0/SCYDN0, 8 fractional bits) with plain CPU writes. */
static void sky_swap_handler(uint32_t serial,void *user) {
    (void)user;
    const sky_scroll_t *s=(const sky_scroll_t*)&sky_pending[serial&3u];
    if (s->serial!=serial) return;
    VDP2_REG16(0x070)=(uint16_t)(((uint32_t)s->x>>16)&0x07FFu);
    VDP2_REG16(0x072)=(uint16_t)((uint32_t)s->x&0xFF00u);
    VDP2_REG16(0x074)=(uint16_t)(((uint32_t)s->y>>16)&0x07FFu);
    VDP2_REG16(0x076)=(uint16_t)((uint32_t)s->y&0xFF00u);
}

/* Called once per frame before sat_end_frame: the scroll for the list that
 * call will submit. The layer manager keeps the same value, so a
 * sat_vdp2_layers_commit (intro fades) does not move the sky back. */
static void sky_update(void) {
    int32_t x,y;
    sky_scroll_for_camera(&x,&y);
    const uint32_t serial=sat_vdp1_list_serial()+1u;
    volatile sky_scroll_t *s=&sky_pending[serial&3u];
    s->serial=0u;
    s->x=x;
    s->y=y;
    s->serial=serial;
    SAT_PANIC_IF_ERROR(sat_vdp2_layer_set_scroll(SAT_VDP2_NBG0,x,y));
}

static void sky_init(void) {
    uint32_t bytes=0;
    SAT_PANIC_IF_ERROR(sat_lz_decode(sky_panorama_lz,SKY_PANORAMA_LZ_BYTES,
                                     sky_band,SKY_BAND_BYTES,&bytes));
    if (bytes!=SKY_BAND_BYTES) SAT_PANIC_IF_ERROR(SAT_ERR_IO);
    SAT_PANIC_IF_ERROR(sat_vdp2_palette_upload(sky_panorama_palette,256u,
                                               (uint16_t)(SKY_PALETTE_BANK*256u)));
    uint16_t row_words[SKY_PANORAMA_WIDTH/2u];
    SAT_PANIC_IF_ERROR(sat_vdp2_bitmap_upload_indexed8(
        0u,SKY_PANORAMA_WIDTH,SKY_PANORAMA_HEIGHT,sky_pixel,0,0,
        row_words,SKY_PANORAMA_WIDTH/2u));
    sat_vdp2_layer_config_t cfg;
    sat_vdp2_layer_config_default(SAT_VDP2_NBG0,&cfg);
    cfg.bitmap=1u;
    cfg.color_mode=SAT_VDP2_COLOR_MODE_256;
    cfg.bitmap_size=SKY_PANORAMA_HEIGHT==512u?SAT_VDP2_BITMAP_512X512:SAT_VDP2_BITMAP_512X256;
    cfg.priority=1u;            /* behind the sprite layer */
    cfg.transparent=0u;
    cfg.palette=SKY_PALETTE_BANK;
    cfg.plane_address[0]=0u;
    SAT_PANIC_IF_ERROR(sat_vdp2_layer_configure(&cfg));
    /* Screen focal length (224/2) / tan(fov_y/2) over the bitmap's
     * width/(2*pi): one bitmap dot then spans the screen pixels one radian
     * of azimuth does. */
    const sat_angle16_t half_fov=(sat_angle16_t)(((int64_t)camera.fov_y*32768)/(180*ONE)/2);
    const int64_t screen_focal=((int64_t)112*sat_cos16(half_fov)*ONE)/sat_sin16(half_fov);
    const uint32_t zoom=(uint32_t)((screen_focal*ONE)/SKY_PANORAMA_FOCAL_FX16);
    SAT_PANIC_IF_ERROR(sat_vdp2_layer_set_zoom(SAT_VDP2_NBG0,zoom,zoom));
    sky_half_w=(int32_t)(((int64_t)160*ONE*ONE)/zoom);
    sky_half_h=(int32_t)(((int64_t)112*ONE*ONE)/zoom);
    int32_t x,y;
    sky_scroll_for_camera(&x,&y);
    SAT_PANIC_IF_ERROR(sat_vdp2_layer_set_scroll(SAT_VDP2_NBG0,x,y));
    SAT_PANIC_IF_ERROR(sat_vdp1_set_erase_transparent());
    SAT_PANIC_IF_ERROR(sat_vdp2_layers_commit());
    SAT_PANIC_IF_ERROR(sat_vdp1_set_swap_handler(sky_swap_handler,0));
}

static void sky_shutdown(void) {
    (void)sat_vdp1_set_swap_handler(0,0);
    (void)sat_vdp2_layer_release(SAT_VDP2_NBG0);
}
#endif
