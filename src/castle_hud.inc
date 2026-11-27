/* debug HUD; textually included by castle.c. */
#if !SM64DS_VISUAL_DIAGNOSTICS || SM64DS_DIAG_SHOW_UI
typedef struct hud_buf {
    char data[48];
    uint8_t len;
} hud_buf_t;

static void hud_put_str(hud_buf_t *b,const char *s) {
    while (*s && b->len<40u) b->data[b->len++]=*s++;
    b->data[b->len]='\0';
}
static void hud_put_u32(hud_buf_t *b,uint32_t v) {
    char tmp[12];unsigned n=0;
    do { tmp[n++]=(char)('0'+(v%10u));v/=10u; } while (v);
    while (n && b->len<40u) b->data[b->len++]=tmp[--n];
    b->data[b->len]='\0';
}
static void hud_put_i32(hud_buf_t *b,int32_t v) {
    if (v<0) {
        if (b->len<40u) b->data[b->len++]='-';
        hud_put_u32(b,(uint32_t)(-(int64_t)v));
    } else hud_put_u32(b,(uint32_t)v);
}
static void hud_draw_box(int16_t x,int16_t y,uint16_t w,uint16_t h) {
    sat_polygon_cmd_t cmd={
        .x={(int16_t)(x-160),(int16_t)(x+(int16_t)w-160),
            (int16_t)(x+(int16_t)w-160),(int16_t)(x-160)},
        .y={(int16_t)(y-112),(int16_t)(y-112),
            (int16_t)(y+(int16_t)h-112),(int16_t)(y+(int16_t)h-112)},
        .color=SAT_RGB555(0,0,0),
        .flags=SAT_SPRITE_FLAG_HALF_TRANSPARENT
    };
    SAT_PANIC_IF_ERROR(sat_vdp1_draw_polygon(&cmd));
}
/* Full-screen tint for damage feedback (i-frames flash). */
static void hud_draw_flash(uint16_t color) {
    sat_polygon_cmd_t cmd={
        .x={-160,160,160,-160},.y={-112,-112,112,112},
        .color=color,.flags=SAT_SPRITE_FLAG_HALF_TRANSPARENT
    };
    SAT_PANIC_IF_ERROR(sat_vdp1_draw_polygon(&cmd));
}
static void hud_draw_text(int x,int y,const char *text) {
    char run[44];
    int col=0;
    while (text[col]!='\0') {
        while (text[col]==' ') ++col;
        if (text[col]=='\0') break;
        int start=col,n=0;
        while (text[col]!='\0' && text[col]!=' ' && n<(int)(sizeof(run)-1))
            run[n++]=text[col++];
        run[n]='\0';
        if (x+start*8>=320) break;
        SAT_PANIC_IF_ERROR(sat_ascii_font_draw_text_screen_indexed8(
            &font,run,x+start*8,y,8,3,0));
    }
}
static void draw_debug_hud(const sat_scene_stats_t *stats,uint32_t fps,
                           uint32_t avg_ms,uint32_t avg_cpu_ms,
                           uint32_t late_delta) {
    if (player.invuln && (player.invuln&8u)) hud_draw_flash(SAT_RGB555(24,0,0));
    if (hud_mode>=2u) return;
    hud_buf_t b;
    if (hud_mode==1u) {
        hud_draw_box(0,1,320,10);
        b.len=0;b.data[0]='\0';
        hud_put_u32(&b,fps);hud_put_str(&b,"FPS ");
        hud_put_u32(&b,avg_ms);hud_put_str(&b,"M CMD:");
        hud_put_u32(&b,stats->commands_used);hud_put_str(&b," M:");
        hud_put_i32(&b,player.feet.x/ONE);hud_put_str(&b,",");
        hud_put_i32(&b,player.feet.y/ONE);hud_put_str(&b,",");
        hud_put_i32(&b,player.feet.z/ONE);hud_put_str(&b," Y:");
        hud_put_i32(&b,camera_yaw);
        hud_draw_text(2,2,b.data);
        return;
    }
    /* 4 and 5 are the swim clips: the stroke and treading water. */
    static const char *const clip_names[6]={"IDL","WLK","RUN","JMP","SWM","FLT"};
    hud_draw_box(0,1,320,20);
    /* Line 1: timing, CPU work, VDP1 commands/capacity, late VBlanks, VRAM free */
    b.len=0;b.data[0]='\0';
    hud_put_u32(&b,fps);hud_put_str(&b,"FPS ");
    hud_put_u32(&b,avg_ms);hud_put_str(&b,"M CPU:");
    hud_put_u32(&b,avg_cpu_ms);hud_put_str(&b," CMD:");
    hud_put_u32(&b,stats->commands_used);hud_put_str(&b,"/");
    hud_put_u32(&b,stats->commands_capacity);hud_put_str(&b," L:");
    hud_put_u32(&b,late_delta);hud_put_str(&b," ");
    hud_put_u32(&b,g_sm64ds_castle_stats.texture_arena_remaining/1024u);
    hud_put_str(&b,"K");
    hud_draw_text(2,2,b.data);

    /* Line 2: submitted/culled/clipped/fallback/skipped faces + support pushes */
    b.len=0;b.data[0]='\0';
    hud_put_str(&b,"F:");hud_put_u32(&b,stats->submitted_faces);
    hud_put_str(&b," CU:");hud_put_u32(&b,stats->culled_faces);
    hud_put_str(&b," CL:");hud_put_u32(&b,stats->clipped_faces);
    hud_put_str(&b," FB:");hud_put_u32(&b,stats->fallback_faces);
    hud_put_str(&b," SK:");hud_put_u32(&b,stats->skipped_faces);
    hud_put_str(&b," SP:");hud_put_u32(&b,hud_support_pushed);
    hud_draw_text(2,11,b.data);

    hud_draw_box(0,203,320,20);
    /* Line 3: Mario position, facing, grounded/air/paused, anim, floor slope, height/walls */
    b.len=0;b.data[0]='\0';
    hud_put_str(&b,"M:");
    hud_put_i32(&b,player.feet.x/ONE);hud_put_str(&b,",");
    hud_put_i32(&b,player.feet.y/ONE);hud_put_str(&b,",");
    hud_put_i32(&b,player.feet.z/ONE);
    hud_put_str(&b," F:");hud_put_i32(&b,facing);
    hud_put_str(&b,paused?" P PAU":(player.swimming?" W ":player.grounded?" G ":" A "));
    if (!paused) hud_put_str(&b,clip<6u?clip_names[clip]:"???");
    hud_put_str(&b," NY:");
    if (hud_floor_ok) hud_put_i32(&b,hud_floor_ny_pct);
    else hud_put_str(&b,"--");
    if (!player.grounded) {
        hud_put_str(&b," H:");hud_put_i32(&b,hud_floor_height);
    } else {
        hud_put_str(&b," W:");hud_put_u32(&b,player.wall_hits);
    }
    hud_draw_text(2,204,b.data);

    /* Line 4: Camera eye position, req/actual yaw, clearance, zoom, visible props */
    b.len=0;b.data[0]='\0';
    hud_put_str(&b,"C:");
    hud_put_i32(&b,camera.eye.x/ONE);hud_put_str(&b,",");
    hud_put_i32(&b,camera.eye.y/ONE);hud_put_str(&b,",");
    hud_put_i32(&b,camera.eye.z/ONE);
    hud_put_str(&b," Y:");hud_put_i32(&b,yaw);
    hud_put_str(&b,"/");hud_put_i32(&b,camera_yaw);
    hud_put_str(&b," D:");hud_put_i32(&b,g_sm64ds_castle_stats.camera_clearance/ONE);
    hud_put_str(&b,close_camera?" N":" F");
    if (player.health<player.max_health) {
        hud_put_str(&b," HP:");hud_put_u32(&b,player.health);
        hud_put_str(&b,"/");hud_put_u32(&b,player.max_health);
        if (player.dead) hud_put_str(&b," DOWN");
    }
    if (player.coins) {hud_put_str(&b," $:");hud_put_u32(&b,player.coins);}
#ifdef CASTLE_PROPS_AVAILABLE
    if (g_stars) {hud_put_str(&b," STAR:");hud_put_u32(&b,g_stars);}
    hud_put_str(&b," T:");hud_put_u32(&b,hud_trees_drawn);
    hud_put_str(&b," S:");hud_put_u32(&b,hud_signs_drawn);
#ifdef CASTLE_CHUNK_CULLING
    hud_put_str(&b," V:");hud_put_u32(&b,hud_chunks_drawn);
#endif
#elif defined(CASTLE_ROOM_CULLING)
    hud_put_str(&b," R:");hud_put_u32(&b,current_room);
    hud_put_str(&b," V:");hud_put_u32(&b,hud_rooms_drawn);
#endif
    hud_draw_text(2,213,b.data);
}
#endif
