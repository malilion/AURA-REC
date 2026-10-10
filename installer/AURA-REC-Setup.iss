; ==============================================================================
;   AURA REC - Windows Inno Setup 安裝程式腳本
;   產生單一安裝精靈：AURA-REC-Setup.exe
; ==============================================================================

#define MyAppName "AURA REC"
#define MyAppVersion "2.5.3"
#define MyAppPublisher "AURA REC Team"
#define MyAppURL "https://malilion.github.io/Record/"
#define MyAppExeName "AURA-REC.exe"

[Setup]
AppId={{5A8F8279-91B6-4E15-9988-518AE29FE57A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
; 不需要系統管理員：預設裝到目前使用者的 %LocalAppData%\Programs；使用者仍可在精靈中選擇「為所有使用者安裝」
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\{#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=AURA-REC-Setup
SetupIconFile=..\AURA-REC.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "chinesetraditional"; MessagesFile: "ChineseTraditional.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; 主程式 EXE
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
; 附帶工具 (若 dist 目錄下有 ffmpeg.exe 則一併打包)
Source: "..\dist\ffmpeg.exe"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "..\dist\ffprobe.exe"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "..\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\FFMPEG-COPYING.GPLv2"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "..\AURA-REC.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion isreadme

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\AURA-REC.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\AURA-REC.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
