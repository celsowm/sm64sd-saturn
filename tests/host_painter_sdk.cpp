#include <cassert>
#include <cstdint>
#include "sm64ds_painter.h"
#include "src/graphics/3d/rendering/logic.hpp"

static uint32_t random_word(uint32_t &state) {
    state^=state<<13;state^=state>>17;state^=state<<5;return state;
}

int main() {
    uint32_t state=0x12934abcu;
    for(unsigned trial=0;trial<1000;++trial) {
        uint32_t original[256],sorted[256];uint16_t order[256];
        unsigned groups=1+trial%8,count=1+random_word(state)%256;
        for(unsigned i=0;i<count;++i) {
            uint32_t g=random_word(state)%groups;
            uint32_t depth=random_word(state)&0xfffffeu;
            original[i]=sorted[i]=(g<<24)|depth;
            if((random_word(state)&63u)==0) original[i]=sorted[i]=0xffffffffu;
        }
        saturn::core::render3d::paint_order_grouped_buckets(sorted,count,order,24);
        for(unsigned g=0;g<groups;++g) {
            sm64ds_painter_bucket_plan_t plan;
            bool exists=sm64ds_painter_bucket_plan(original,count,g,&plan)!=0;
            int base=-1;
            for(unsigned i=0;i<count;++i) {
                if(original[i]==0xffffffffu || original[i]>>24!=g) continue;
                assert(exists);
                unsigned local=((original[i]&0xffffffu)-plan.low)>>plan.shift;
                int current=(int)sorted[i]-(int)local;
                if(base<0)base=current;
                assert(current==base);
            }
            assert(exists==(base>=0));
        }
    }
}
