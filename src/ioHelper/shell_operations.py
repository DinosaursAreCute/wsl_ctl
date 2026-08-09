from __future__ import annotations

import shutil

import colorama as c
import src.Utils.Logger as logger
import os
import shlex
import subprocess
import locale
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
# ============= Objects and static variables =============
log: logger = logger.LoggerClass("shell_operations",0)
DEFAULT_TIMEOUT = 60.0

# ============= Helper Functions =============

def emphasize_string(s):
    return c.Fore.CYAN + c.Style.BRIGHT + str(s) + c.Fore.RESET + c.Style.RESET_ALL

def emphasize_err_string(s):
    return c.Fore.RED + c.Style.BRIGHT + str(s) + c.Fore.RESET + c.Style.RESET_ALL

def _decode(raw: bytes | None) -> str:
    """Decode child output, tolerating UTF-16 emitted by some Windows tools."""
    if not raw:
        return ""

    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16", errors="replace")

    # wsl.exe and friends emit UTF-16LE with no BOM; interleaved NULs give it away.
    if b"\x00" in raw[:64]:
        encoding = "utf-16-le" if raw[1:2] == b"\x00" else "utf-16-be"
        return raw.decode(encoding, errors="replace")

    for encoding in ("utf-8", locale.getpreferredencoding(False)):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")

# ============= cmd helper Functions =============
"""Helpers for running external commands."""
class CommandError(RuntimeError):
    """Raised when a command cannot be executed or does not finish in time."""

