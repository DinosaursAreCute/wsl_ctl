<p align="center">
  <img src="assets/icon.ico" alt="WSL Controller" width="128">
</p>
  
<h1 align="center">WSL Controller</h1>

<p align="center">A terminal menu for managing WSL distributions on Windows.</p>

---
 
<p align="center">
  <a href="../../releases"><img src="https://img.shields.io/github/v/release/DinosaursAreCute/wsl_ctl?style=flat-square&color=44cc11" alt="Latest release"></a>
  <a href="../../releases"><img src="https://img.shields.io/github/downloads/DinosaursAreCute/wsl_ctl/total?style=flat-square" alt="Downloads"></a>
  <a href="../../stargazers"><img src="https://img.shields.io/github/stars/DinosaursAreCute/wsl_ctl?style=flat-square" alt="Stars"></a>
  <a href="../../commits/master"><img src="https://img.shields.io/github/last-commit/DinosaursAreCute/wsl_ctl?style=flat-square" alt="Last commit"></a>
  <img src="https://img.shields.io/badge/python-3.11%2B-blue?style=flat-square" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/platform-windows-lightgrey?style=flat-square" alt="Windows,Linux">
</p>

## What it does

- List installed instances and available distributions
- Install, remove, start, stop and (eventually) rename instances
- Open a shell in any instance

## Install

Download the latest `wsl_ctl-setup-*.exe` from [Releases](../../releases) and run it.

No admin rights needed as it installs to your user profile, adds itself to `PATH`, and creates a Start Menu entry.

Then open a new terminal or run it from the startmenu:

```powershell
wsl_ctl
```

> [!NOTE]
> Requires WSL. If it's missing, install it with `wsl.exe --install` and reboot.

## Run from source

```powershell
git clone <repo-url>
cd PythonProject1
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
python -m src.main
```

## Build

```powershell
.\build.ps1
```

This writes the version files from `pyproject.toml`, builds `dist\wsl_ctl.exe` with PyInstaller, then compiles the installer to `dist\installer\`.

Needs [Inno Setup](https://jrsoftware.org/isdl.php) for the last step:

```powershell
winget install JRSoftware.InnoSetup
```

To release a new version, bump `version` in `pyproject.toml` and rebuild. Everything else picks it up automatically.

## Layout

```
src/
  ioHelper/       menu framework, shell command execution
  Utils/          logging, config parsing
  wsl_handler/    WSL operations
main.py           entry point
build.ps1         version -> exe -> installer
installer.iss     Inno Setup script
```

## Troubleshooting

**`wsl_ctl` not recognised** — open a new terminal; `PATH` changes don't reach already-running ones.


