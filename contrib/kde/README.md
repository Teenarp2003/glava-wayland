# KDE Plasma: bars on each connected monitor

This optional Python supervisor runs one native Wayland GLava renderer per connected, enabled KDE output. It checks `kscreen-doctor -j` every two seconds, pins each process using `GLAVA_OUTPUT`, and adjusts the surface for the output's scale and rotation. Unplugging/disabling an output stops only that renderer; reconnecting starts a new one. Resolution/scale and bottom-panel height changes restart only the affected renderer. A failed display query preserves current processes until discovery recovers.

The accompanying native backend changes bind `wl_output` version4 names, reject absent requested names rather than silently falling back, and handle output removal and layer-surface closure. A nonblocking event pump reads Wayland events between frames. KWin supports the required layer-shell protocol; it need not be a wlroots compositor.

Bars are click-through, on the **bottom** layer above wallpaper and below normal apps. Default settings use purple/lilac, double the stock amplitude (600 instead of300), a600-logical-pixel surface, automatic bottom-panel clearance and60fps. Settings are in `settings.json`; `bottom_margin` is the fallback when no matching panel has been discovered. The baseline stays at the bottom; increased height does not move it halfway up the screen. `setswap=0` plus the frame limiter avoids waiting indefinitely on EGL frame callbacks for obscured surfaces.

With `auto_panel_margin: true`, the supervisor queries Plasma's panel configuration through `qdbus6` each polling cycle. It matches the panel's logical screen rectangle to the KScreen output geometry rather than assuming their screen indexes agree. Bottom clearance is the largest matching bottom-panel height plus `panel_extra_gap` (default0). For floating-panel breathing room, use a global gap or a connector-specific preference, for example `"outputs": {"HDMI-1": {"panel_extra_gap": 22}}`. Panel size changes take effect automatically; only the affected renderer restarts.

On a transient Plasma/D-Bus failure, the most recent successful panel snapshot remains in use. Before the first successful query, or for an output with no matching bottom panel, `bottom_margin` supplies manual clearance. Both `bottom_margin` and `auto_panel_margin` can be overridden per output. Set `auto_panel_margin: false` to retain strictly manual placement. Changing the JSON preferences still requires restarting the supervisor.

The configured panel height is tracked, not the transient animation of adaptive floating/defloating or auto-hide visibility. Full configured clearance is reserved even for an auto-hiding bottom panel; `panel_extra_gap` controls additional spacing without moving or resizing the panel itself.

## Install as a user

Dependencies on Arch: `base-devel meson ninja git python libkscreen qt6-tools wayland wayland-protocols mesa libglvnd libpulse`. PipeWire's PulseAudio server or PulseAudio supplies playback monitoring. Install dependencies using your usual package management before building.

```sh
git clone --recurse-submodules https://github.com/boredhero/glava-wayland.git ~/.local/share/glava-wayland
cd ~/.local/share/glava-wayland
git checkout main
meson setup build -Denable_wayland=true -Ddisable_glx=true -Ddisable_obs=true -Dstandalone=true
ninja -C build
mkdir -p ~/.config/glava-desktop ~/.config/systemd/user
cp contrib/kde/{rc.glsl,bars.glsl,settings.json} ~/.config/glava-desktop/
cp contrib/kde/glava-desktop.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now glava-desktop.service
```

No global GLava installation or privileged service is required. To try it without autostart, omit the service commands and run:

```sh
python3 contrib/kde/glava-desktop.py --source "$PWD" --config ~/.config/glava-desktop
```

Each renderer gets a separate temporary `userconf` directory under `$XDG_RUNTIME_DIR/alien-glava-UID/`. The supervisor supplies the standalone shader fallback through a symlink; it never changes your normal `~/.config/glava` setup. Logs for each output live alongside its `userconf`. The default script paths match the original Alien setup, but the service above explicitly sets generic paths.

After changing settings, `systemctl --user restart glava-desktop.service`. Stop/remove autostart with `systemctl --user disable --now glava-desktop.service`. It uses the graphical session target and closes its children when stopped.

## Output selection without supervisor

```sh
GLAVA_OUTPUT=DP-1 ./build/glava --backend wayland
```

With a standalone build run from the build directory (`GLAVA_OUTPUT=DP-1 ./glava ...`). Use your compositor's exact connector name. A missing requested output exits nonzero before creating a surface; no `GLAVA_OUTPUT` retains first-output behavior. Named selection needs `wl_output` v4, available on tested KWin6.8. Discovery on older compositors can still use the unnamed default behavior.

## Validation and limits

Tested on KDE Plasma/KWin6.8 Wayland with simultaneous1920×1080@1x and3840×2160@1.5x outputs. Both selected names and live renderer logs were checked. The Python tests simulate unplug/replug/resize and panel-height changes, check unaffected processes remain running, and verify cached heights survive a failed panel query. Native tests exercise output removal/closure callbacks and real name discovery without creating windows. No physical monitor unplug is claimed by these tests.

```sh
python3 contrib/kde/tests/test_manager.py
```

See [native test commands](tests/README-native.md). Output-change detection takes up to the polling interval (default2seconds), plus termination grace if a driver stalls. This supervisor is KDE-specific; other compositors can use `GLAVA_OUTPUT` with their own output-management scripts. No audio playback is started by the visualizer. The shader's gain affects bar size, not speaker volume.
