
from __future__ import annotations
import socket
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import Enum, auto
import colorama as color
import src.ioHelper.shell_operations as sop
import src.wsl_handler.wsl_utils as wsl
from functools import partial
import src.Utils.Logger as Logger
log: Logger.LoggerClass = Logger.LoggerClass("menu_logger",0)

# ---------------------------------------------------------------------------
# 1. Theme
# ---------------------------------------------------------------------------

GREEN = color.Fore.LIGHTGREEN_EX
DIM_GREEN = color.Style.DIM + color.Fore.GREEN
YELLOW = color.Fore.LIGHTYELLOW_EX
RED = color.Fore.LIGHTRED_EX
CYAN = color.Fore.LIGHTCYAN_EX
RESET = color.Style.RESET_ALL

SUBMENU_MARKER = f"{CYAN}/"
BELL = "\a"

APP_TITLE = "======= WSL Controller Menu ======="


# ---------------------------------------------------------------------------
# 2. Terminal primitives
# ---------------------------------------------------------------------------


def clear() -> None:
    """Clear the screen and home the cursor."""
    print("\033[2J\033[H", end="")


def write(text: str, *, style: str = GREEN) -> None:
    """Print one styled line."""
    print(f"{style}{text}{RESET}")


def pause(message: str = "Press 'Enter' to continue...") -> None:
    """Block until the user acknowledges."""
    write(f"\n{BELL}{message}")
    _read_line()


def prompt(label: str) -> str:
    """Read one trimmed line of input, shown with *label*."""
    print(f"{GREEN}{label}{RESET}", end="", flush=True)
    return _read_line()


def _read_line() -> str:
    """Read stdin, treating EOF as an empty line rather than a crash."""
    try:
        return input().strip()
    except EOFError:
        print()
        return ""


