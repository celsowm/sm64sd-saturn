/* Scan locally generated collision for continuous sloped-floor samples.
 * Build on the host with the generated castle_scene.c and sm64ds_play.c;
 * it calls the same fixed-point floor query as the Saturn prototype. */
#include <stdint.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "castle_scene.h"

int main(int argc,char **argv) {
    if(argc==5 && !strcmp(argv[1],"--point")) {
        char *end[3];
        double x=strtod(argv[2],&end[0]),z=strtod(argv[3],&end[1]),ceiling=strtod(argv[4],&end[2]);
        if(end[0]==argv[2] || end[1]==argv[3] || end[2]==argv[4] ||
           *end[0] || *end[1] || *end[2] || !isfinite(x) || !isfinite(z) || !isfinite(ceiling) ||
           x < -16000 || x > 16000 ||
           z < -16000 || z > 16000 || ceiling < -16000 || ceiling > 16000) {
            fprintf(stderr,"invalid point\n");return 2;
        }
        int32_t height;sat_vec3_t normal;
        if(!sm64ds_floor_normal(&castle_collision,(int32_t)(x*65536),(int32_t)(z*65536),
                                (int32_t)(ceiling*65536),&height,&normal)) {
            puts("no floor");return 1;
        }
        printf("x,z,height,nx,ny,nz\n%.6f,%.6f,%.6f,%.6f,%.6f,%.6f\n",
               x,z,height/65536.0,normal.x/65536.0,normal.y/65536.0,normal.z/65536.0);
        return 0;
    }
    if(argc!=1 && argc!=5) {
        fprintf(stderr,"usage: %s [min max grid_step ceiling] | --point x z ceiling\n",argv[0]);
        return 2;
    }
    int lo=argc==5?atoi(argv[1]):-512,hi=argc==5?atoi(argv[2]):512;
    int step=argc==5?atoi(argv[3]):16,ceiling=argc==5?atoi(argv[4]):100;
    if(lo < -16000 || hi > 16000 || lo>hi || step<1 || ceiling < -16000 || ceiling>16000) {
        fprintf(stderr,"invalid scan bounds\n");return 2;
    }
    puts("x,z,height,dx2,dz2");
    for(int z=lo;z<=hi;z+=step) for(int x=lo;x<=hi;x+=step) {
        int32_t y,xx,zz;
        if(!sm64ds_floor(&castle_collision,x*65536,z*65536,ceiling*65536,&y) ||
           !sm64ds_floor(&castle_collision,(x+2)*65536,z*65536,ceiling*65536,&xx) ||
           !sm64ds_floor(&castle_collision,x*65536,(z+2)*65536,ceiling*65536,&zz)) continue;
        int32_t dx=xx-y,dz=zz-y,ax=dx<0?-dx:dx,az=dz<0?-dz:dz;
        if((ax<6554 && az<6554) || ax>2*65536 || az>2*65536) continue;
        printf("%d,%d,%.4f,%.4f,%.4f\n",x,z,y/65536.0,dx/65536.0,dz/65536.0);
    }
    return 0;
}
