# Linux startup crashes

This fix targets the standalone Whispering 7.11.0 desktop source. Newer Epicenter
revisions moved the native host to `apps/epicenter/src-tauri`.

## Wayland protocol error: issue #1316

The issue reports `Gdk-Message: Error 71 (Protocol error) dispatching to Wayland
display`. WebKitGTK can abort the process when its DMA-BUF rendering path is
incompatible with the graphics driver/compositor. Rust's panic hook and frontend
error handling cannot recover from that process termination.

The Linux entrypoint sets `WEBKIT_DISABLE_DMABUF_RENDERER=1` on Wayland before
calling `run()`. This order matters: `run()` has `#[tokio::main]`, which creates
worker threads before executing its body. Process environment changes belong
before that runtime and before GTK/WebKit initialization.

An existing renderer setting is preserved, including `0` for an explicit opt-out.
X11 sessions retain the default renderer. The compatible path can reduce rendering
performance. This is an application-level mitigation for an upstream renderer
bug, not a repair to WebKitGTK or a guarantee against every graphics failure.

The arboard messages report a clipboard fallback; they are not evidence of the
fatal graphics error. The AppImage log in the issue contains no crash backtrace,
so the cause of its interaction crash cannot be established from that log alone.

References:

- [Whispering issue #1316](https://github.com/EpicenterHQ/epicenter/issues/1316)
- [Tauri Linux graphics guidance](https://v2.tauri.app/develop/debug/linux-graphics/)
- [WebKitGTK bug #280210](https://bugs.webkit.org/show_bug.cgi?id=280210)

## Crash when navigating to Settings or Home

The locally rebuilt production executable also crashed when switching routes.
GDB captured SIGSEGV in the main process, and the Ubuntu debug symbols identified
`WebKit::AcceleratedBackingStore::update`, called from
`WebKit::WebPageProxy::enterAcceleratedCompositingMode`. The same crash occurred
with `WEBKIT_DISABLE_COMPOSITING_MODE=1`.

The root Svelte layout calls `document.startViewTransition()` for every route
change. That animation enters accelerated compositing even on the affected
software-rendering setup. Checking whether the API exists does not establish
that the native renderer can execute it safely.

The navigation callback skips view transitions in the Linux desktop app. It
returns immediately, letting SvelteKit finish normal client-side navigation.
Browser builds and other desktop platforms retain the animation when supported.
No GPU or compositing override was added for this navigation failure.

The regression tests execute the layout's actual callback and verify that Linux
desktop navigation never invokes the failing API:

```bash
bun test apps/whispering/tests/navigation.test.js
```

## Whisper model loading failure after download

The local Large v3 Turbo download failed with `invalid model data (bad magic)`.
Its size was 2,541,948,500 bytes instead of 1,624,555,275, and its first four
bytes were not the expected GGML magic. This failure happened before model
allocation or inference; the generic context-creation error hid the invalid file.

`downloadModel()` set the UI state to `downloading`, then called `refreshStatus()`.
That refresh could reset the UI state to `not-downloaded` while network activity
continued, allowing another click to start another writer against the same file.
The old validation accepted any file larger than 90% of its expected size,
including this oversized corrupt file. These are demonstrated flaws; the exact
sequence that produced the original corrupt download was not recorded.

The downloader now holds a separate lock, prevents status refreshes from changing
the UI during a download, writes each attempt to a unique temporary file, checks
both the response byte count and the on-disk size, and renames only complete files
into place. Approximate model-size validation now has an upper bound as well.
The filesystem capability grants rename within its existing scope.

The damaged local model was preserved as `ggml-large-v3-turbo.bin.corrupt-backup`.
A replacement from the official model repository was installed after verifying
its length, header and SHA-256:
`1fc70f774d38eb169993ac391eea357ef47c88757ef72ee5943879b7e8e2bc69`.

```bash
bun test apps/whispering/tests/model-download.test.js
```

## Illegal instruction before main

The installed 7.11.0 Debian binary on the local Ubuntu Wayland machine also
terminates with SIGILL before `main()`. GDB identifies `vmovdqu8 %zmm0,...`, an
AVX-512 instruction, inside a static initializer. The exposed CPU has AVX2 but
no AVX-512. Renderer environment variables cannot fix an unsupported instruction.

The locked `whisper-rs-sys` 0.11.1 builds whisper.cpp 1.7.1 with `GGML_NATIVE=ON`,
which adds `-march=native` to GGML's C and C++ sources, including the Vulkan
backend. A release can therefore inherit CPU requirements from its build host.

`.cargo/config.toml` passes a CMake project hook to that dependency. The hook
disables native CPU targeting on Linux and selects the x86-64 baseline on Linux
x86-64. Setting `GGML_NATIVE=OFF` alone is insufficient because this GGML version
then enables AVX, AVX2, FMA and F16C by default. The GPU backend choices remain
unchanged. CPU-only transcription may be slower than a build tuned for the local
processor.

The dependency only forwards environment variables beginning with `WHISPER_`
or `CMAKE_`. Plain `GGML_NATIVE=OFF` in CI would be silently ignored. The hook
uses the supported `CMAKE_PROJECT_INCLUDE` mechanism and is scoped to the
whisper.cpp/GGML projects. Cargo resolves its absolute path from the repository
root, even when Tauri builds from the app directory. The hook also overrides
stale CMake cache options.

## Verification and rebuild

From the repository root, with Rust, Python 3 and CMake installed:

```bash
python3 apps/whispering/tests/linux-startup.test.py
```

The tests compile the real entrypoint against a runtime probe, check renderer
selection before the runtime starts, verify platform/project isolation of the
CMake hook, and check Cargo path resolution from both launch directories. They
run in `.github/workflows/linux-startup.yml`.

With the standard Tauri Linux development dependencies installed:

```bash
bun install
bun run --cwd apps/whispering tauri build
```

The Tauri CLI enables `tauri/custom-protocol` for production builds. A direct
`cargo build --release` does not: it still uses `devUrl` and displays a localhost
connection error when no development server is running. To build the executable
directly after building the frontend, use:

```bash
cargo build --release --locked --features tauri/custom-protocol --manifest-path apps/whispering/src-tauri/Cargo.toml
```

On a machine with limited memory, build with one task at a time:

```bash
CARGO_BUILD_JOBS=1 CMAKE_BUILD_PARALLEL_LEVEL=1 bun run --cwd apps/whispering tauri build
```

For a checkout that previously compiled GGML, remove its old dependency artifacts
before rebuilding:

```bash
cargo clean --manifest-path apps/whispering/src-tauri/Cargo.toml -p whisper-rs-sys
```

The source fix takes effect in a rebuilt executable. Editing source files does
not change an already installed `/usr/bin/whispering`.

## Optional local CPU optimization

On a CPU verified to support AVX, AVX2, FMA and F16C, set
`WHISPER_CPU_AVX2=ON` while rebuilding. Native targeting, AVX-512 and AMX remain
disabled. This opt-in executable must not be distributed to older CPUs.

For a VM exposing only the software Vulkan device llvmpipe, also set
`WHISPER_CPU_ONLY=ON` to disable Vulkan and use GGML's CPU backend directly.
Whispering 7.11 has no UI switch for this. A future real GPU requires a rebuild
without this option. Clean the whisper-rs-sys artifacts when changing options:

```bash
cargo clean --manifest-path apps/whispering/src-tauri/Cargo.toml -p whisper-rs-sys
WHISPER_CPU_AVX2=ON WHISPER_CPU_ONLY=ON CARGO_BUILD_JOBS=1 CMAKE_BUILD_PARALLEL_LEVEL=1 cargo build --release --locked --features tauri/custom-protocol --manifest-path apps/whispering/src-tauri/Cargo.toml
```
