#!/usr/bin/env bash
# Monta o CNT Legendas para Linux ou Mac (P-04): Python próprio + bibliotecas + programa + ffmpeg + modelos.
#
#   packaging/build_unix.sh linux     → build/Output/CNT_Legendas_<versão>_linux_x86_64.tar.gz e .AppImage
#   packaging/build_unix.sh mac       → build/Output/CNT_Legendas_<versão>_mac_<arquitetura>.dmg
#
# Roda no GitHub Actions (ubuntu / macos). Precisa de internet, python3, curl e jq.
# No Mac e no Linux o programa abre no navegador padrão (a janela própria e o ícone da bandeja são do Windows).
set -euo pipefail

SISTEMA=${1:?use: build_unix.sh linux|mac}
RAIZ=$(cd "$(dirname "$0")/.." && pwd)
BUILD="$RAIZ/build"; DL="$BUILD/downloads"; SAIDA="$BUILD/Output"
mkdir -p "$DL" "$SAIDA"
etapa() { echo "== $*"; ETAPA="$*"; }
trap 'echo "::error title=Montagem $SISTEMA::falhou na etapa: ${ETAPA:-início}"' ERR

VERSAO=$(python3 -c "import sys; sys.path.insert(0, '$RAIZ'); import core; print(core.__version__)")
CANAL=${CNT_CANAL:-desenvolvimento}; NUM=${CNT_BUILD:-0}
COMPLETA=$VERSAO; [ "$NUM" != "0" ] && COMPLETA="$VERSAO.$NUM"
ARQ=$(uname -m)                                   # x86_64 | arm64
case "$SISTEMA-$ARQ" in
  linux-x86_64) TRIPLA=x86_64-unknown-linux-gnu ;;
  mac-arm64)    TRIPLA=aarch64-apple-darwin ;;
  mac-x86_64)   TRIPLA=x86_64-apple-darwin ;;
  *) echo "sistema/arquitetura não suportados: $SISTEMA-$ARQ"; exit 1 ;;
esac
echo "CNT Legendas $COMPLETA ($CANAL) para $SISTEMA-$ARQ"

baixar() { [ -s "$2" ] || curl -fsSL --retry 3 -o "$2" "$1"; }
ultimo_asset() {  # repositório e expressão → endereço do arquivo na última versão publicada
  curl -fsSL ${GH_TOKEN:+-H "Authorization: Bearer $GH_TOKEN"} "https://api.github.com/repos/$1/releases/${3:-latest}" \
    | jq -r --arg re "$2" '[.assets[] | select(.name | test($re))][0].browser_download_url'
}

# ---------------------------------------------------------------- pastas
if [ "$SISTEMA" = mac ]; then
  APP="$BUILD/mac/CNT Legendas.app"; PROG="$APP/Contents/Resources/programa"
else
  APP="$BUILD/linux/CNT Legendas"; PROG="$APP"
fi
rm -rf "$BUILD/$SISTEMA"; mkdir -p "$PROG/bin" "$PROG/models"

# ---------------------------------------------------------------- Python próprio (relocável, com tkinter)
etapa "python"
URL=$(ultimo_asset astral-sh/python-build-standalone "^cpython-3\\.12\\.[0-9]+\\+[0-9]+-$TRIPLA-install_only\\.tar\\.gz$")
[ -n "$URL" ] && [ "$URL" != null ] || { echo "não achei o Python 3.12 para $TRIPLA"; exit 1; }
baixar "$URL" "$DL/python-$TRIPLA.tar.gz"
tar -xzf "$DL/python-$TRIPLA.tar.gz" -C "$PROG"          # cria $PROG/python
PY="$PROG/python/bin/python3"
"$PY" -c "import sys, tkinter; print('Python', sys.version.split()[0])"

# ---------------------------------------------------------------- bibliotecas
etapa "bibliotecas"
PIP=("$PY" -m pip install --disable-pip-version-check --no-warn-script-location -q)
if [ "$SISTEMA" = linux ]; then "${PIP[@]}" torch --index-url https://download.pytorch.org/whl/cpu; else "${PIP[@]}" torch; fi
"${PIP[@]}" -r "$RAIZ/requirements.txt" -r "$RAIZ/requirements-align.txt" -r "$RAIZ/requirements-whisper.txt"
[ "$SISTEMA" = linux ] && "${PIP[@]}" -r "$RAIZ/requirements-gpu.txt"
"${PIP[@]}" --no-deps faster-whisper==1.2.1
find "$PROG/python" -name "__pycache__" -type d -prune -exec rm -rf {} +
rm -rf "$PROG"/python/lib/python3.12/site-packages/torch/{include,test} 2>/dev/null || true

