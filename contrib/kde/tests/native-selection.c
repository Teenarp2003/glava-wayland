/* SPDX-License-Identifier: GPL-3.0-only */
/* Real Wayland discovery/event-pump test; never creates a wl_surface. */
#include <assert.h>
#include <stdio.h>
#define GLAVA_WAYLAND 1
#include "glava/wayland_wcb.c"

int main(int argc, char** argv) {
    if (argc < 2) {
        fprintf(stderr, "Usage: %s OUTPUT_NAME [OUTPUT_NAME ...]\n", argv[0]);
        return 2;
    }
    for (int i = 1; i < argc; ++i) {
        assert(setenv("GLAVA_OUTPUT", argv[i], 1) == 0);
        init();
        assert(selected_output && selected_output->name);
        assert(strcmp(selected_output->name, argv[i]) == 0);
        struct wlwin window = {0};
        pump_events(&window);
        assert(!window.should_close);

        /* Simulate only our callback: do not remove/disable a real output. */
        registry_global_remove(NULL, registry, selected_output->registry_name);
        pump_events(&window);
        assert(window.should_close);
        terminate();
        assert(!outputs && !display && !selected_output);
    }
    puts("PASS: exact named selection, nonblocking pump, simulated removal, clean reinitialization; no surfaces created");
    return 0;
}
