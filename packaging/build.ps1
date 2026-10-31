# Monta o programa completo em build\CNTLegendas e gera o instalador.
#
# Resultado: build\Output\Instalador_CNT_Legendas_<versão>.exe e, do mesmo programa montado,
#            build\Output\Instalador_CNT_Dubla_<versão da Dubla>.exe (abre com `cntboot --produto dubla`).
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
# Canal e número da montagem (o CI define): "producao" no ramo main, "desenvolvimento" no dev.
# A versão completa é <versão>.<montagem> (ex.: 2.10.0.57); a atualização automática compara por ela.
$Canal = if ($env:CNT_CANAL) { $env:CNT_CANAL } else { "desenvolvimento" }
$BuildNum = if ($env:CNT_BUILD) { [int]$env:CNT_BUILD } else { 0 }
if ($Canal -notin @("producao", "desenvolvimento")) { throw "CNT_CANAL inválido: $Canal" }
$FullVersion = if ($BuildNum) { "$Version.$BuildNum" } else { $Version }
$DublaVersion = (& python -c "import sys; sys.path.insert(0, r'$Root'); import dubla; print(dubla.VERSAO)").Trim()
$DublaFull = if ($BuildNum) { "$DublaVersion.$BuildNum" } else { $DublaVersion }
Write-Host "== CNT Legendas $FullVersion ($Canal) =="

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
    -r (Join-Path $Root "requirements.txt") -r (Join-Path $Root "requirements-align.txt") `
    -r (Join-Path $Root "requirements-whisper.txt") -r (Join-Path $Root "requirements-gpu.txt")
if ($LASTEXITCODE) { throw "falha ao instalar as bibliotecas" }
& python -m pip install --disable-pip-version-check --no-warn-script-location --target $site --no-deps faster-whisper==1.2.1
if ($LASTEXITCODE) { throw "falha ao instalar o faster-whisper" }
# só um onnxruntime: o DirectML (usa a placa de vídeo); o comum, se algum pacote trouxe, sai
Get-ChildItem $site -Directory | Where-Object { $_.Name -match '^onnxruntime-[0-9].*\.dist-info$' } | ForEach-Object {
    Write-Host "::warning::onnxruntime comum também instalado ($($_.Name))" }
# limpeza: testes e caches que não servem para nada no programa instalado
Get-ChildItem $site -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
Get-ChildItem $site -Directory | Where-Object { $_.Name -in @("bin") } | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $site "torch\include") -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $site "torch\test") -Recurse -Force -ErrorAction SilentlyContinue

# ---------------------------------------------------------------- código do programa
$Stage = "código"
Copy-Item (Join-Path $Root "core") (Join-Path $App "core") -Recurse
Copy-Item (Join-Path $Root "app") (Join-Path $App "app") -Recurse
Copy-Item (Join-Path $Root "dubla") (Join-Path $App "dubla") -Recurse
Copy-Item (Join-Path $Root "cntboot.py") (Join-Path $App "cntboot.py")
Get-ChildItem $App -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
Remove-Item (Join-Path $App "core\canal.json") -ErrorAction SilentlyContinue
$canalJson = @{ canal = $Canal; build = $BuildNum } | ConvertTo-Json -Compress
[IO.File]::WriteAllText((Join-Path $App "core\canal.json"), $canalJson, (New-Object Text.UTF8Encoding $false))
& python -m compileall -q -f (Join-Path $App "core") (Join-Path $App "app") (Join-Path $App "dubla") | Out-Null
# conferência dos arquivos (o lançador avisa se a cópia estiver alterada ou faltando arquivo)
& python (Join-Path $PSScriptRoot "manifesto.py") $App
if ($LASTEXITCODE) { throw "falha ao gerar o manifesto dos arquivos" }

# pacote de atualização (patch): app\ e core\, para o programa já instalado baixar e aplicar
New-Item -ItemType Directory -Force -Path (Join-Path $Build "Output") | Out-Null
$patch = Join-Path $Build "Output\Atualizacao_CNT_Legendas_$FullVersion.zip"
Remove-Item $patch -ErrorAction SilentlyContinue
# + lib\ com as bibliotecas em Python puro (packaging\bibliotecas-no-pacote.txt)
$PatchRoot = Join-Path $Build "pacote"
Remove-Item $PatchRoot -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $PatchRoot | Out-Null
Copy-Item (Join-Path $App "app") (Join-Path $PatchRoot "app") -Recurse
Copy-Item (Join-Path $App "core") (Join-Path $PatchRoot "core") -Recurse
Copy-Item (Join-Path $App "dubla") (Join-Path $PatchRoot "dubla") -Recurse
# o pacote não leva canal: é o mesmo arquivo no dev e na produção (o canal vem do programa instalado)
[IO.File]::WriteAllText((Join-Path $PatchRoot "core\canal.json"), (@{ build = $BuildNum } | ConvertTo-Json -Compress), (New-Object Text.UTF8Encoding $false))
& python -m pip install --disable-pip-version-check --no-warn-script-location --no-deps --target (Join-Path $PatchRoot "lib") `
    -r (Join-Path $PSScriptRoot "bibliotecas-no-pacote.txt")