@dataclass(frozen=True, slots=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def __bool__(self) -> bool:
        return self.ok

# ============= Logic =============
@dataclass(frozen=True, slots=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def __bool__(self) -> bool:
        return self.ok


def run_cmd(
    command: str | Sequence[str],
    *,
    use_shell:bool=True,
    shell_executable: str | None = None,
    cwd: str | os.PathLike[str] | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float | None = DEFAULT_TIMEOUT,
    check: bool = False,
    quiet: bool = True,
) -> CommandResult:
    """Run *command* and return its result.

    Args:
        command: Either an argument list (preferred) or a string. A string is
            split with :func:`shlex.split` unless *shell_executable* is given,
            in which case it is passed to that shell via ``-c``.
        shell_executable: Shell to interpret *command* with, e.g. ``"/bin/bash"``.
            Only use this with trusted input — it enables shell metacharacters.
        cwd: Working directory for the child process.
        env: Environment for the child process; inherits the parent's if omitted.
        timeout: Seconds to wait before killing the process. ``None`` waits forever.
        check: Raise :class:`subprocess.CalledProcessError` on a non-zero exit.
        quiet: reduces log level to avoid cluttering the output

    Raises:
        ValueError: If *command* is empty.
        CommandError: If the executable is missing or the command times out.
        subprocess.CalledProcessError: If *check* is true and the exit code is non-zero.
    """
    if quiet:
        tmp_logger_level=log.logger_level
        log.logger_level=2

    log.debug(
        f"Args received: {emphasize_string('command')}={command!r}, "
        f"{emphasize_string('shell_executable')}={shell_executable!r}, "
        f"{emphasize_string('cwd')}={cwd!r}, "
        f"{emphasize_string('timeout')}={timeout!r}, "
        f"{emphasize_string('check')}={check!r}"
    )

    if use_shell:
        if not isinstance(command, str) or not command.strip():
            raise ValueError("use_shell requires a non-empty command string")
        if shell_executable:
            raise ValueError("use_shell and shell_executable are mutually exclusive")
        argv: str | list[str] = command
        printable = emphasize_string(command)
    else:
        argv = _build_argv(command, shell_executable)
        printable = emphasize_string(shlex.join(argv))
    log.info(f"Running command: {printable}")
    try:
        completed = subprocess.run(
            argv,
            shell = use_shell,
            capture_output = True,
            text = False,
            timeout = timeout,
            cwd = cwd,
            env = dict(env) if env is not None else None,
            check = check,
        )
    except FileNotFoundError as exc:
        message = f"Executable not found: {emphasize_err_string(argv[0])}"
        log.error(message)
        if quiet:
            log.logger_level = tmp_logger_level
        raise CommandError(message) from exc
    except subprocess.TimeoutExpired as exc:
        message = f"Command {printable} timed out after {emphasize_string(str(timeout))}s"
        log.error(message)
        if quiet:
            log.logger_level = tmp_logger_level
        raise CommandError(message) from exc

    result = CommandResult(
        argv = tuple(argv),
        returncode = completed.returncode,
        stdout = _decode(completed.stdout),
        stderr = _decode(completed.stderr),
    )

    code = emphasize_string(str(result.returncode))
    if result.ok:
        log.success(f"Command {printable} finished with code: {code}")
        stdout = emphasize_string(_one_line(result.stdout))
        log.debug(f"stdout: {stdout}")
    else:
        stderr = emphasize_err_string(_one_line(result.stderr))
        log.warning(f"Command failed with code {code}.\nstderr: {stderr}")
    if quiet:
        log.logger_level = tmp_logger_level
    return result


def _build_argv(command: str | Sequence[str], shell_executable: str | None) -> list[str]:
    if isinstance(command, str):
        if not command.strip():
            log.error("Empty string for command was passed")
            raise ValueError("command must be a non-empty string")
        if shell_executable:
            log.debug(f"Interpreting command with shell: {emphasize_string(shell_executable)}")
            return [shell_executable, "-c", command]
        return shlex.split(command)

    argv = [str(part) for part in command]
    if not argv:
        log.error("Empty argument list for command was passed")
        raise ValueError("command must contain at least one argument")
    if shell_executable:
        raise ValueError("shell_executable is only valid with a string command")
    return argv

def spawn_terminal(
    command: str,
    *,
    title: str = "",
    keep_open: bool = True,
    wait: bool = False,
    timeout: float | None = None,
) -> int | None:
    """Launch *command* in a new terminal window.

    Args:
        command: Command line to run, interpreted by the new window's shell.
        title: Window title, where the terminal supports one.
        keep_open: Leave the window open after the command finishes. Combined
            with *wait*, this blocks until the user closes the window rather
            than until the command exits.
        wait: Block until the window closes.
        timeout: Seconds to wait before giving up. ``None`` waits forever.
            Ignored unless *wait* is set.

    Returns:
        The terminal's exit code when *wait* is set, otherwise ``None``. Note
        this is the *terminal's* code, which most emulators do not inherit
        from the command — do not read it as the command's success.

    Raises:
        CommandError: If no supported terminal was found, or the wait timed out.
    """
    argv = _terminal_argv(command, title=title, keep_open=keep_open, wait=wait)
    log.info(f"Spawning terminal: {emphasize_string(shlex.join(argv))}")

    try:
        process = subprocess.Popen(argv, start_new_session=not wait and os.name != "nt")
    except FileNotFoundError as exc:
        raise CommandError(f"Terminal not found: {argv[0]}") from exc

    if not wait:
        return None

    try:
        return process.wait(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        process.kill()
        raise CommandError(f"Terminal did not close within {timeout}s") from exc

def run_interactive(command: str) -> int:
    """Run *command* attached to this terminal, so it can draw and take input.

    Output is not captured: the child inherits stdin, stdout and stderr.
    """
    log.info(f"Running interactively: {emphasize_string(command)}")
    return subprocess.run(command, shell=True).returncode

def _terminal_argv(command: str, *, title: str, keep_open: bool, wait: bool) -> list[str]:
    if os.name == "nt":
        comspec = os.environ.get("COMSPEC") or "cmd.exe"
        flag = "/k" if keep_open else "/c"
        # 'start' returns as soon as the window exists; /wait makes it block.
        start = ["start", "/wait"] if wait else ["start"]
        return [comspec, "/c", *start, title or "", comspec, flag, command]

    tail = "; exec $SHELL" if keep_open else ""
    for emulator, args in (
        ("gnome-terminal", ["gnome-terminal", *(["--wait"] if wait else []),
                            "--title", title or "Command", "--", "sh", "-c", command + tail]),
        ("konsole", ["konsole", "-e", "sh", "-c", command + tail]),
        ("xterm", ["xterm", "-title", title or "Command", "-e", "sh", "-c", command + tail]),
    ):
        if shutil.which(emulator):
            return args
    raise CommandError("No supported terminal emulator found")


def comspec_sh() -> str:
    return shutil.which("sh") or "/bin/sh"

def _one_line(text: str) -> str:
    """Collapse output to a single line so it does not break log formatting."""
    return " ".join(text.split())