# ---------------------------------------------------------------- programa
etapa "código"
cp -R "$RAIZ/core" "$RAIZ/app" "$PROG/"; cp "$RAIZ/cntboot.py" "$PROG/"
find "$PROG/core" "$PROG/app" -name "__pycache__" -type d -prune -exec rm -rf {} +
printf '{"canal": "%s", "build": %s}' "$CANAL" "$NUM" > "$PROG/core/canal.json"
"$PY" -m compileall -q -f "$PROG/core" "$PROG/app" >/dev/null

# ---------------------------------------------------------------- modelos (os mesmos do Windows)
etapa "modelos"
baixar "https://raw.githubusercontent.com/snakers4/silero-vad/v6.2.3/src/silero_vad/data/silero_vad.onnx" "$DL/silero_vad-6.2.3.onnx"
cp "$DL/silero_vad-6.2.3.onnx" "$PROG/models/silero_vad.onnx"
baixar "https://github.com/TRvlvr/model_repo/releases/download/all_public_uvr_models/UVR-MDX-NET-Voc_FT.onnx" "$DL/UVR-MDX-NET-Voc_FT.onnx"
cp "$DL/UVR-MDX-NET-Voc_FT.onnx" "$PROG/models/"

# ---------------------------------------------------------------- ffmpeg (estático)
etapa "ffmpeg"
if [ "$SISTEMA" = linux ]; then
  URL=$(ultimo_asset BtbN/FFmpeg-Builds "^ffmpeg-master-latest-linux64-gpl\\.tar\\.xz$")
  baixar "$URL" "$DL/ffmpeg-linux.tar.xz"
  rm -rf "$DL/ffmpeg-linux"; mkdir -p "$DL/ffmpeg-linux"; tar -xJf "$DL/ffmpeg-linux.tar.xz" -C "$DL/ffmpeg-linux"
  find "$DL/ffmpeg-linux" -type f \( -name ffmpeg -o -name ffprobe \) -path "*/bin/*" -exec cp {} "$PROG/bin/" \;
else
  A=$([ "$ARQ" = arm64 ] && echo arm64 || echo x64)
  for b in ffmpeg ffprobe; do
    URL=$(ultimo_asset eugeneware/ffmpeg-static "^$b-darwin-$A(\\.gz)?$")
    baixar "$URL" "$DL/$b-darwin-$A.dl"
    if gzip -t "$DL/$b-darwin-$A.dl" 2>/dev/null; then gunzip -c "$DL/$b-darwin-$A.dl" > "$PROG/bin/$b"; else cp "$DL/$b-darwin-$A.dl" "$PROG/bin/$b"; fi
  done
fi
chmod +x "$PROG/bin/ffmpeg" "$PROG/bin/ffprobe"
"$PROG/bin/ffprobe" -version | head -1

# ---------------------------------------------------------------- partida
etapa "partida"
cat > "$PROG/cnt-legendas" <<'EOS'
#!/bin/sh
# Abre o CNT Legendas (no navegador padrão). O programa fica nesta pasta; os dados ficam na pasta do usuário.
DIR=$(cd "$(dirname "$0")" && pwd -P)
export CNT_INSTALL_ROOT="$DIR"
cd "$DIR" && exec "$DIR/python/bin/python3" -m cntboot "$@"
EOS
chmod +x "$PROG/cnt-legendas"
"$PY" -m pip install -q pillow >/dev/null 2>&1 || true
"$PY" - "$RAIZ/app/static/icon.png" "$BUILD/icone-512.png" <<'EOS'
import sys
from PIL import Image
Image.open(sys.argv[1]).convert("RGBA").resize((512, 512), Image.LANCZOS).save(sys.argv[2])
EOS

# ---------------------------------------------------------------- empacotar
etapa "pacote"
if [ "$SISTEMA" = linux ]; then
  cp "$BUILD/icone-512.png" "$APP/cnt-legendas.png"
  cat > "$APP/cnt-legendas.desktop" <<EOS
