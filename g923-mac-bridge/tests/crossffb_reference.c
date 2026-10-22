// SPDX-License-Identifier: GPL-3.0-only
// Runs ONLY pure functions from the pinned MIT reference. No wheel/app startup.
#define main crossffb_unused_app_main
#include "../vendor/CrossFFB-reference/native_bridge/g29_ffb_bridge.c"
#undef main
int main(void) {
    for (int value=-10000;value<=10000;value+=100) {
        uint8_t cmd[7];make_app_constant_command(cmd,magnitude_to_force_byte(value));
        printf("%d",value);for(int i=0;i<7;i++)printf(" %u",cmd[i]);printf("\n");
    }
    int value;while(scanf("%d", &value)==1) {
        uint8_t cmd[7];make_app_constant_command(cmd,magnitude_to_force_byte(value));
        printf("%d",value);for(int i=0;i<7;i++)printf(" %u",cmd[i]);printf("\n");
    }
    return 0;
}
