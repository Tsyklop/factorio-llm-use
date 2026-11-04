import configparser
import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.start_server import MOD_FILE, game_data, parser, prepare


def unused_port(kind):
    with socket.socket(socket.AF_INET, kind) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def fingerprint(directory):
    return {
        str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in directory.rglob("*")
        if path.is_file()
    }


class SessionPreparationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="factorio setup ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.project = self.root / "project"
        (self.project / "dist").mkdir(parents=True)
        with zipfile.ZipFile(self.project / "dist" / MOD_FILE, "w") as archive:
            archive.writestr("factorio_llm_use_0.1.1/info.json", "{}")
        self.executable = self.root / "install/bin/x64/factorio"
        self.executable.parent.mkdir(parents=True)
        self.executable.write_text("fixture executable", encoding="utf-8")
        self.read_data = self.root / "install/data"
        (self.read_data / "base").mkdir(parents=True)
        (self.read_data / "base/info.json").write_text("{}", encoding="utf-8")
        self.source = self.root / "user data"
        self.mods = self.source / "mods"
        (self.mods / "unpacked_mod").mkdir(parents=True)
        (self.mods / "unpacked_mod/control.lua").write_text("-- fixture", encoding="utf-8")
        (self.mods / "mod-settings.dat").write_bytes(b"fixture settings")
        (self.mods / "mod-list.json").write_text(
            json.dumps(
                {
                    "mods": [
                        {"name": "base", "enabled": True},
                        {"name": "factorio_llm_use", "enabled": False},
                    ]
                }
            ),
            encoding="utf-8",
        )
        self.save = self.source / "saves/world.zip"
        self.save.parent.mkdir()
        with zipfile.ZipFile(self.save, "w") as archive:
            archive.writestr("world/fixture", "original world")
        self.runtime = self.project / ".runtime"
        self.arguments = [
            "--factorio",
            str(self.executable),
            "--mods",
            str(self.mods),
            "--save",
            str(self.save),
            "--game-port",
            str(unused_port(socket.SOCK_DGRAM)),
            "--rcon-port",
            str(unused_port(socket.SOCK_STREAM)),
        ]

    def args(self):
        return parser(self.project).parse_args(self.arguments)

    def test_new_session_preserves_sources_and_writes_a_usable_snapshot(self):
        before = fingerprint(self.source)
        command = prepare(self.args(), self.project)
        self.assertEqual(fingerprint(self.source), before)
        self.assertEqual((self.runtime / "session.zip").read_bytes(), self.save.read_bytes())
        self.assertEqual((self.runtime / "mods/unpacked_mod/control.lua").read_text(), "-- fixture")
        self.assertEqual((self.runtime / "mods/mod-settings.dat").read_bytes(), b"fixture settings")
        mod_list = json.loads((self.runtime / "mods/mod-list.json").read_text())
        self.assertEqual(mod_list["mods"][-1], {"name": "factorio_llm_use", "enabled": True})
        config = configparser.ConfigParser()
        config.read(self.runtime / "config.ini")
        self.assertEqual(config["path"]["read-data"], self.read_data.as_posix())
        self.assertEqual(config["path"]["write-data"], (self.runtime / "data").as_posix())
        self.assertTrue((self.runtime / "data/saves").is_dir())
        self.assertEqual(
            command[command.index("--start-server") + 1], str(self.runtime / "session.zip")
        )
        self.assertEqual(command[command.index("--bind") + 1], "127.0.0.1")
        settings = json.loads((self.runtime / "server-settings.json").read_text())
        self.assertFalse(settings["auto_pause"])
        self.assertEqual(settings["autosave_interval"], 5)
        if os.name != "nt":
            self.assertEqual((self.runtime / "rcon-password.txt").stat().st_mode & 0o777, 0o600)

    def test_new_import_refuses_to_modify_an_existing_session(self):
        prepare(self.args(), self.project)
        before = fingerprint(self.runtime)
        self.save.write_bytes(b"another source world")
        with self.assertRaisesRegex(ValueError, "already exists"):
            prepare(self.args(), self.project)
        self.assertEqual(fingerprint(self.runtime), before)

    def test_resume_uses_latest_native_save_and_preserves_mod_snapshot_and_credentials(self):
        prepare(self.args(), self.project)
        credentials = (self.runtime / "rcon-password.txt").read_bytes()
        older = self.runtime / "data/saves/session-old.zip"
        latest = self.runtime / "data/saves/session-latest.zip"
        older.write_bytes(b"old persisted fixture")
        latest.write_bytes(b"latest persisted fixture")
        os.utime(older, (100, 100))
        os.utime(latest, (200, 200))
        self.arguments.remove("--save")
        self.arguments.remove(str(self.save))
        self.arguments.append("--resume")
        self.mods.joinpath("mod-settings.dat").write_bytes(b"changed outside session")
        before = fingerprint(self.runtime / "mods")
        command = prepare(self.args(), self.project)
        self.assertEqual(command[command.index("--start-server") + 1], str(latest))
        self.assertEqual(fingerprint(self.runtime / "mods"), before)
        self.assertEqual((self.runtime / "rcon-password.txt").read_bytes(), credentials)

    def test_resume_without_a_session_fails_without_creating_one(self):
        args = self.args()
        args.resume = True
        args.save = None
        with self.assertRaisesRegex(ValueError, "No complete session"):
            prepare(args, self.project)
        self.assertFalse(self.runtime.exists())

    def test_source_mods_cannot_contain_the_runtime_directory(self):
        args = self.args()
        args.runtime_directory = self.mods / "nested runtime"
        before = fingerprint(self.source)
        with self.assertRaisesRegex(ValueError, "must not overlap"):
            prepare(args, self.project)
        self.assertEqual(fingerprint(self.source), before)

    def test_mac_bundle_data_and_explicit_data_override(self):
        executable = self.root / "factorio.app/Contents/MacOS/factorio"
        data = executable.parent.parent / "data"
        (data / "base").mkdir(parents=True)
        (data / "base/info.json").write_text("{}", encoding="utf-8")
        self.assertEqual(game_data(executable, None), data)
        self.assertEqual(game_data(executable, self.read_data), self.read_data)

    def test_occupied_port_is_rejected_before_files_are_written(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as occupied:
            occupied.bind(("127.0.0.1", 0))
            args = self.args()
            args.game_port = occupied.getsockname()[1]
            with self.assertRaisesRegex(ValueError, "unavailable"):
                prepare(args, self.project)
        self.assertFalse(self.runtime.exists())

    @unittest.skipIf(os.name == "nt", "Foreground exec is a Unix process boundary")
    def test_unix_cli_executes_a_process_that_consumes_the_generated_config(self):
        # This executable checks launch/configuration behavior, not Factorio gameplay.
        self.executable.write_text(
            f"#!{sys.executable}\n"
            "import configparser, json, sys\n"
            "from pathlib import Path\n"
            "config = configparser.ConfigParser()\n"
            "config.read(sys.argv[sys.argv.index('--config') + 1])\n"
            "save = Path(sys.argv[sys.argv.index('--start-server') + 1])\n"
            "output = Path(config['path']['write-data']) / 'boundary.json'\n"
            "output.write_text(json.dumps({'save_bytes': save.stat().st_size, "
            "'mod_list': json.loads((Path(sys.argv[sys.argv.index('--mod-directory') + 1]) "
            "/ 'mod-list.json').read_text())}))\n",
            encoding="utf-8",
        )
        self.executable.chmod(0o700)
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; from pathlib import Path; from scripts.start_server import main; "
                "root = Path(sys.argv.pop(1)); main(root)",
                str(self.project),
                *self.arguments,
            ],
            cwd=Path(__file__).resolve().parents[1],
            text=True,
            capture_output=True,
            timeout=15,
            check=True,
        )
        output = json.loads((self.runtime / "data/boundary.json").read_text())
        self.assertEqual(output["save_bytes"], self.save.stat().st_size)
        self.assertEqual(output["mod_list"]["mods"][-1]["enabled"], True)
        self.assertNotIn((self.runtime / "rcon-password.txt").read_text(), result.stdout)


if __name__ == "__main__":
    unittest.main()
