# PM99 visual-upscale POC

This folder contains a complete local copy of the PM99 game data plus two
separate Wine launch paths. Nothing in `game/` has been rewritten: enhanced
mode loads a local DirectDraw presentation shim; original mode forces Wine's
builtin DirectDraw implementation and ignores that shim.

From an Ubuntu desktop session, install the local runtime prerequisites once:

```bash
sudo apt install wine xdotool wmctrl imagemagick x11-utils python3-opencv python3-numpy
```

Run the enhanced POC at your current desktop resolution:

```bash
./run-enhanced.sh
```

Run the original comparison:

```bash
./run-original.sh
```

The two modes use independent Wine prefixes. Enhanced mode keeps PM99's
native 640x480 simulation and DirectDraw primary surface. It presents
completed snapshots of that normal X11 window in a 4:3 surface, with Scale2x plus a restrained final fit for menus
and the adaptive match-only scaler for a live 3D pitch. It deliberately does
not resize, hide, move, or forward clicks through the native PM99 window. This
is the stable visual POC. The large surface is input-transparent; it does not
yet make a click on an enlarged button clickable. That feature remains
separate until it can be implemented as a direct, in-process coordinate bridge
rather than the former hide/raise forwarding cycle.

The stable presenter never reads the live RGB565 export or asks DirectDraw to
allocate a host-sized primary surface, so it cannot display a partially
written DirectDraw frame or mutate PM99's renderer. It starts after the native
PM99 window has mapped and submits no more than 30 completed presentation frames per
second. Your desktop resolution affects the final fractional fit (and thus
sharpness), but it should not cause the display to mutate or the PM99 window
to resize.

To force a particular host geometry, for example a 1920x1080 monitor:

```bash
PM99_POC_SCREEN_GEOMETRY=1920x1080x16 ./run-enhanced.sh
```

Runtime logs and captured RGB565 frames are written under `runtime/`; the
game data itself is unchanged. `build-manifest.json` records source provenance
and hashes for the executable, MFC runtime, and DirectDraw shim.
