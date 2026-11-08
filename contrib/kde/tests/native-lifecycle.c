/* SPDX-License-Identifier: GPL-3.0-only */
/* Callback lifecycle regression test: no compositor, window or display change. */
#include <assert.h>
#include <stdio.h>
#define GLAVA_WAYLAND 1
#include "glava/wayland_wcb.c"

int main(void) {
    struct output_info first = {.registry_name = 10, .name = "TEST-OUTPUT-A"};
    struct output_info second = {.registry_name = 11, .name = "TEST-OUTPUT-B"};
    struct output_info replug = {.registry_name = 12, .name = "TEST-OUTPUT-A"};
    first.next = &second;
    second.next = &replug;
    outputs = &first;
    selected_output = &first;

    registry_global_remove(NULL, NULL, 999);
    assert(!selected_output_removed && !first.removed && !second.removed);
    registry_global_remove(NULL, NULL, 11);
    assert(second.removed && !selected_output_removed);
    registry_global_remove(NULL, NULL, 10);
    assert(first.removed && selected_output_removed && !replug.removed);
    registry_global_remove(NULL, NULL, 10);
    assert(selected_output_removed);

    struct wlwin window = {0};
    layer_surface_closed(&window, NULL);
    assert(window.should_close);
    puts("PASS: unrelated/duplicate removal, selected-output removal, distinct replug, and compositor closure");
    return 0;
}
