; Instalador do Legendas (Inno Setup 6).
; Gerado por packaging\build.ps1, que define AppVersion e BuildDir.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef BuildDir
  #define BuildDir "..\build"
#endif

[Setup]
AppId={{6F3B1E7A-9C2D-4C1B-8B8E-3A5D2F1C7E42}
AppName=Legendas
AppVersion={#AppVersion}
AppVerName=Legendas {#AppVersion}
AppPublisher=Róbson Saldanha
DefaultDirName={autopf}\Legendas
DefaultGroupName=Legendas
DisableProgramGroupPage=yes
; Instala para todos os perfis do Windows (o PC tem mais de um usuário)
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#BuildDir}\Output
OutputBaseFilename=Instalador_Legendas_{#AppVersion}
SetupIconFile={#BuildDir}\Legendas\legendas.ico
UninstallDisplayIcon={app}\legendas.ico
UninstallDisplayName=Legendas
Compression=lzma2/max
SolidCompression=yes
LZMANumBlockThreads=4
WizardStyle=modern
CloseApplications=force
RestartApplications=no
ShowLanguageDialog=no

[Languages]
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho (para todos os usuários)"; GroupDescription: "Atalhos:"

[Dirs]
; Modelos de alinhamento compartilhados entre os perfis: todos podem gravar
Name: "{commonappdata}\Legendas"; Permissions: users-modify
Name: "{commonappdata}\Legendas\modelos"; Permissions: users-modify

[Files]
Source: "{#BuildDir}\Legendas\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#BuildDir}\redist\vc_redist.x64.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: VCRedistNeeded

[Icons]
Name: "{commonprograms}\Legendas"; Filename: "{app}\python\pythonw.exe"; Parameters: "-m app"; WorkingDir: "{app}"; IconFilename: "{app}\legendas.ico"; Comment: "Legendagem automática"
Name: "{commondesktop}\Legendas"; Filename: "{app}\python\pythonw.exe"; Parameters: "-m app"; WorkingDir: "{app}"; IconFilename: "{app}\legendas.ico"; Comment: "Legendagem automática"; Tasks: desktopicon

[Run]
Filename: "{tmp}\vc_redist.x64.exe"; Parameters: "/install /quiet /norestart"; StatusMsg: "Instalando componentes do Windows (Visual C++)..."; Flags: waituntilterminated; Check: VCRedistNeeded
Filename: "{app}\python\pythonw.exe"; Parameters: "-m app"; WorkingDir: "{app}"; Description: "Abrir o Legendas agora"; Flags: nowait postinstall skipifsilent runasoriginaluser

[UninstallDelete]
; arquivos .pyc gerados em uso; os dados de cada perfil (%APPDATA%\Legendas) são mantidos
Type: filesandordirs; Name: "{app}\core"
Type: filesandordirs; Name: "{app}\app"

[Code]
function VCRedistNeeded: Boolean;
var
  Installed: Cardinal;
begin
  Result := True;
  if RegQueryDWordValue(HKLM64, 'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64', 'Installed', Installed) then
    Result := (Installed <> 1);
end;
