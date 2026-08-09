; Inno Setup script for wsl_ctl
;
; Build the exe first, then compile this:
;   pyinstaller wsl_ctl.spec
;   iscc installer.iss
;
; Produces dist\installer\wsl_ctl-setup-0.2.2.exe
;
; Installs per-user (no admin prompt): the app lives in %LOCALAPPDATA%, PATH
; is written to HKCU\Environment, and shortcuts go in the user's Start Menu.
; This matches WSL itself, which registers distributions per-user.
#include "version.iss"
#define AppName        "WSL Controller"
#define AppExeName     "wsl_ctl.exe"
#define AppPublisher   "DinosaursAreCute"
#define AppId          "{{8F3C2A61-4D9E-4B77-9E14-2C6A1B5D0F32}"

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
VersionInfoVersion={#AppVersion}

; lowest = no UAC prompt, installs for the current user only.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto

OutputDir=dist\installer
OutputBaseFilename=wsl_ctl-setup-{#AppVersion}
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

; Tells Explorer the environment changed, so new terminals see the new PATH
; without a reboot. Without this, PATH updates go unnoticed until logoff.
ChangesEnvironment=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "addtopath"; Description: "Add wsl_ctl to my PATH"; GroupDescription: "Integration:"
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Integration:"; Flags: unchecked

[Files]
; --onefile build: a single executable.
Source: "dist\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion
; --onedir build: comment the line above and uncomment these two instead.
; Source: "dist\wsl_ctl\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion
; Source: "dist\wsl_ctl\*";             DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Registry]
; Append to the user's PATH. Check: prevents a duplicate entry on reinstall,
; which is the usual way PATH grows unbounded across upgrades.
Root: HKCU; Subkey: "Environment"; ValueType: expandsz; ValueName: "Path"; \
    ValueData: "{olddata};{app}"; \
    Tasks: addtopath; Check: NeedsAddPath(ExpandConstant('{app}'))

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; \
    Flags: postinstall nowait skipifsilent

[Code]
function NeedsAddPath(Param: string): Boolean;
var
  OrigPath: string;
begin
  //True when {app} is not already a PATH entry. Semicolons around both sides
  //  stop C:\Tools\udm matching C:\Tools\wsl_ctl. }
  if not RegQueryStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', OrigPath) then
  begin
    Result := True;
    exit;
  end;
  Result := Pos(';' + Uppercase(Param) + ';', ';' + Uppercase(OrigPath) + ';') = 0;
end;

procedure RemovePath(Param: string);
var
  OrigPath: string;
  Position: Integer;
begin
  if not RegQueryStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', OrigPath) then
    exit;

  Position := Pos(';' + Uppercase(Param), ';' + Uppercase(OrigPath));
  if Position = 0 then
    exit;

  Delete(OrigPath, Position, Length(Param) + 1);
  RegWriteExpandStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', OrigPath);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    RemovePath(ExpandConstant('{app}'));
end;
