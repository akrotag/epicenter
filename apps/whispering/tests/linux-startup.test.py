"""Regression tests without desktop libraries: python3 apps/whispering/tests/linux-startup.test.py."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
MAIN = ROOT / "apps/epicenter/src-tauri/src/main.rs"


class LinuxStartup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.directory = Path(cls.temp.name)
        # The real entrypoint calls this probe instead of starting GTK/Tokio.
        stub = cls.directory / "lib.rs"
        stub.write_text('pub fn run() { println!("{}", std::env::var("WEBKIT_DISABLE_DMABUF_RENDERER").unwrap_or("unset".into())); }')
        library = cls.directory / "libepicenter_lib.rlib"
        subprocess.run(["rustc", "--edition=2021", "--crate-name=epicenter_lib", "--crate-type=rlib", str(stub), "-o", str(library)], check=True)
        cls.binary = cls.directory / "startup"
        subprocess.run(["rustc", "--edition=2021", str(MAIN), "--extern", f"epicenter_lib={library}", "-o", str(cls.binary)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_renderer_is_selected_before_runtime_start(self):
        cases = [
            ({}, "unset"),
            ({"XDG_SESSION_TYPE": "x11"}, "unset"),
            ({"WAYLAND_DISPLAY": "wayland-0"}, "1"),
            ({"XDG_SESSION_TYPE": "wayland"}, "1"),
            ({"WAYLAND_DISPLAY": ""}, "unset"),
            ({"WAYLAND_DISPLAY": "", "XDG_SESSION_TYPE": "wayland"}, "1"),
            ({"WAYLAND_DISPLAY": "wayland-0", "WEBKIT_DISABLE_DMABUF_RENDERER": "0"}, "0"),
            ({"WAYLAND_DISPLAY": "wayland-0", "WEBKIT_DISABLE_DMABUF_RENDERER": "1"}, "1"),
            ({"WAYLAND_DISPLAY": "wayland-0", "WEBKIT_DISABLE_DMABUF_RENDERER": ""}, ""),
        ]
        for values, expected in cases:
            with self.subTest(environment=values):
                env = os.environ.copy()
                for key in ("WAYLAND_DISPLAY", "XDG_SESSION_TYPE", "WEBKIT_DISABLE_DMABUF_RENDERER"):
                    env.pop(key, None)
                env.update(values)
                result = subprocess.run([str(self.binary)], env=env, check=True, capture_output=True, text=True)
                self.assertEqual(result.stdout.strip(), expected)


if __name__ == "__main__":
    if not shutil.which("rustc"):
        raise SystemExit("These tests require rustc on PATH.")
    unittest.main(verbosity=2)
