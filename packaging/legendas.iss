; Instalador do CNT Legendas (Inno Setup 6).
; Gerado por packaging\build.ps1, que define AppVersion e BuildDir.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef BuildDir
  #define BuildDir "..\build"
#endif

[Setup]
AppId={{6F3B1E7A-9C2D-4C1B-8B8E-3A5D2F1C7E42}
AppName=CNT Legendas
AppVersion={#AppVersion}
AppVerName=CNT Legendas {#AppVersion}
AppPublisher=Róbson Saldanha
DefaultDirName={autopf}\CNT Legendas
; mesma AppId da versão "Legendas": atualiza por cima, mas na pasta nova
UsePreviousAppDir=no
DefaultGroupName=CNT Legendas
DisableProgramGroupPage=yes
; Instala para todos os perfis do Windows (o PC tem mais de um usuário)
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#BuildDir}\Output
OutputBaseFilename=Instalador_CNT_Legendas_{#AppVersion}
SetupIconFile={#BuildDir}\CNTLegendas\legendas.ico
UninstallDisplayIcon={app}\legendas.ico
UninstallDisplayName=CNT Legendas
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
Name: "{commonappdata}\CNT Legendas"; Permissions: users-modify
Name: "{commonappdata}\CNT Legendas\modelos"; Permissions: users-modify
; atualizações baixadas pelo programa (patches) e a licença deste computador
Name: "{commonappdata}\CNT Legendas\versoes"; Permissions: users-modify
Name: "{commonappdata}\CNT Legendas\licenca"; Permissions: users-modify

[Files]
Source: "{#BuildDir}\CNTLegendas\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#BuildDir}\redist\vc_redist.x64.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: VCRedistNeeded

[Icons]
Name: "{commonprograms}\CNT Legendas"; Filename: "{app}\python\pythonw.exe"; Parameters: "-m cntboot"; WorkingDir: "{app}"; IconFilename: "{app}\legendas.ico"; Comment: "Legendagem automática"; AppUserModelID: "CNT.Legendas"
Name: "{commondesktop}\CNT Legendas"; Filename: "{app}\python\pythonw.exe"; Parameters: "-m cntboot"; WorkingDir: "{app}"; IconFilename: "{app}\legendas.ico"; Comment: "Legendagem automática"; AppUserModelID: "CNT.Legendas"; Tasks: desktopicon

[Run]
Filename: "{tmp}\vc_redist.x64.exe"; Parameters: "/install /quiet /norestart"; StatusMsg: "Instalando componentes do Windows (Visual C++)..."; Flags: waituntilterminated; Check: VCRedistNeeded
Filename: "{app}\python\pythonw.exe"; Parameters: "-m cntboot"; WorkingDir: "{app}"; Description: "Abrir o CNT Legendas agora"; Flags: nowait postinstall skipifsilent runasoriginaluser
; atualização automática: o programa roda este instalador em silêncio com /ABRIR e espera reabrir
Filename: "{app}\python\pythonw.exe"; Parameters: "-m cntboot"; WorkingDir: "{app}"; Flags: nowait runasoriginaluser; Check: AbrirDepois

[InstallDelete]
; versão antiga, com o nome "Legendas": programa e atalhos (os dados ficam e são migrados)
Type: filesandordirs; Name: "{autopf}\Legendas\python"
Type: filesandordirs; Name: "{autopf}\Legendas\core"
Type: filesandordirs; Name: "{autopf}\Legendas\app"
Type: filesandordirs; Name: "{autopf}\Legendas\bin"
Type: files; Name: "{autopf}\Legendas\*"
Type: dirifempty; Name: "{autopf}\Legendas"
Type: files; Name: "{commonprograms}\Legendas.lnk"
Type: files; Name: "{commondesktop}\Legendas.lnk"

[UninstallDelete]
; arquivos .pyc gerados em uso; os dados de cada perfil (%APPDATA%\CNT Legendas) são mantidos
Type: filesandordirs; Name: "{app}\core"
Type: filesandordirs; Name: "{app}\app"
Type: filesandordirs; Name: "{app}\python"
Type: files; Name: "{app}\cntboot.py"
Type: filesandordirs; Name: "{app}\__pycache__"
Type: dirifempty; Name: "{app}"

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  OldDir, NewDir: String;
begin
  if CurStep = ssInstall then
  begin
    { modelos de alinhamento já baixados pela versão "Legendas" }
    OldDir := ExpandConstant('{commonappdata}\Legendas');
    NewDir := ExpandConstant('{commonappdata}\CNT Legendas');
    if DirExists(OldDir) and not DirExists(NewDir) then
      RenameFile(OldDir, NewDir);
  end;
end;

function AbrirDepois: Boolean;
var
  I: Integer;
begin
  Result := False;
  for I := 1 to ParamCount do
    if CompareText(ParamStr(I), '/ABRIR') = 0 then
      Result := True;
end;

function VCRedistNeeded: Boolean;
var
  Installed: Cardinal;
begin
  Result := True;
  if RegQueryDWordValue(HKLM64, 'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64', 'Installed', Installed) then
    Result := (Installed <> 1);
end;
