; Inno Setup script -- wraps the portable "Hongtai Screen.exe" PyInstaller
; already builds (see packaging\hongtai_screen.spec) into a real Windows
; installer: Start Menu/Desktop shortcuts, an Add/Remove Programs entry,
; a proper uninstaller, and -- the reason this exists at all -- silent-
; install support with documented exit codes, which distribution channels
; like the Microsoft Store require and a bare portable exe can't provide
; (it doesn't "install" anything; running it just launches the app).
;
; Build (Windows only, requires Inno Setup 6: https://jrsoftware.org/isinfo.php):
;   1. Build "dist\Hongtai Screen.exe" first (see BUILD.md / build_local.ps1) --
;      this script only packages that exe, it doesn't build the app itself.
;   2. ISCC packaging\hongtai_screen.iss /DAppVersion=2.1.1
;      (AppVersion defaults to 0.0.0-local below if omitted, for a quick
;      local test compile.)
;
; Output: dist\Rigvue-Setup.exe
;
; Silent install (what a Store/winget-style submission form asks for):
;   Rigvue-Setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
;
; Exit codes are Inno Setup's own standard ones (documented at
; https://jrsoftware.org/ishelp/topic_setupexitcodes.htm) -- this script
; doesn't override or add custom codes, so the table below is what to type
; into a submission form asking for "EXE return code value" per scenario:
;   0 success | 1 failed to initialize | 2 user cancelled |
;   3 critical error preparing install | 4 fatal error during install |
;   5 user cancelled/aborted during install | 6 forcibly terminated |
;   7 can't proceed | 8 can't proceed, restart needed first

#ifndef AppVersion
  #define AppVersion "0.0.0-local"
#endif

; Everything below is relative to THIS FILE's own directory (packaging\),
; not whatever directory ISCC happens to be invoked from -- Inno Setup's
; default SourceDir behavior already gives us that anchoring for free, so
; unlike hongtai_screen.spec's REPO_ROOT dance this doesn't need any extra
; plumbing; just consistently write "..\" to reach the repo root.

[Setup]
; Fixed, never-reused GUID -- this is what Inno Setup/Windows actually
; uses to recognize "this is the same app, upgrade in place" across
; versions. Do not regenerate this for a version bump; only if the app
; is meant to be treated as a wholly different product from here on.
AppId={{B8F2C1A4-6D3E-4F1A-9C5B-2E7D4A1F8C3D}
; "Rigvue" is the Microsoft Store listing name (reserved there since
; the OEM's own "Hongtai" name doesn't help anyone discover this app,
; but the app/repo itself keeps that name everywhere else -- see
; README.md/CHANGELOG.md). This is what actually shows up in Windows'
; "Installed apps"/"Add or Remove Programs" list, which is also why it
; has to be here: the Store's automated package-validation flagged a
; prior submission because it couldn't match the app name it was told
; about ("Rigvue") against what the installer had actually registered
; ("Hongtai Screen") -- this is that fix. OutputBaseFilename below is
; "Rigvue-Setup" for the same consistency reason (see its own comment).
; Deliberately NOT renamed: the built exe itself stays
; "Hongtai Screen.exe" everywhere below (Source/Filename/
; UninstallDisplayIcon/CloseRunningApp) -- it's not customer-visible
; the way AppName/the shortcuts/the install folder/the installer
; filename are, and PyInstaller's own output name (hongtai_screen.spec)
; is a separate build step this file doesn't control.
AppName=Rigvue
AppVersion={#AppVersion}
AppPublisher=magoumi
AppPublisherURL=https://github.com/M-Agoumi/XTRMLAB-SPECTRA-LCD
AppSupportURL=https://github.com/M-Agoumi/XTRMLAB-SPECTRA-LCD/issues
AppUpdatesURL=https://github.com/M-Agoumi/XTRMLAB-SPECTRA-LCD/releases

; {autopf}\Rigvue + PrivilegesRequired=lowest + the Overrides
; setting below is Inno Setup's own recommended modern combo: an
; interactive run offers a choice ("install for me" vs "install for all
; users, needs admin"), and a non-admin standard-user account still gets
; a working per-user install instead of failing outright. A silent
; install (what the Store actually runs) skips the dialog and just picks
; the per-user path with no prompt -- exactly what an unattended install
; needs. See https://jrsoftware.org/ishelp/topic_admininstallmode.htm
DefaultDirName={autopf}\Rigvue
DefaultGroupName=Rigvue
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

OutputDir=..\dist
OutputBaseFilename=Rigvue-Setup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\Hongtai Screen.exe
LicenseFile=..\LICENSE

Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
; PyInstaller's --onefile build already bakes in the frontend, fonts,
; backgrounds and icon (see hongtai_screen.spec's datas=[...]), so this
; one exe really is the entire app -- nothing else needs to ship.
Source: "..\dist\Hongtai Screen.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Rigvue"; Filename: "{app}\Hongtai Screen.exe"
Name: "{group}\Uninstall Rigvue"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Rigvue"; Filename: "{app}\Hongtai Screen.exe"; Tasks: desktopicon

[Run]
; skipifsilent matters here specifically: a silent/unattended install
; (what the Store, or `/VERYSILENT`, runs) must NOT pop the app open on
; its own -- Store certification runs installs unattended and doesn't
; expect a GUI window to appear uninvited. An interactive install still
; offers the normal "Launch now?" checkbox.
Filename: "{app}\Hongtai Screen.exe"; Description: "Launch Rigvue"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Best-effort cleanup of the Task Scheduler entry startup_registration.py
; creates (STARTUP_TASK_NAME = "HongtaiScreenApp") when "Launch at Windows
; startup" is turned on. RunOnceId dedupes if this ever runs twice; a
; missing task (schtasks exits non-zero) is a perfectly fine outcome and
; doesn't fail the uninstall. Only removes a task this same user account
; can already manage -- one created via the elevated path (see
; startup_registration.py's _run_schtasks_elevated()) by a DIFFERENT
; account needs that account's own elevation to remove, same as it did
; to create; that's an acceptable edge case for a best-effort cleanup.
Filename: "{sys}\schtasks.exe"; Parameters: "/Delete /TN ""HongtaiScreenApp"" /F"; Flags: runhidden; RunOnceId: "RemoveStartupTask"

[UninstallDelete]
; The non-elevated startup fallback: a .vbs shortcut in the user's own
; Startup folder (see startup_registration.py, "shell:startup/Run-key
; entries get funneled through"). {userstartup} is Inno Setup's own
; constant for exactly that folder.
Type: files; Name: "{userstartup}\HongtaiScreenApp.vbs"

; Deliberately NOT removing %LOCALAPPDATA%\HongtaiScreen (app_config.json,
; startup_debug.log -- see paths.py's USER_DATA_DIR) on uninstall: that's
; the user's saved settings/layout, and the standard expectation is that
; reinstalling the app should pick up where they left off, not reset
; everything. If a future "reset app data" option is wanted, add it as an
; explicit opt-in checkbox here rather than deleting it by default.

[Code]
procedure CloseRunningApp;
var
  ResultCode: Integer;
begin
  // Best-effort: the tray process (and any spawned --ui webview child --
  // see app.py's own docstring on the single-exe dispatch) holds
  // "Hongtai Screen.exe" open while running, which would otherwise make
  // the file copy below fail with a sharing violation on an upgrade.
  // taskkill's exit code is ignored -- "no such process" is just as
  // fine an outcome here as "killed it".
  Exec(ExpandConstant('{cmd}'), '/C taskkill /IM "Hongtai Screen.exe" /F /T',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

function InitializeSetup(): Boolean;
begin
  CloseRunningApp;
  Result := True;
end;

function InitializeUninstall(): Boolean;
begin
  CloseRunningApp;
  Result := True;
end;
