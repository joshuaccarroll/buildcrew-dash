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
    BuildCrewDashApp().run()


if __name__ == "__main__":
    main()
