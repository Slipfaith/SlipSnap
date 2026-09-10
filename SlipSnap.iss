[Setup]
AppName=SlipSnap
AppVersion=3.3.2
AppPublisher=slipfaith
SetupIconFile=SlipSnap.ico
DefaultDirName={autopf}\SlipSnap
DefaultGroupName=SlipSnap
UninstallDisplayIcon={app}\SlipSnap.exe
OutputDir={#SourcePath}\installer
OutputBaseFilename=SlipSnap_Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
russian.AutoStartTask=Запускать SlipSnap при входе в Windows
english.AutoStartTask=Launch SlipSnap when Windows starts

[Tasks]
Name: "autostart"; Description: "{cm:AutoStartTask}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Файлы программы SlipSnap
Source: "{#SourcePath}\dist\SlipSnap.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourcePath}\SlipSnap.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\SlipSnap"; Filename: "{app}\SlipSnap.exe"; IconFilename: "{app}\SlipSnap.ico"
Name: "{autodesktop}\SlipSnap"; Filename: "{app}\SlipSnap.exe"; IconFilename: "{app}\SlipSnap.ico"
Name: "{userstartup}\SlipSnap"; Filename: "{app}\SlipSnap.exe"; WorkingDir: "{app}"; IconFilename: "{app}\SlipSnap.ico"; Tasks: autostart

[Run]
; Запуск SlipSnap
Filename: "{app}\SlipSnap.exe"; Description: "Запустить SlipSnap"; Flags: nowait postinstall skipifsilent