[Desktop Entry]
Type=Application
Name=CNT Legendas
Comment=Legendagem, tradução e sincronia
Exec=cnt-legendas
Icon=cnt-legendas
Categories=AudioVideo;Video;
Terminal=false
EOS
  cat > "$APP/INSTALAR.txt" <<'EOS'
CNT Legendas para Linux

1. Extraia esta pasta onde quiser (por exemplo, ~/Aplicativos/CNT Legendas).
2. Abra com ./cnt-legendas (ele abre no navegador padrão).
3. Opcional: copie cnt-legendas.desktop para ~/.local/share/applications e troque Exec= pelo caminho completo.
EOS
  tar -C "$BUILD/linux" -czf "$SAIDA/CNT_Legendas_${COMPLETA}_linux_x86_64.tar.gz" "CNT Legendas"
  # AppImage (um arquivo só, dois cliques)
  AI="$BUILD/linux/AppDir"; rm -rf "$AI"; mkdir -p "$AI/usr"
  cp -R "$APP" "$AI/usr/cnt-legendas"
  cp "$APP/cnt-legendas.desktop" "$AI/"; cp "$BUILD/icone-512.png" "$AI/cnt-legendas.png"
  printf '#!/bin/sh\nHERE=$(dirname "$(readlink -f "$0")")\nexec "$HERE/usr/cnt-legendas/cnt-legendas" "$@"\n' > "$AI/AppRun"; chmod +x "$AI/AppRun"
  URL=$(ultimo_asset AppImage/appimagetool "^appimagetool-x86_64\\.AppImage$" tags/continuous)
  baixar "$URL" "$DL/appimagetool"; chmod +x "$DL/appimagetool"
  ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$DL/appimagetool" -n "$AI" "$SAIDA/CNT_Legendas_${COMPLETA}_linux_x86_64.AppImage"
else
  mkdir -p "$APP/Contents/MacOS"
  cat > "$APP/Contents/MacOS/CNT Legendas" <<'EOS'
#!/bin/sh
DIR=$(cd "$(dirname "$0")/../Resources/programa" && pwd -P)
exec "$DIR/cnt-legendas" "$@"
EOS
  chmod +x "$APP/Contents/MacOS/CNT Legendas"
  cat > "$APP/Contents/Info.plist" <<EOS
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>CNT Legendas</string>
  <key>CFBundleDisplayName</key><string>CNT Legendas</string>
  <key>CFBundleIdentifier</key><string>br.com.cntoficial.legendas</string>
  <key>CFBundleVersion</key><string>$COMPLETA</string>
  <key>CFBundleShortVersionString</key><string>$VERSAO</string>
  <key>CFBundleExecutable</key><string>CNT Legendas</string>
  <key>CFBundleIconFile</key><string>icone</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
  <key>NSHighResolutionCapable</key><true/>
</dict></plist>
EOS
  ICONSET="$BUILD/icone.iconset"; rm -rf "$ICONSET"; mkdir -p "$ICONSET"
  for s in 16 32 64 128 256 512; do sips -z $s $s "$BUILD/icone-512.png" --out "$ICONSET/icon_${s}x${s}.png" >/dev/null; done
  iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/icone.icns"
  # assinatura local (sem conta de desenvolvedor: na 1ª vez o Mac pede "Abrir" pelo botão direito)
  codesign --force --deep -s - "$APP" || true
  DMG="$BUILD/dmg"; rm -rf "$DMG"; mkdir -p "$DMG"; cp -R "$APP" "$DMG/"; ln -s /Applications "$DMG/Aplicativos"
  # o hdiutil às vezes falha com "Resource busy" nas máquinas do CI: tenta de novo
  for tentativa in 1 2 3 4; do
    hdiutil create -volname "CNT Legendas" -srcfolder "$DMG" -ov -format UDZO "$SAIDA/CNT_Legendas_${COMPLETA}_mac_${ARQ}.dmg" >/dev/null && break
    [ "$tentativa" = 4 ] && false
    echo "hdiutil ocupado; tentando de novo ($tentativa)"; sleep $((tentativa * 10))
  done
fi
ls -la "$SAIDA"
echo "PROG=$PROG" >> "${GITHUB_ENV:-/dev/null}"
