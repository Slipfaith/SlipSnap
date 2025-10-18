[Setup]
AppName=SlipSnap
AppVersion=1.0.0
AppPublisher=SlipFaith
DefaultDirName={pf}\SlipSnap
DefaultGroupName=SlipSnap
UninstallDisplayIcon={app}\SlipSnap.exe
OutputDir=E:\PythonProjects\SlipSnap\installer
OutputBaseFilename=SlipSnap_Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "E:\PythonProjects\SlipSnap\build_dist\main.dist\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\SlipSnap"; Filename: "{app}\SlipSnap.exe"; IconFilename: "{app}\SlipSnap.ico"
Name: "{autodesktop}\SlipSnap"; Filename: "{app}\SlipSnap.exe"; IconFilename: "{app}\SlipSnap.ico"

[Run]
Filename: "{app}\SlipSnap.exe"; Description: "Запустить SlipSnap"; Flags: nowait postinstall skipifsilent
