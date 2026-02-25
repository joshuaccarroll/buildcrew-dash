import shutil
import subprocess
import sys
from pathlib import Path

from textual.app import App

from buildcrew_dash.screens.index import IndexScreen


class BuildCrewDashApp(App):
    CSS = ""
    SCREENS = {"index": IndexScreen}

    def on_mount(self) -> None:
        self.push_screen("index")
        from buildcrew_dash import scanner
        if scanner._PGREP_UNAVAILABLE or scanner._LSOF_UNAVAILABLE:
            self.notify("pgrep/lsof not available — process discovery disabled", severity="error")


def main() -> None:
    if len(sys.argv) == 1:
        BuildCrewDashApp().run()
        return

    arg = sys.argv[1]

    if arg == "update":
        print("Fetching latest buildcrew-dash...")
        result = subprocess.run(
            ["bash", "-c", "curl -fsSL https://raw.githubusercontent.com/joshuaccarroll/buildcrew-dash/main/install.sh | bash -s -- --upgrade"],
            check=False,
        )
        sys.exit(result.returncode)

    elif arg == "uninstall":
        print("Will remove: ~/.buildcrew-dash/")
        print("Will remove: ~/.local/bin/buildcrew-dash")
        try:
            response = input("Continue? [y/N] ")
        except EOFError:
            response = ""
        if response.strip().lower() == "y":
            shutil.rmtree(Path.home() / ".buildcrew-dash", ignore_errors=True)
            (Path.home() / ".local/bin/buildcrew-dash").unlink(missing_ok=True)
            print("buildcrew-dash uninstalled.")
            sys.exit(0)
        else:
            print("Aborted.")
            sys.exit(0)

    else:
        print(f"Unknown command: {arg}")
        print("Usage: buildcrew-dash [update|uninstall]")
        sys.exit(1)


if __name__ == "__main__":
    main()
