"""Managing WSL distributions and instances."""

from __future__ import annotations

import re
import time
import winreg
from collections.abc import Iterator
import shlex
from time import sleep

import src.Utils.Logger as Logger
import src.ioHelper.shell_operations as sop
from src.Utils.Logger import emphasize_err_string, emphasize_string
from src.ioHelper.shell_operations import run_cmd, spawn_terminal

log = Logger.LoggerClass("wsl_utils", 0)

_LXSS_KEY = r"Software\Microsoft\Windows\CurrentVersion\Lxss"
_ILLEGAL = set('\\/:*?"<>|')

#: Characters WSL leaves in its UTF-16 output that must not reach a command line.
_JUNK = "\x00\ufeff\r\n\t "

VALID_LIST_MODES = ("all", "running", "online")


class WslError(RuntimeError):
    """Raised when a WSL operation cannot be completed."""

# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


def check_wsl_installed(quiet: bool = True) -> bool:
    """Return whether the WSL executable is present and responding."""
    result = run_cmd("wsl --version", quiet=quiet)
    if result.ok:
        log.success("WSL is installed")
        return True

    log.error("WSL not installed")
    if result.stderr.strip():
        log.debug(f"stderr: {emphasize_err_string(result.stderr.strip())}")
    return False


def list_wsl(arg: str = "all", quiet: bool = True) -> list[dict]:
    """List WSL distributions.

    Args:
        arg: ``all`` or ``running`` for installed instances, ``online`` for
            distributions available to install.
        quiet: Suppress per-command logging.

    Returns:
        A list of dicts with keys ``name``, ``status``, ``version`` and
        ``default``. Keys are always present; unknown values are ``None``.
        An empty list means no distributions, not a failure.

    Raises:
        ValueError: If *arg* is not one of the supported modes.
        WslError: If the list could not be retrieved.
    """
    if arg not in VALID_LIST_MODES:
        message = f"Argument {arg!r} not known. Valid arguments: {', '.join(VALID_LIST_MODES)}"
        log.error(message)
        raise ValueError(message)

    if arg == "online":
        return _list_online(quiet=quiet)
    return _list_installed(arg, quiet=quiet)


def _list_online(*, quiet: bool) -> list[dict]:
    """Parse ``wsl --list --online``."""
    result = run_cmd("wsl --list --online", quiet=quiet)
    if not result.ok:
        raise WslError(f"Could not list available distributions: {result.stderr}")

    distros: list[dict] = []
    body = result.stdout
    marker = body.find("FRIENDLY NAME")
    if marker != -1:
        body = body[marker + len("FRIENDLY NAME"):]

    for line in body.splitlines():
        line = line
        if not line or line.startswith("-"):
            continue
        name = re.split(r"\s{2,}|\t", line, maxsplit=1)[0]
        if name:
            distros.append({"name": name, "status": None, "version": None, "default": False})

    if not quiet:
        log.debug(f"Found the following distributions:\n {distros}")
    log.value(f"Found {len(distros)} available distros")
    return distros


def _list_installed(mode: str, *, quiet: bool) -> list[dict]:
    """Parse ``wsl --list --{mode} --verbose``."""
    result = run_cmd(f"wsl --list --{mode} --verbose", quiet=quiet)

    combined = result.stdout + result.stderr
    if "no installed distributions" in combined.lower():
        log.info("0 instances found")
        return []

    if not result.ok:
        raise WslError(f"Failed to retrieve list of installed instances: {combined}")

    distros: list[dict] = []
    for line in result.stdout.splitlines()[1:]:  # drop the header row
        raw = line
        if not raw:
            continue

        is_default = raw.startswith("*")
        fields = raw.lstrip("*").split()
        if not fields:
            continue

        distros.append(
            {
                "name": fields[0],
                "status": fields[1] if len(fields) > 1 else None,
                "version": fields[2] if len(fields) > 2 else None,
                "default": is_default,
            }
        )

    if not quiet:
        log.debug(f"Found the following instances:\n {distros}")
    return distros


def list_distros(arg: str = "all") -> list[str]:
    """Return just the names of the distributions matching *arg*."""
    return [distro["name"] for distro in list_wsl(arg)]


def instance_exists(instance_name: str) -> bool:
    """Return whether an instance with exactly this name is registered."""
    return instance_name in list_distros("all")


def instance_state(instance_name: str) -> str | None:
    """Return the state of *instance_name* (``Running`` / ``Stopped``), or None."""
    target = instance_name
    for distro in list_wsl("all"):
        if distro["name"] == target:
            return distro["status"]
    return None


