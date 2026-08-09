$ErrorActionPreference = 'Stop'
$iscc = "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"

python make_version_file.py        # writes version_info.txt AND version.iss
pyinstaller wsl_ctl.spec
& $iscc .\installer.iss