def local_ip() -> str:
    """primary IPv4 address of this host."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("192.0.2.1", 1))  # TEST-NET-1; no packets are sent
            return sock.getsockname()[0]
    except OSError:
        return "unavailable"


def header() -> None:
    """Draw the persistent banner at the top of every screen."""
    clear()
    write(f"         {APP_TITLE}")
    write(f"             IP address: {local_ip()}\n", style=DIM_GREEN)


# ---------------------------------------------------------------------------
# 3. Framework
# ---------------------------------------------------------------------------


class Signal(Enum):
    """What a menu action tells its parent loop to do next."""
    STAY = auto()
    BACK = auto()
    EXIT = auto()

#: An action either returns a Signal or ``None``, which is read as ``STAY``.
Action = Callable[[], Signal | None]


@dataclass(frozen=True, slots=True)
class MenuItem:
    """One selectable line."""
    key: str
    label: str
    action: Action
    style: str = GREEN
    is_submenu: bool = False
    pause_after: bool = True

    def render(self) -> str:
        suffix = SUBMENU_MARKER if self.is_submenu else ""
        return f"{self.style}{self.key:>3}) {self.label}{suffix}{RESET}"



#: Menu contents: either a fixed list, or a function that builds one on demand.
ItemSource = Sequence[MenuItem] | Callable[[], Sequence[MenuItem]]


@dataclass(slots=True)
class Menu:
    """A screen: a title, a set of items, and its own input loop.

    Pass a callable as *items* for menus whose contents change at runtime —
    it is re-evaluated before every redraw, so the list is never stale.
    """

    title: str
    prompt_label: str
    items: ItemSource
    _current: list[MenuItem] = field(init=False, repr=False, default_factory=list)
    _by_key: dict[str, MenuItem] = field(init=False, repr=False, default_factory=dict)

    def refresh(self) -> None:
        """Rebuild the item list and the key lookup."""
        items = list(self.items() if callable(self.items) else self.items)

        seen: set[str] = set()
        duplicates = {i.key for i in items if i.key in seen or seen.add(i.key)}
        if duplicates:
            raise ValueError(f"duplicate keys in menu {self.title!r}: {sorted(duplicates)}")

        self._current = items
        self._by_key = {item.key: item for item in items}

    def draw(self) -> None:
        header()
        write(f"{self.title}\n")
        for item in self._current:
            print(item.render())
        print()

    def run(self) -> Signal:
        """Loop until an action asks to go back or exit."""
        while True:
            self.refresh()          # ← contents re-evaluated every pass
            self.draw()
            choice = prompt(self.prompt_label)
            item = self._by_key.get(choice)

            if item is None:
                write("Invalid selection. Please try again.", style=RED)
                pause()
                continue

            signal = self._invoke(item)
            if signal is Signal.EXIT:
                return Signal.EXIT
            if signal is Signal.BACK:
                return Signal.BACK

    def _invoke(self, item: MenuItem) -> Signal:
        """Run one item, keeping a failure inside it from killing the menu."""
        clear()
        try:
            signal = item.action() or Signal.STAY
        except KeyboardInterrupt:
            write("\nCancelled.", style = YELLOW)
            signal = Signal.STAY
        except Exception as exc:
            write(f"{item.label} raised {type(exc).__name__}: {exc}", style = RED)
            signal = Signal.STAY

        if item.pause_after and signal is Signal.STAY:
            pause()
        return signal


# ---------------------------------------------------------------------------
# 4. Actions
# ---------------------------------------------------------------------------

def back() -> Signal:
    """Close the current menu."""
    return Signal.BACK


def quit_app() -> Signal:
    """Close every menu and end the program."""
    write("Exiting Have a nice day :D")
    return Signal.EXIT


def open_menu(menu: Menu) -> Action:
    """Wrap *menu* so selecting the item enters it.

    ``EXIT`` propagates outward; ``BACK`` stops here and returns to this level.
    """

    def action() -> Signal:
        return Signal.STAY if menu.run() is Signal.BACK else Signal.EXIT

    return action


def run(description: str, command: str) -> Action:
    """Build an action that runs *command* in the native shell."""

    def action() -> None:
        write(f"{description}...\n")
        result: sop.CommandResult = sop.run_cmd(command)
        print(result.stdout, end="")
        if not result:
            write(f"\nFailed (exit {result.returncode}): {result.stderr.strip()}", style=RED)

    return action


def run_with_variants(description: str, variants: dict[str, tuple[str, str]]) -> Action:
    """Ask which variant to run, then run it.

    *variants* maps an input key to ``(label, command)``. Any other key aborts,
    which covers the "0) Return" arms of the original menus.
    """

    def action() -> None:
        write(f"{description}:\n")
        for key, (label, _) in variants.items():
            write(f"  {key}) {label}")
        write("  0) Cancel\n")

        chosen = variants.get(prompt("Select option: "))
        if chosen is None:
            return
        label, command = chosen
        run(f"{description} — {label}", command)()

    return action


def ask(description: str, template: str, field_label: str) -> Action:
    """Prompt for one value, substitute it into *template*, then run.

    *template* must contain a single ``{}`` placeholder; the answer is shell
    quoted before substitution.
    """

    def action() -> None:
        from shlex import quote

        answer = prompt(f"{field_label}: ")
        if not answer:
            write("Nothing entered.", style=YELLOW)
            return
        run(f"{description} '{answer}'", template.format(quote(answer)))()

    return action

def ask_value(
    question: str,
    *,
    default: str | None = None,
    required: bool = True,
) -> str | None:
    """Ask *question* and return the answer.

    Args:
        question: Shown to the user; a ``": "`` suffix is added if absent.
        default: Returned when the user submits an empty line. Displayed in
            the prompt when set.
        required: When true and there is no default, keep asking until the
            user types something or cancels with Ctrl-C.

    Returns:
        The trimmed answer, the default, or ``None`` if the user cancelled or
        declined to answer an optional question.
    """
    label = question if question.rstrip().endswith((":", "?", ">")) else f"{question}:"
    if default is not None:
        label = f"{label} [{default}] >"

    while True:
        try:
            answer = prompt(f"{label} ")
        except KeyboardInterrupt:
            write("\nCancelled.", style=YELLOW)
            return None

        if answer:
            return answer
        if default is not None:
            return default
        if not required:
            return None
        write("A value is required.", style=YELLOW)


def ask_then(
    question: str,
    func: Callable[[str], object],
    *,
    default: str | None = None,
) -> Action:
    """Build an action that asks *question* and passes the answer to *func*."""

    def action() -> None:
        answer = ask_value(question, default=default)
        if answer is None:
            return
        func(answer)

    return action

def run_in_selected_instance(
    description: str,
    command: str,
    *,
    interactive: bool = False,
    user: str | None = None,
    cwd: str | None = None,
) -> Action:
    """Build an action that asks which instance to use, then runs *command*.

    Args:
        description: Shown while selecting and while running.
        command: Linux command line to execute.
        interactive: Hand the terminal to the command instead of capturing it.
            Required for editors, pagers, and anything that prompts.
        user: Linux user to run as.
        cwd: Linux working directory.
    """

    def action() -> None:
        name = pick_instance(f"{description} — select an instance:")
        if name is None:
            return

        if interactive:
            wsl.open_in_instance(name, command, user=user, cwd=cwd)
            return

        write(f"{description} on {name}...\n")
        result = wsl.run_in_instance(name, command, user=user, cwd=cwd)
        print(result.stdout, end="")
        if not result:
            write(f"\nFailed (exit {result.returncode}): {result.stderr.strip()}", style=RED)

    return action

def run_arbitrary_in_instance() -> None:
    """Ask for an instance and a command, then run it there interactively."""
    name = pick_instance("Run a command — select an instance:")
    if name is None:
        return

    command = ask_value("Command to run", required=True)
    if command is None:
        return

    wsl.open_in_instance(name, command)
# ---------------------------------------------------------------------------
# 4.5 Menu functions
# ---------------------------------------------------------------------------

def pick_instance(
    title: str = "Select an instance:",
    *,
    mode: str = "all",
    running_only: bool = False,
) -> str | None:
    """Show a numbered list of instances and return the chosen name.

    Args:
        title: Heading for the selection screen.
        mode: Passed to ``list_wsl`` — ``all`` or ``running``.
        running_only: Filter out stopped instances. Use for actions that
            would otherwise boot a distro as a side effect.

    Returns:
        The selected instance name, or ``None`` if the user chose Back or
        there was nothing to choose from.
    """
    distros = wsl.list_wsl(mode)
    if running_only:
        distros = [d for d in distros if d["status"] == "Running"]

    if not distros:
        write("No matching instances.", style=YELLOW)
        pause()
        return None

    header()
    write(f"{title}\n")
    for index, distro in enumerate(distros, start=1):
        marker = f" {DIM_GREEN}({distro['status']}){GREEN}" if distro["status"] else ""
        write(f"{index:>3}) {distro['name']}{marker}")
    write("  0) Back\n")

    while True:
        choice = prompt("Instance> ")
        if choice == "0":
            return None
        if choice.isdigit() and 1 <= int(choice) <= len(distros):
            return distros[int(choice) - 1]["name"]
        write("Invalid selection. Please try again.", style=RED)

# Functionality for some simpler options
def build_removable_distro_menu() -> list[MenuItem]:
    distro_list = wsl.list_wsl("online")
    menu_items=[]
    index=1
    for distro in distro_list:
        menu_items.append(MenuItem(str(index), distro['name'], partial(wsl.remove_instance(),distro_name=distro['name']), pause_after=True))
        index=index+1
    menu_items.append(MenuItem("0", "Back", back, pause_after=False))
    return menu_items

def build_available_distros_menu() -> list[MenuItem]:
    """Build one item per installed instance, plus a Back entry."""
    distros = wsl.list_wsl("online")
    items = [
        MenuItem(str(index), distro["name"], partial(install_new_distro, distro_name=distro["name"]))
        for index, distro in enumerate(distros, start=1)
    ]
    if not items:
        items.append(MenuItem("", "No distors available - check your connection", lambda: None, pause_after=False))
    items.append(MenuItem("0", "Back", back, pause_after=False))
    return items


def build_start_instance_menu() -> list[MenuItem]:
    """Build one item per installed instance, plus a Back entry."""
    distros = wsl.list_wsl("all")
    items = [
        MenuItem(str(index), distro["name"], partial(start_instance, instance_name=distro["name"]))
        for index, distro in enumerate(distros, start=1)
    ]
    if not items:
        items.append(MenuItem("", "No instances installed", lambda: None, pause_after=False))
    items.append(MenuItem("0", "Back", back, pause_after=False))
    return items

def build_stop_instance_menu() -> list[MenuItem]:
    """Build one item per installed instance, plus a Back entry."""
    distros = wsl.list_wsl("all")
    distro_running=[]
    for distro in distros:
        if not distro['status'] != 'Running':
            distro_running.append(distro['name'])
    items = [
        MenuItem(f"{index}", distro, partial(stop_instance, instance_name=distro))
        for index, distro in enumerate(distro_running, start=1)
    ]
    if not items:
        items.append(MenuItem("-", "No instances running", lambda: None, pause_after=False))
    items.append(MenuItem("0", "Back", back, pause_after=False))
    return items

def build_installed_distro_menu() -> list[MenuItem]:
    """Build one item per installed instance, plus a Back entry."""
    distros = wsl.list_wsl("all")
    items = [
        MenuItem(str(index), distro["name"], partial(remove_distro, instance_name=distro["name"]))
        for index, distro in enumerate(distros, start=1)
    ]
    if not items:
        items.append(MenuItem("-", "No instances installed", lambda: None, pause_after=False))
    items.append(MenuItem("0", "Back", back, pause_after=False))
    return items

def start_instance(instance_name):
    wsl.start_instance(instance_name)

def stop_instance(instance_name):
    wsl.stop_instance(instance_name)

def install_new_distro(distro_name):
    log.info("Running install_new_distro option")
    instance_name = ask_value(question = f"""Please provide a name or leave empty to use the default:\n"""
                    ,default = distro_name, required = False)
    log.info(instance_name)
    wsl.install_instance(distro_name,instance_name)

def remove_distro(instance_name):
    answer = ask_value(question = f"""Are you sure you want to remove {instance_name}:\n"""
                    ,default = "y/N", required = False)
    if answer in ["y","Y"]:
        log.info(f"User confirmed removal of {instance_name} by typing {answer}")
        wsl.remove_instance(instance_name)
    else:
        log.error(f"User cancelled the removal of {instance_name}")
# ---------------------------------------------------------------------------
# 5. Menu tree
# ---------------------------------------------------------------------------

START_DISTRO_MENU = Menu(
    title="Start an instance:",
    prompt_label="start-distro> ",
    items=build_start_instance_menu,
)

STOP_DISTRO_MENU = Menu(
    title="Running Instances:",
    prompt_label="stop-distro> ",
    items=build_stop_instance_menu,
)

INSTALL_DISTRO_MENU = Menu(
    title="Install a distribution:",
    prompt_label="install-distro> ",
    items=build_available_distros_menu,
)

REMOVE_DISTRO_MENU = Menu(
    title="Remove an instance:",
    prompt_label="remove-distro> ",
    items=build_installed_distro_menu,
)

UTIL_MENU = Menu(
    title = "Utils:",
    prompt_label = "Util> ",
    items = [
        MenuItem(key="1",label="Check WSL installed",action=wsl.check_wsl_installed),
        MenuItem(key="2",label="Install a distribution",action=open_menu(INSTALL_DISTRO_MENU),pause_after = False,is_submenu = True),
        MenuItem("0", "Back", back, pause_after = False),

    ]

)

MAIN_MENU = Menu(
    title=f"Welcome {Logger.emphasize_string(sop.run_cmd("whoami").stdout.split("\\")[1])}\nPlease make a choice from the list below:",
    prompt_label="CMD> ",
    items=[
        MenuItem("1","Start an instance",open_menu(START_DISTRO_MENU),is_submenu = True,pause_after = False),
        MenuItem("2","Stop an instance",open_menu(STOP_DISTRO_MENU),is_submenu = True,pause_after = False),
        MenuItem("3", "Boot lsh", run_in_selected_instance("Boot lsh", "lsh setup;lsh boot; lsh wds"),is_submenu = True),
        MenuItem("5", "Run a command...", run_arbitrary_in_instance, pause_after = False,is_submenu = True),
        MenuItem("10","Utils",open_menu(UTIL_MENU),is_submenu = True,pause_after = False),
        MenuItem("11", "Install new instance", open_menu(INSTALL_DISTRO_MENU), is_submenu=True, pause_after=False),
        MenuItem("12","Remove Instance",open_menu(REMOVE_DISTRO_MENU),is_submenu = True,pause_after=False),
        MenuItem("0", "Exit", quit_app, pause_after=False),
    ],
)


# ---------------------------------------------------------------------------
# 6. Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    color.just_fix_windows_console()
    try:
        MAIN_MENU.run()
    except KeyboardInterrupt:
        write("\nInterrupted.", style=YELLOW)
        return 130
    finally:
        print(RESET, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())