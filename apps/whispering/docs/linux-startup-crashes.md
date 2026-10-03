# Linux WebKitGTK crashes

## Current host

Whispering is a Svelte SPA hosted by Epicenter. Its native entrypoint is
`apps/epicenter/src-tauri/src/main.rs`, not the removed Whispering Tauri crate.
The Linux renderer workaround belongs at this host entrypoint so it takes effect
before GTK/WebKit initialization and before the async runtime starts.

On Wayland, the entrypoint sets `WEBKIT_DISABLE_DMABUF_RENDERER=1` unless the
user already supplied a value. An empty `WAYLAND_DISPLAY` alone does not enable
the workaround. An explicit `XDG_SESSION_TYPE=wayland` does.

This addresses the DMA-BUF failure associated with
[issue #1316](https://github.com/EpicenterHQ/epicenter/issues/1316). The workaround
does not establish that every Linux crash has that cause.

## Navigation

The Whispering root layout skips View Transitions when the platform OS is Linux
and a Tauri runtime is present. During the original local investigation,
WebKitGTK crashed in `AcceleratedBackingStore::update` when clicking navigation
buttons even with DMA-BUF disabled. Skipping that renderer path keeps navigation
working. Other platforms retain transitions; the current reduced-motion guard
is preserved.

## CPU and model downloads

The current Linux host enables `transcribe-cpp`'s `dynamic-backends` feature.
The locked `transcribe-cpp-sys` 0.1.2 configures
`TRANSCRIBE_X86_CONSERVATIVE=ON` and `GGML_CPU_ALL_VARIANTS=ON` on x86, building
CPU modules for runtime instruction-set selection over a compatible baseline.
The old `whisper-rs-sys` CMake hook and local AVX2 options are obsolete here.

The current model UI registers a transfer before checking whether the model
is installed. It blocks a second transfer of that model while the first is
active. The native catalog delegates downloading to `hf-hub` 0.5.0, which locks
the cache blob and writes an incomplete file before renaming it into place.
These mechanisms replace the old Svelte downloader fix; the old component and
its filesystem capability are not restored by the merge. This describes cache
publication, not a new cryptographic verification guarantee.

The legacy standalone build, model repair and performance measurements remain
in the historical branch `codex/fix-whispering-linux-crash`. Merging these source
changes does not replace the executable already installed on the local PC.

## Verification

From the repository root:

```bash
python3 apps/whispering/tests/linux-startup.test.py
bun test apps/whispering/tests/navigation.test.js
```

The Python test compiles the real Epicenter entrypoint against a small runtime
probe; nine environment cases check renderer selection before runtime startup.
The navigation tests execute the real Svelte callback with browser API mocks.
These checks require Rust and Bun/Svelte but no GTK, microphone or model load.
They do not replace a complete native build or an interactive WebKitGTK test.

For a full build, follow the current [Epicenter README](../../epicenter/README.md).
On a machine with limited memory, use `CARGO_BUILD_JOBS=1` and
`CMAKE_BUILD_PARALLEL_LEVEL=1` and avoid concurrent native builds.
