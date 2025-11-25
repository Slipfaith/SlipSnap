[Setup]
AppName=SlipSnap
AppVersion=2.0.0
AppPublisher=slipfaith
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
; Файлы программы SlipSnap
Source: "E:\PythonProjects\SlipSnap\dist\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; Инсталлятор Tesseract (лежит рядом с этим .iss)
Source: "tesseract-ocr-w64-setup-5.5.0.2024.exe"; DestDir: "{tmp}"

[Icons]
Name: "{autoprograms}\SlipSnap"; Filename: "{app}\SlipSnap.exe"; IconFilename: "{app}\SlipSnap.ico"
Name: "{autodesktop}\SlipSnap"; Filename: "{app}\SlipSnap.exe"; IconFilename: "{app}\SlipSnap.ico"

[Run]
; Установка Tesseract
Filename: "{tmp}\tesseract-ocr-w64-setup-5.5.0.2024.exe"; \
  Parameters: "/silent"; \
  StatusMsg: "Устанавливается Tesseract OCR..."; \
  Check: NeedTesseract

; Добавляем Tesseract в PATH
Filename: "cmd.exe"; \
  Parameters: "/c setx PATH ""%PATH%;{pf}\Tesseract-OCR"""; \
  Flags: runhidden; \
  Check: NeedTesseract

; Запуск SlipSnap
Filename: "{app}\SlipSnap.exe"; Description: "Запустить SlipSnap"; Flags: nowait postinstall skipifsilent

[Code]

function NeedTesseract(): Boolean;
var
  OCRPath: string;
begin
  OCRPath := ExpandConstant('{pf}\Tesseract-OCR\tesseract.exe');
  Result := not FileExists(OCRPath);
end;
