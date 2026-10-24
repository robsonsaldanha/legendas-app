; Instalador da CNT Dubla (Inno Setup 6) — o mesmo programa montado do CNT Legendas, aberto com `cntboot --produto dubla`.
; Gerado por packaging\build.ps1, que define AppVersion (versão da Dubla) e BuildDir.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef BuildDir
  #define BuildDir "..\build"
#endif

[Setup]
AppId={{B6E2D4A1-5F3C-4E8B-9A71-2C4D6E8F0A13}
AppName=CNT Dubla
AppVersion={#AppVersion}
AppVerName=CNT Dubla {#AppVersion}
AppPublisher=Róbson Saldanha
DefaultDirName={autopf}\CNT Dubla
DefaultGroupName=CNT Dubla
DisableProgramGroupPage=yes
; para todos os perfis do Windows (estúdio com mais de um usuário no mesmo computador)
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#BuildDir}\Output
OutputBaseFilename=Instalador_CNT_Dubla_{#AppVersion}
SetupIconFile={#BuildDir}\CNTLegendas\dubla.ico
UninstallDisplayIcon={app}\dubla.ico
UninstallDisplayName=CNT Dubla
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
Name: "{commonappdata}\CNT Dubla"; Permissions: users-modify
Name: "{commonappdata}\CNT Dubla\modelos"; Permissions: users-modify
Name: "{commonappdata}\CNT Dubla\versoes"; Permissions: users-modify
Name: "{commonappdata}\CNT Dubla\licenca"; Permissions: users-modify

[Files]
Source: "{#BuildDir}\CNTLegendas\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#BuildDir}\redist\vc_redist.x64.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: VCRedistNeeded

[Icons]
Name: "{commonprograms}\CNT Dubla"; Filename: "{app}\python\pythonw.exe"; Parameters: "-m cntboot --produto dubla"; WorkingDir: "{app}"; IconFilename: "{app}\dubla.ico"; Comment: "Estúdio de dublagem"; AppUserModelID: "CNT.Dubla"
Name: "{commondesktop}\CNT Dubla"; Filename: "{app}\python\pythonw.exe"; Parameters: "-m cntboot --produto dubla"; WorkingDir: "{app}"; IconFilename: "{app}\dubla.ico"; Comment: "Estúdio de dublagem"; AppUserModelID: "CNT.Dubla"; Tasks: desktopicon

[Run]
Filename: "{tmp}\vc_redist.x64.exe"; Parameters: "/install /quiet /norestart"; StatusMsg: "Instalando componentes do Windows (Visual C++)..."; Flags: waituntilterminated; Check: VCRedistNeeded
Filename: "{app}\python\pythonw.exe"; Parameters: "-m cntboot --produto dubla"; WorkingDir: "{app}"; Description: "Abrir a CNT Dubla agora"; Flags: nowait postinstall skipifsilent runasoriginaluser
; atualização automática: o programa roda este instalador em silêncio com /ABRIR e espera reabrir
Filename: "{app}\python\pythonw.exe"; Parameters: "-m cntboot --produto dubla"; WorkingDir: "{app}"; Flags: nowait runasoriginaluser; Check: AbrirDepois

[UninstallDelete]
; arquivos .pyc gerados em uso; os dados de cada perfil (%APPDATA%\CNT Dubla) e os projetos ficam
Type: filesandordirs; Name: "{app}\core"
Type: filesandordirs; Name: "{app}\app"
Type: filesandordirs; Name: "{app}\dubla"
Type: filesandordirs; Name: "{app}\python"
Type: files; Name: "{app}\cntboot.py"
Type: filesandordirs; Name: "{app}\__pycache__"
Type: dirifempty; Name: "{app}"

[Code]
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
