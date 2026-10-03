// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    // WebKitGTK's DMA-BUF path can terminate the process with Wayland Error 71.
    // Configure it before run(): #[tokio::main] starts worker threads there.
    // https://github.com/EpicenterHQ/epicenter/issues/1316
    #[cfg(target_os = "linux")]
    if (std::env::var_os("WAYLAND_DISPLAY").is_some_and(|display| !display.is_empty())
        || std::env::var_os("XDG_SESSION_TYPE").is_some_and(|session| session == "wayland"))
        && std::env::var_os("WEBKIT_DISABLE_DMABUF_RENDERER").is_none()
    {
        std::env::set_var("WEBKIT_DISABLE_DMABUF_RENDERER", "1");
    }

    whispering_lib::run()
}
