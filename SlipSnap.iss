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
; Файлы программы
Source: "E:\PythonProjects\SlipSnap\build_dist\main.dist\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; Инсталлятор Tesseract (должен лежать рядом с этим .iss файлом)
Source: "tesseract-ocr-w64-setup-5.5.0.2024.exe"; DestDir: "{tmp}"; Flags: dontcopy

[Icons]
Name: "{autoprograms}\SlipSnap"; Filename: "{app}\SlipSnap.exe"; IconFilename: "{app}\SlipSnap.ico"
Name: "{autodesktop}\SlipSnap"; Filename: "{app}\SlipSnap.exe"; IconFilename: "{app}\SlipSnap.ico"

[Run]
; Установка Tesseract, если его нет
Filename: "{tmp}\tesseract-ocr-w64-setup-5.5.0.2024.exe"; \
  Parameters: "/silent"; \
  StatusMsg: "Устанавливается Tesseract OCR..."; \
  Check: NeedTesseract

; Запуск SlipSnap после установки
Filename: "{app}\SlipSnap.exe"; Description: "Запустить SlipSnap"; Flags: nowait postinstall skipifsilent

[Code]

function NeedTesseract(): Boolean;
var
  OCRPath: string;
begin
  // Проверяем стандартный путь Tesseract
  OCRPath := ExpandConstant('{pf}\Tesseract-OCR\tesseract.exe');
  Result := not FileExists(OCRPath);
end;