def _require_instance(instance_name: str | None) -> str:
    """Validate *instance_name* and return its cleaned form.

    Raises:
        ValueError: If the name is empty.
        WslError: If no instance with that name is registered. The message
            includes the repr of both sides so a mismatch caused by invisible
            characters is visible rather than baffling.
    """
    if instance_name is None or not instance_name.strip():
        raise ValueError("Instance name must not be empty")

    name = instance_name
    known = list_distros("all")
    if name not in known:
        log.error(f"Instance {emphasize_err_string(name)} not found")
        log.debug(f"Looked for {name!r} among {known!r}")
        raise WslError(f"No instance named {name!r}. Found: {', '.join(known) or 'none'}")
    return name


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def install_instance(distribution_name: str, instance_name: str | None = None) -> None:
    """Install *distribution_name* as a new instance called *instance_name*.

    Runs to completion with output echoed, so a failure surfaces here rather
    than vanishing with a closed window.

    Raises:
        ValueError: If the distribution name is empty or the instance name is
            not a legal WSL name.
        WslError: If the instance already exists or the install fails.
    """
    distribution_name = (distribution_name or "")
    if not distribution_name:
        raise ValueError("Distribution name must not be empty")

    instance_name = (instance_name or "") or distribution_name
    _validate_name(instance_name)

    if instance_exists(instance_name):
        log.error(f"Instance named {emphasize_err_string(instance_name)} already exists")
        raise WslError(f"An instance named {instance_name!r} already exists")

    log.info(
        f"Creating new {emphasize_string(distribution_name)} instance "
        f"named {emphasize_string(instance_name)}"
    )
    print(f"Installing {instance_name} — this can take several minutes...")

    result = spawn_terminal(
        f'wsl --install {distribution_name} --name {instance_name} --no-launch',
        timeout=1800.0,
    )
    log.success(f"Instance {emphasize_string(instance_name)} installed")


def remove_instance(instance_name: str | None = None) -> None:
    """Unregister *instance_name*, deleting its filesystem.

    Raises:
        ValueError: If no name was given.
        WslError: If the instance does not exist or the unregister fails.
    """
    name = _require_instance(instance_name)

    log.info(f"Removing instance {emphasize_string(name)}")
    print(f"Removing {name}...")

    result = run_cmd(f'wsl --unregister {name}', timeout=300.0)
    if not result.ok:
        raise WslError(
            f"Could not remove {name!r} (exit {result.returncode}): "
            f"{result.stderr or 'no error output'}"
        )
    log.success(f"Instance {emphasize_string(name)} removed")


def start_instance(instance_name: str, *, wait: bool = False, timeout: float | None = 120.0) -> None:
    """Start the WSL instance *instance_name*.

    WSL has no start command — a distribution boots when something runs inside
    it. This runs ``true``, which exits immediately and leaves the VM up until
    it idles out or ``wsl --shutdown`` is issued.

    Args:
        instance_name: Instance to start.
        wait: Block until the instance reports ``Running``.
        timeout: Seconds to allow for the boot. ``None`` waits forever.

    Raises:
        ValueError: If the name is empty.
        WslError: If the instance does not exist, fails to boot, or times out.
    """
    name = _require_instance(instance_name)

    log.info(f"Starting instance {emphasize_string(name)}")
    result = spawn_terminal(f'wsl -d {name}', timeout = timeout)
    if wait and not _wait_for_state(name, "Running", timeout=timeout):
        raise WslError(f"{name!r} did not reach Running within {timeout}s")

    log.success(f"Instance {emphasize_string(name)} is running")


def stop_instance(instance_name: str) -> None:
    """Terminate a single running instance, leaving other instances up."""
    name = _require_instance(instance_name)
    log.info(f"Terminating instance {emphasize_string(name)}")
    result = run_cmd(f'wsl --terminate {name}')
    if not result.ok:
        raise WslError(
            f"Could not terminate {name!r} (exit {result.returncode}): "
            f"{result.stderr or 'no error output'}"
        )
    log.success(f"Instance {emphasize_string(name)} terminated")


def open_shell(instance_name: str) -> None:
    """Open an interactive shell in *instance_name* in the current terminal.

    This is the one case that must not capture output: the shell needs the
    terminal to draw and to read keystrokes. Returns when the user exits.
    """
    name = _require_instance(instance_name)

    log.info(f"Opening shell in {emphasize_string(name)}")
    print(f"Entering {name}. Type 'exit' to return.\n")
    sop.run_interactive(f'wsl --distribution "{name}"')


def _wait_for_state(instance_name: str, target: str, *, timeout: float | None) -> bool:
    """Poll until *instance_name* reports *target*, or the timeout expires."""
    deadline = None if timeout is None else time.monotonic() + timeout
    while deadline is None or time.monotonic() < deadline:
        if instance_state(instance_name) == target:
            return True
        time.sleep(0.5)
    return False


# ---------------------------------------------------------------------------
# Renaming (registry)
# ---------------------------------------------------------------------------


