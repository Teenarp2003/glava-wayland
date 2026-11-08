# Native Wayland regression tests

These harnesses exercise the actual `glava/wayland_wcb.c` implementation. They are licensed under GPL-3.0, like the project (`LICENSE`). They do not patch the compositor or disconnect any physical monitor.

Run the commands below **from the repository root**, after configuring and building GLava with native Wayland support. They assume the Meson build directory is `build`:

```sh
meson setup build -Denable_wayland=true -Ddisable_glx=true -Ddisable_obs=true -Dstandalone=true
ninja -C build
mkdir -p build/tests
```

If `build` already exists, keep its configuration or use `meson configure build` rather than rerunning setup. Tests need the same compiler and Wayland/EGL development headers as GLava. Assertions are part of the tests: do **not** compile with `-DNDEBUG`.

## Output-removal callback lifecycle (no running compositor required)

```sh
cc -ffunction-sections -fdata-sections \
  -I. -Iglava -Ibuild \
  $(pkg-config --cflags wayland-client wayland-egl egl) \
  contrib/kde/tests/native-lifecycle.c \
  -Wl,--gc-sections -o build/tests/native-lifecycle
./build/tests/native-lifecycle
```

Covers unrelated output removal, selected output removal, duplicate removal, a distinct replug registry ID, and compositor-initiated layer-surface closure. Unused backend functions are discarded by the linker; no Wayland connection or EGL context is created. The synthetic disconnect diagnostic is expected.

## Real output discovery and event pump (Wayland session required)

```sh
cc -ffunction-sections -fdata-sections \
  -I. -Iglava -Ibuild \
  $(pkg-config --cflags wayland-client wayland-egl egl) \
  contrib/kde/tests/native-selection.c \
  build/wlr-layer-shell-unstable-v1-protocol.c \
  build/xdg-shell-protocol.c \
  -Lbuild -Wl,-rpath,'$ORIGIN/..' -lglava \
  $(pkg-config --libs wayland-client wayland-egl egl) \
  -Wl,--gc-sections -o build/tests/native-selection
```

Run with the names reported by your compositor (`kscreen-doctor -o` or `wayland-info`), for example:

```sh
timeout 5 ./build/tests/native-selection DP-2 HDMI-A-1
```

Each argument must identify a currently advertised output. The harness checks exact name selection, an idle/nonblocking event pump, simulated selected-output removal, and clean teardown/reinitialization. It connects to the real compositor and initializes EGL, but **never creates a `wl_surface` or draws a window**. The removal simulation only invokes this process's listener callback; it does not alter your displays.

To test failure without silently selecting a different monitor:

```sh
./build/tests/native-selection ALIEN-NONEXISTENT-OUTPUT
```

That command must exit **1** with an `unavailable; refusing fallback` diagnostic, listing the available names. Exit 124 under `timeout` would indicate a hang, not a successful negative test. An older compositor without `wl_output` version 4 cannot provide connector names and should fail explicit named selection instead of choosing another display.

These tests do not substitute for a real unplug/replug test or exercise `eglSwapBuffers` under output loss. The desktop manager tests cover process reconciliation separately. A supervisor should still bound shutdown time for a driver or compositor that blocks inside EGL.