if ($LASTEXITCODE) { throw "falha ao instalar as bibliotecas do pacote" }
Get-ChildItem (Join-Path $PatchRoot "lib") -Directory | Where-Object { $_.Name -eq "bin" } | Remove-Item -Recurse -Force
# corretor: só os dicionários de português, espanhol e inglês (os outros só aumentam o pacote)
$dic = Join-Path $PatchRoot "lib\spellchecker\resources"
if (Test-Path $dic) { Get-ChildItem $dic -File | Where-Object { $_.Name -notmatch '^(pt|es|en)\.json\.gz$' } | Remove-Item -Force }
# (zip pelo Python: nomes com "/", que funcionam em qualquer descompactador)
& python -c "import sys, zipfile, pathlib; r = pathlib.Path(sys.argv[1]); z = zipfile.ZipFile(sys.argv[2], 'w', zipfile.ZIP_DEFLATED, compresslevel=9); [z.write(f, f.relative_to(r).as_posix()) for d in ('app', 'core', 'dubla', 'lib') for f in sorted((r / d).rglob('*')) if f.is_file()]; z.close()" $PatchRoot $patch
if ($LASTEXITCODE) { throw "falha ao gerar o pacote de atualização" }
Write-Host "Pacote de atualização: $([math]::Round((Get-Item $patch).Length / 1MB, 1)) MB"
# a Dubla usa o mesmo pacote (com dubla\), com o número de versão dela
Copy-Item $patch (Join-Path $Build "Output\Atualizacao_CNT_Dubla_$DublaFull.zip") -Force

# ---------------------------------------------------------------- detector de voz
$Stage = "detector de voz"
$VadUrl = "https://raw.githubusercontent.com/snakers4/silero-vad/v6.2.3/src/silero_vad/data/silero_vad.onnx"
New-Item -ItemType Directory -Force -Path (Join-Path $App "models") | Out-Null
Get-File $VadUrl (Join-Path $Dl "silero_vad-6.2.3.onnx")
Copy-Item (Join-Path $Dl "silero_vad-6.2.3.onnx") (Join-Path $App "models\silero_vad.onnx")
if ((Get-Item (Join-Path $App "models\silero_vad.onnx")).Length -lt 1MB) { throw "modelo do detector de voz incompleto" }
# separador de voz (MDX-Net, projeto Ultimate Vocal Remover)
$SepUrl = "https://github.com/TRvlvr/model_repo/releases/download/all_public_uvr_models/UVR-MDX-NET-Voc_FT.onnx"
Get-File $SepUrl (Join-Path $Dl "UVR-MDX-NET-Voc_FT.onnx")
Copy-Item (Join-Path $Dl "UVR-MDX-NET-Voc_FT.onnx") (Join-Path $App "models\UVR-MDX-NET-Voc_FT.onnx")
if ((Get-Item (Join-Path $App "models\UVR-MDX-NET-Voc_FT.onnx")).Length -lt 50MB) { throw "modelo do separador de voz incompleto" }

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
Copy-Item (Join-Path $App "legendas.ico") (Join-Path $App "dubla.ico")

# ---------------------------------------------------------------- instalador
$Stage = "inno setup"
$iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe") |
    Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 não encontrado (choco install innosetup)" }
$size = [math]::Round(((Get-ChildItem $App -Recurse | Measure-Object Length -Sum).Sum / 1MB))
Write-Host "Programa montado: $size MB"
& $iscc /Q "/DAppVersion=$FullVersion" "/DBuildDir=$Build" (Join-Path $PSScriptRoot "legendas.iss")
if ($LASTEXITCODE) { throw "falha ao gerar o instalador" }
$Stage = "inno setup (Dubla)"
& $iscc /Q "/DAppVersion=$DublaFull" "/DBuildDir=$Build" (Join-Path $PSScriptRoot "dubla.iss")
if ($LASTEXITCODE) { throw "falha ao gerar o instalador da Dubla" }
# produção junto (2.31): a mesma montagem, só o canal do instalador muda; fica guardada até a liberação
if ($env:CNT_TAMBEM_PRODUCAO -eq "1" -and $Canal -eq "desenvolvimento") {
    $Stage = "inno setup (produção)"
    $canalProd = @{ canal = "producao"; build = $BuildNum } | ConvertTo-Json -Compress
    [IO.File]::WriteAllText((Join-Path $App "core\canal.json"), $canalProd, (New-Object Text.UTF8Encoding $false))
    & $iscc /Q "/DAppVersion=$FullVersion" "/DBuildDir=$Build" "/O$(Join-Path $Build 'Output\producao')" (Join-Path $PSScriptRoot "legendas.iss")
    $falhou = $LASTEXITCODE
    [IO.File]::WriteAllText((Join-Path $App "core\canal.json"), $canalJson, (New-Object Text.UTF8Encoding $false))
    if ($falhou) { throw "falha ao gerar o instalador de produção" }
    Get-ChildItem (Join-Path $Build "Output\producao")
}
Get-ChildItem (Join-Path $Build "Output")
