import unittest

from xv6_bridge import Xv6Bridge
from xv6_tools import Xv6ToolError, Xv6Tools


class FakeBridge:
    def __init__(self):
        self.commands = []

    def run_command(self, command):
        self.commands.append(command)
        if command == "ls":
            return "README\ncat\nls"
        if command == "cat README":
            return "xv6 exercise files"
        if command == "cat inbox.txt":
            return "The project review is on Friday."
        if command == "cat pipe_dep_test":
            return "\x7fELF\x01\x01\x01compiled executable bytes"
        return "sample file"


class Xv6ToolsTests(unittest.TestCase):
    def setUp(self):
        self.bridge = FakeBridge()
        self.tools = Xv6Tools(self.bridge)

    def test_list_files_uses_ls(self):
        self.assertEqual(self.tools.list_files(), "README\ncat\nls")
        self.assertEqual(self.bridge.commands, ["ls"])

    def test_read_file_uses_cat(self):
        self.assertEqual(self.tools.read_file("README"), "xv6 exercise files")
        self.assertEqual(self.bridge.commands, ["cat README"])

    def test_read_text_files_preserves_contents(self):
        self.assertEqual(
            self.tools.read_file("inbox.txt"),
            "The project review is on Friday.",
        )
        self.assertEqual(self.bridge.commands, ["cat inbox.txt"])

    def test_elf_executable_is_identified_without_displaying_binary(self):
        self.assertEqual(
            self.tools.read_file("pipe_dep_test"),
            (
                "This is a compiled ELF executable, not a text file. I can "
                "identify it, but cannot display its contents as readable "
                "source code."
            ),
        )
        self.assertEqual(self.bridge.commands, ["cat pipe_dep_test"])

    def test_rejects_invalid_paths_without_running_commands(self):
        invalid_paths = (
            "",
            "../README",
            "/README",
            "folder/README",
            r"folder\README",
            ".",
            "..",
            "README;ls",
            "README name",
        )
        for path in invalid_paths:
            with self.subTest(path=path):
                with self.assertRaises(Xv6ToolError):
                    self.tools.read_file(path)
        self.assertEqual(self.bridge.commands, [])

    def test_bridge_rejects_unsupported_commands(self):
        bridge = Xv6Bridge()
        for command in ("echo hello", "cat ../README", "cat README; ls", ""):
            with self.subTest(command=command):
                with self.assertRaises(ValueError):
                    bridge.run_command(command)


def main():
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Xv6ToolsTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        return 1

    print("\nLive xv6 bridge check:")
    with Xv6Bridge() as bridge:
        tools = Xv6Tools(bridge)
        files = tools.list_files()
        readme = tools.read_file("README")
        if "README" not in files or "xv6" not in readme:
            raise RuntimeError("Live xv6 tools returned unexpected output")
        print(f"list_files() found README: {'README' in files}")
        print(f"read_file('README') returned {len(readme)} characters")
    print("All tool tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
