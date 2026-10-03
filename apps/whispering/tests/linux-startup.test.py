"""Regression tests without desktop libraries: python3 apps/whispering/tests/linux-startup.test.py."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
MAIN = ROOT / "apps/whispering/src-tauri/src/main.rs"
HOOK = ROOT / ".cargo/portable-whisper.cmake"
FEATURES = "NATIVE AVX AVX2 AVX512 AVX512_VBMI AVX512_VNNI AVX512_BF16 FMA F16C AMX_TILE AMX_INT8 AMX_BF16".split()


class LinuxStartup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.directory = Path(cls.temp.name)
        # The real entrypoint calls this probe instead of starting GTK/Tokio.
        stub = cls.directory / "lib.rs"
        stub.write_text('pub fn run() { println!("{}", std::env::var("WEBKIT_DISABLE_DMABUF_RENDERER").unwrap_or("unset".into())); }')
        library = cls.directory / "libwhispering_lib.rlib"
        subprocess.run(["rustc", "--edition=2021", "--crate-name=whispering_lib", "--crate-type=rlib", str(stub), "-o", str(library)], check=True)
        cls.binary = cls.directory / "startup"
        subprocess.run(["rustc", "--edition=2021", str(MAIN), "--extern", f"whispering_lib={library}", "-o", str(cls.binary)], check=True)

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

    def test_cmake_disables_host_cpu_features_only_for_linux_ggml(self):
        for system, project, portable in [("Linux", "whisper.cpp", True), ("Linux", "ggml", True), ("Linux", "other", False), ("Darwin", "whisper.cpp", False), ("Windows", "whisper.cpp", False)]:
            with self.subTest(system=system, project=project):
                script = self.directory / "check.cmake"
                script.write_text(
                    f'set(CMAKE_SYSTEM_NAME "{system}")\nset(CMAKE_SYSTEM_PROCESSOR x86_64)\nset(CMAKE_PROJECT_NAME "{project}")\n'
                    + "\n".join(f'set(GGML_{feature} ON CACHE BOOL "" FORCE)' for feature in FEATURES)
                    + f'\ninclude("{HOOK}")\n'
                    + "\n".join(f'if({"" if portable else "NOT "}GGML_{feature})\nmessage(FATAL_ERROR "Incorrect {feature}")\nendif()' for feature in FEATURES)
                )
                subprocess.run(["cmake", "-P", str(script)], check=True, capture_output=True)

    def test_cargo_resolves_hook_from_repository_and_app(self):
        project = self.directory / "probe"
        (project / "src").mkdir(parents=True)
        (project / "Cargo.toml").write_text('[package]\nname="startup-probe"\nversion="0.0.0"\nedition="2021"\n')
        (project / "src/main.rs").write_text('fn main() { println!("{}", env!("CMAKE_PROJECT_INCLUDE")); }')
        env = os.environ.copy()
        env["CMAKE_PROJECT_INCLUDE"] = "/invalid/host-hook.cmake"
        for cwd in (ROOT, MAIN.parent.parent):
            with self.subTest(cwd=cwd):
                result = subprocess.run(["cargo", "run", "--quiet", "--offline", "--manifest-path", str(project / "Cargo.toml")], cwd=cwd, env=env, check=True, capture_output=True, text=True)
                self.assertEqual(Path(result.stdout.strip()), HOOK)

    def test_local_avx2_opt_in_keeps_avx512_and_native_disabled(self):
        script = self.directory / "avx2.cmake"
        enabled = {"AVX", "AVX2", "FMA", "F16C"}
        script.write_text(
            'set(CMAKE_SYSTEM_NAME Linux)\nset(CMAKE_SYSTEM_PROCESSOR x86_64)\n'
            'set(CMAKE_PROJECT_NAME whisper.cpp)\nset(WHISPER_CPU_AVX2 ON)\n'
            'set(WHISPER_CPU_ONLY ON)\nset(GGML_VULKAN ON CACHE BOOL "" FORCE)\n'
            + "\n".join(f'set(GGML_{feature} ON CACHE BOOL "" FORCE)' for feature in FEATURES)
            + f'\ninclude("{HOOK}")\n'
            + 'if(GGML_VULKAN)\nmessage(FATAL_ERROR "Vulkan still enabled")\nendif()\n'
            + "\n".join(f'if({"NOT " if feature in enabled else ""}GGML_{feature})\nmessage(FATAL_ERROR "Incorrect {feature}")\nendif()' for feature in FEATURES)
        )
        subprocess.run(["cmake", "-P", str(script)], check=True, capture_output=True)


if __name__ == "__main__":
    if not shutil.which("rustc") or not shutil.which("cmake"):
        raise SystemExit("These tests require rustc, cargo and cmake on PATH.")
    unittest.main(verbosity=2)