def rename_instance(old_name: str, new_name: str, *, shutdown: bool = True) -> None:
    """Rename instance *old_name* to *new_name* via the registry.

    Raises:
        ValueError: If *new_name* is empty or contains illegal characters.
        WslError: If *old_name* does not exist, *new_name* is taken, or the
            registry cannot be written.
    """
    old = _require_instance(old_name)
    new = new_name
    _validate_name(new)

    if instance_exists(new):
        raise WslError(f"An instance named {new!r} already exists")

    if shutdown:
        log.info(f"Shutting down WSL before renaming {emphasize_string(old)}")
        if not run_cmd("wsl --shutdown").ok:
            raise WslError("Could not shut down WSL; refusing to rename a running instance")

    key_path = _find_instance_key(old)
    if key_path is None:
        raise WslError(f"{old!r} is registered with WSL but has no registry entry")

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "DistributionName", 0, winreg.REG_SZ, new)
    except PermissionError as exc:
        raise WslError(
            f"Access denied writing {key_path}. The instance likely belongs to "
            f"a different Windows user."
        ) from exc
    except OSError as exc:
        raise WslError(f"Failed to write registry key {key_path}: {exc}") from exc

    log.success(f"Renamed {emphasize_string(old)} to {emphasize_string(new)}")


def _validate_name(name: str) -> None:
    if not name or not name.strip():
        raise ValueError("Instance name must not be empty")
    if illegal := _ILLEGAL.intersection(name):
        raise ValueError(f"Instance name contains illegal characters: {''.join(sorted(illegal))}")


def _find_instance_key(name: str) -> str | None:
    """Return the Lxss subkey path whose DistributionName is *name*."""
    for guid in _iter_subkeys(_LXSS_KEY):
        path = rf"{_LXSS_KEY}\{guid}"
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
                value, _ = winreg.QueryValueEx(key, "DistributionName")
        except OSError:
            continue
        if value == name:
            return path
    return None


def _iter_subkeys(path: str) -> Iterator[str]:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            for index in range(winreg.QueryInfoKey(key)[0]):
                yield winreg.EnumKey(key, index)
    except OSError as exc:
        raise WslError(f"Cannot read {path}: {exc}") from exc


# ---------------------------------------------------------------------------
# Interaction
# ---------------------------------------------------------------------------
def run_in_instance(
    instance_name: str,
    command: str,
    *,
    user: str | None = None,
    cwd: str | None = None,
    use_shell: bool = True,
    timeout: float | None = 300.0,
) -> sop.CommandResult:
    """Run *command* inside *instance_name* and return its captured result.

    Starting the instance is implicit — WSL boots it to run the command.

    Args:
        instance_name: Instance to run in.
        command: Command line to execute inside the distribution.
        user: Linux user to run as. Defaults to the instance's default user.
        cwd: Linux working directory. Without this the child inherits the
            Windows working directory, which lands you in ``/mnt/c/...``.
        use_shell: Run through the login shell, so pipes, globs and ``&&``
            work. Set false to exec the binary directly.
        timeout: Seconds before the command is killed.

    Returns:
        The CommandResult, falsy when the exit code is non-zero. Note the code
        is the Linux command's own, not WSL's.

    Raises:
        WslError: If the instance does not exist.
    """
    name = _require_instance(instance_name)

    payload = f"cd {shlex.quote(cwd)} && {command}" if cwd else command
    user_flag = f' --user {user}' if user else ""
    mode = "--" if use_shell else "--exec"

    full = f'wsl --distribution {name} {user_flag} {mode} {payload}'
    log.info(f"Running in {emphasize_string(name)}: {emphasize_string(command)}")

    result = run_cmd(full, timeout=timeout)
    if not result.ok:
        log.warning(
            f"Command in {emphasize_err_string(name)} exited {result.returncode}: "
            f"{result.stdout or 'no error output'}"
        )
    return result


def open_in_instance(
    instance_name: str,
    command: str | None = None,
    *,
    user: str | None = None,
    cwd: str | None = None,
) -> int:
    """Run *command* in *instance_name* attached to this terminal.

    Use this for anything the user watches or types into — an editor, ``top``,
    an installer with prompts, or a plain login shell when *command* is None.
    Blocks until the program exits.
    """
    name = _require_instance(instance_name)
    command=command
    user_flag = f' --user {user}' if user else ""
    if command is None:
        full = f'wsl --distribution "{name}"{user_flag}'
        log.info(f"Opening shell in {emphasize_string(name)}")
    else:
        payload = f"cd {shlex.quote(cwd)} && {command}" if cwd else command
        full = f'wsl --distribution {name} {user_flag} -- {payload}'
        log.info(f"Opening {emphasize_string(command)} in {emphasize_string(name)}")

    return sop.spawn_terminal(full)


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


def diagnose() -> None:
    """Print the raw and parsed view of every instance.

    Run this when a name that appears in the list cannot be found by a
    command
    """
    print("--- raw output of 'wsl --list --verbose' ---")
    raw = run_cmd("wsl --list --verbose")
    print(repr(raw.stdout))
    print(f"exit={raw.returncode} stderr={raw.stderr!r}\n")

    print("--- parsed names ---")
    for distro in list_wsl("all"):
        print(f"  {distro['name']!r}  status={distro['status']!r}  default={distro['default']}")

if __name__ == "__main__":
    log.debug(open_in_instance("Ubuntu","ls -la",user="dino").stdout)
    #diagnose()