# Monta o programa completo em build\CNTLegendas e gera o instalador.
#
# Resultado: build\Output\Instalador_CNT_Legendas_<versão>.exe
#
# Precisa (só na máquina que monta, não na da usuária): Python 3.12 no PATH,
# Inno Setup 6 e internet. O GitHub Actions roda este script.
#
#   powershell -ExecutionPolicy Bypass -File packaging\build.ps1

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$Stage = "início"
trap {
    $msg = "$($_.Exception.Message) [etapa: $Stage, linha $($_.InvocationInfo.ScriptLineNumber)]"
    if ($env:GITHUB_ACTIONS) { Write-Host "::error title=Montagem do instalador::$msg" }
    Write-Error $msg
    exit 1
}

$PyVersion = "3.12.10"
$FfmpegZips = @(
    "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
)
$VcRedist  = "https://aka.ms/vs/17/release/vc_redist.x64.exe"

$Root  = Resolve-Path (Join-Path $PSScriptRoot "..")
$Build = Join-Path $Root "build"
$App   = Join-Path $Build "CNTLegendas"
$Py    = Join-Path $App "python"
$Dl    = Join-Path $Build "downloads"

$Version = (& python -c "import sys; sys.path.insert(0, r'$Root'); import core; print(core.__version__)").Trim()
Write-Host "== CNT Legendas $Version =="

Remove-Item $App -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $App, $Py, $Dl, (Join-Path $App "bin"), (Join-Path $Build "redist") | Out-Null

function Get-File($url, $dest) {
    if (-not (Test-Path $dest)) {
        Write-Host "Baixando $url"
        Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing
    }
}

# ---------------------------------------------------------------- Python embutido
$Stage = "python embutido"
$embedZip = Join-Path $Dl "python-$PyVersion-embed-amd64.zip"
Get-File "https://www.python.org/ftp/python/$PyVersion/python-$PyVersion-embed-amd64.zip" $embedZip
Expand-Archive $embedZip -DestinationPath $Py -Force

# Caminhos do Python embutido: biblioteca padrão, site-packages e a pasta do programa (..)
$pth = Get-ChildItem $Py -Filter "python3*._pth" | Select-Object -First 1
$zipName = (Get-ChildItem $Py -Filter "python3*.zip" | Select-Object -First 1).Name
@($zipName, ".", "Lib\site-packages", "..", "import site") | Set-Content -Path $pth.FullName -Encoding ascii

# tkinter (janelas "Abrir"/"Salvar como") não vem no Python embutido: copia do Python da máquina de montagem
$Stage = "tkinter"
$hostPy = (& python -c "import sys; print(sys.base_prefix)").Trim()
$hostVer = (& python -c "import sys; print('%d.%d' % sys.version_info[:2])").Trim()
if ($hostVer -ne "3.12") { throw "O Python da montagem precisa ser 3.12 (encontrado $hostVer)" }
Copy-Item (Join-Path $hostPy "DLLs\_tkinter.pyd") $Py
# DLLs do Tcl/Tk e suas dependências (o que ainda não existe no Python embutido)
$hostDlls = Get-ChildItem (Join-Path $hostPy "DLLs") -Filter "*.dll"
foreach ($d in $hostDlls) {
    if (-not (Test-Path (Join-Path $Py $d.Name))) { Copy-Item $d.FullName $Py; Write-Host "copiado $($d.Name)" }
}
$hostVerFull = (& python -c "import sys; print(sys.version.split()[0])").Trim()
if ($env:GITHUB_ACTIONS) { Write-Host "::notice title=Python da montagem::$hostVerFull; DLLs: $(($hostDlls | ForEach-Object Name) -join ', ')" }
Copy-Item (Join-Path $hostPy "Lib\tkinter") (Join-Path $Py "tkinter") -Recurse
Copy-Item (Join-Path $hostPy "tcl") (Join-Path $Py "tcl") -Recurse
Remove-Item (Join-Path $Py "tkinter\test") -Recurse -Force -ErrorAction SilentlyContinue

# ---------------------------------------------------------------- bibliotecas
$Stage = "bibliotecas"
$site = Join-Path $Py "Lib\site-packages"
& python -m pip install --disable-pip-version-check --no-warn-script-location --target $site `
    torch --index-url https://download.pytorch.org/whl/cpu
if ($LASTEXITCODE) { throw "falha ao instalar torch" }
& python -m pip install --disable-pip-version-check --no-warn-script-location --target $site `
    -r (Join-Path $Root "requirements.txt") -r (Join-Path $Root "requirements-align.txt")
if ($LASTEXITCODE) { throw "falha ao instalar as bibliotecas" }
# limpeza: testes e caches que não servem para nada no programa instalado
Get-ChildItem $site -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
Get-ChildItem $site -Directory | Where-Object { $_.Name -in @("bin") } | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $site "torch\include") -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $site "torch\test") -Recurse -Force -ErrorAction SilentlyContinue

# ---------------------------------------------------------------- código do programa
$Stage = "código"
Copy-Item (Join-Path $Root "core") (Join-Path $App "core") -Recurse
Copy-Item (Join-Path $Root "app") (Join-Path $App "app") -Recurse
Get-ChildItem $App -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
& python -m compileall -q -f (Join-Path $App "core") (Join-Path $App "app") | Out-Null

# ---------------------------------------------------------------- ffmpeg
$Stage = "ffmpeg"
$ffZip = Join-Path $Dl "ffmpeg.zip"
foreach ($u in $FfmpegZips) {
    try { Get-File $u $ffZip; break } catch { Write-Host "Falhou $u : $($_.Exception.Message)"; Remove-Item $ffZip -ErrorAction SilentlyContinue }
}
if (-not (Test-Path $ffZip)) { throw "não consegui baixar o ffmpeg" }
$ffDir = Join-Path $Dl "ffmpeg"
Remove-Item $ffDir -Recurse -Force -ErrorAction SilentlyContinue
Expand-Archive $ffZip -DestinationPath $ffDir -Force
Get-ChildItem $ffDir -Recurse -Include "ffmpeg.exe", "ffprobe.exe" | Copy-Item -Destination (Join-Path $App "bin")
if (-not (Test-Path (Join-Path $App "bin\ffprobe.exe"))) { throw "ffmpeg não encontrado no pacote" }

# ---------------------------------------------------------------- VC++ e ícone
$Stage = "vc++ e ícone"
Get-File $VcRedist (Join-Path $Build "redist\vc_redist.x64.exe")
& python -m pip install --disable-pip-version-check -q pillow
& python (Join-Path $PSScriptRoot "make_icon.py") (Join-Path $App "legendas.ico")

# ---------------------------------------------------------------- instalador
$Stage = "inno setup"
$iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe") |
    Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 não encontrado (choco install innosetup)" }
$size = [math]::Round(((Get-ChildItem $App -Recurse | Measure-Object Length -Sum).Sum / 1MB))
Write-Host "Programa montado: $size MB"
& $iscc /Q "/DAppVersion=$Version" "/DBuildDir=$Build" (Join-Path $PSScriptRoot "legendas.iss")
if ($LASTEXITCODE) { throw "falha ao gerar o instalador" }
Get-ChildItem (Join-Path $Build "Output")
