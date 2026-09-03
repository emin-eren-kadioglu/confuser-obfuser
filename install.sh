#!/bin/sh

# Confuser Obfuser installer for macOS and Linux.
set -eu

from_github=0
install_tools=0
for option in "$@"; do
    case "$option" in
        --from-github) from_github=1 ;;
        --install-tools) install_tools=1 ;;
        *) printf 'Bilinmeyen seçenek: %s\n' "$option" >&2; exit 1 ;;
    esac
done

if [ "$from_github" -eq 1 ]; then
    source_tmp=$(mktemp -d "${TMPDIR:-/tmp}/confuser-source.XXXXXX")
    trap 'rm -rf -- "$source_tmp"' 0
    curl -fsSL https://github.com/emin-eren-kadioglu/confuser-obfuser/archive/refs/heads/main.tar.gz -o "$source_tmp/source.tar.gz"
    mkdir "$source_tmp/source"
    tar -xzf "$source_tmp/source.tar.gz" -C "$source_tmp/source" --strip-components=1
    if [ "$install_tools" -eq 1 ]; then
        sh "$source_tmp/source/install.sh" --install-tools
    else
        sh "$source_tmp/source/install.sh"
    fi
    exit 0
fi

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
INSTALL_ROOT=${CONFUSER_INSTALL_ROOT:-"$HOME/.local/share/confuser-obfuser"}
USER_BIN=${CONFUSER_USER_BIN:-"$HOME/.local/bin"}
OS_NAME=$(uname -s)

say() {
    printf '%s\n' "$1"
}

have() {
    command -v "$1" >/dev/null 2>&1
}

python_ready() {
    have python3 && python3 -c 'import sys; assert sys.version_info >= (3, 10)' >/dev/null 2>&1
}

as_root() {
    if [ "$(id -u)" -eq 0 ]; then
        "$@"
    else
        sudo "$@"
    fi
}

install_macos_tools() {
    if python_ready && have clang && have go; then
        return
    fi
    if ! have brew; then
        say "Homebrew bulunamadı; resmi Homebrew kurucusu başlatılıyor..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        if [ -x /opt/homebrew/bin/brew ]; then
            eval "$(/opt/homebrew/bin/brew shellenv)"
        elif [ -x /usr/local/bin/brew ]; then
            eval "$(/usr/local/bin/brew shellenv)"
        fi
    fi
    if ! have brew; then
        say "Hata: Homebrew kurulamadı."
        exit 1
    fi
    if ! python_ready; then
        brew install python@3.14
        PATH="$(brew --prefix python@3.14)/libexec/bin:$PATH"
        export PATH
    fi
    if ! have go; then
        brew install go
    fi
    if ! have clang; then
        say "Apple Command Line Tools kurulumu açılıyor..."
        xcode-select --install || true
        say "Kurulum tamamlandıktan sonra install.sh dosyasını yeniden çalıştır."
        exit 1
    fi
}

install_linux_tools() {
    missing=""
    python_ready || missing="$missing python3"
    have clang || missing="$missing clang"
    have go || missing="$missing go"
    [ -z "$missing" ] && return

    if have apt-get; then
        set --
        python_ready || set -- "$@" python3
        have clang || set -- "$@" clang
        have go || set -- "$@" golang-go
        as_root apt-get update
        as_root apt-get install -y "$@"
    elif have dnf; then
        set --
        python_ready || set -- "$@" python3
        have clang || set -- "$@" clang
        have go || set -- "$@" golang
        as_root dnf install -y "$@"
    elif have pacman; then
        set --
        python_ready || set -- "$@" python
        have clang || set -- "$@" clang
        have go || set -- "$@" go
        as_root pacman -S --needed --noconfirm "$@"
    else
        say "Hata: Eksik araçlar:$missing"
        say "Desteklenen bir paket yöneticisi bulunamadı (apt, dnf veya pacman)."
        exit 1
    fi
}

case "$OS_NAME" in
    Darwin|Linux) ;;
    *)
        say "Hata: install.sh yalnızca macOS ve Linux'u destekliyor."
        exit 1
        ;;
esac

if [ "$install_tools" -eq 1 ]; then
    say "İsteğe bağlı Python/Clang/Go kurulumu: bağımlılıklar yüzlerce MB veya birkaç GB indirebilir."
    say "Paket yöneticisi/Apple geliştirici araçları da kurulabilir. Yönetici onayı gerekebilir."
    say "Devam etmek için EVET yazın (diğer yanıtlar indirmeyi iptal eder):"
    answer=""
    if ! (test -r /dev/tty) 2>/dev/null || ! { IFS= read -r answer </dev/tty; } 2>/dev/null; then
        say "Onay alınamadı; araç indirilmedi. Etkileşimli terminalden tekrar deneyin."
        exit 1
    fi
    [ "$answer" = "EVET" ] || { say "İptal edildi; araç indirilmedi."; exit 1; }
    case "$OS_NAME" in
        Darwin) install_macos_tools ;;
        Linux) install_linux_tools ;;
    esac
fi

if ! python_ready; then
    say "Hata: Python 3.10+ gerekiyor. Araç indirilmedi. Python kurun veya --install-tools ile onaylı kurulumu seçin."
    exit 1
fi

say "Uygulama hazırlanıyor (pip veya ek Python paketi indirilmez)..."
mkdir -p "$INSTALL_ROOT" "$USER_BIN"
PYTHON_EXE=$(python3 -c 'import sys; print(sys.executable)')
RELEASE_DIR=$(mktemp -d "$INSTALL_ROOT/app.XXXXXX")
"$PYTHON_EXE" - "$PROJECT_DIR" "$RELEASE_DIR" <<'PY'
import shutil
import sys
from pathlib import Path
source, target = map(Path, sys.argv[1:])
shutil.copytree(source / "obfuscator", target / "obfuscator",
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
shutil.copy2(source / "confuser_obfuser.py", target)
shutil.copy2(source / "LICENSE", target)
PY

CHECK_DIR=$(mktemp -d "${TMPDIR:-/tmp}/confuser-check.XXXXXX")
trap 'rm -rf -- "$CHECK_DIR"' 0
say "Python motoru kontrol ediliyor..."
"$PYTHON_EXE" "$RELEASE_DIR/confuser_obfuser.py" "$PROJECT_DIR/examples/demo.py" -o "$CHECK_DIR/demo.obf.py" --seed 42 --validate
# Optional tools are probed, never downloaded. Their failure must not prevent Python use.
export GOTOOLCHAIN=local GOPROXY=off GOSUMDB=off
for language in c go; do
    tool=clang
    [ "$language" != go ] || tool=go
    if have "$tool"; then
        if "$PYTHON_EXE" "$RELEASE_DIR/confuser_obfuser.py" "$PROJECT_DIR/examples/demo.$language" -o "$CHECK_DIR/demo.obf.$language" --seed 42 --validate --timeout 60; then
            say "$language motoru doğrulandı."
        else
            say "Uyarı: $language motor kontrolü geçmedi; mevcut araçları/SDK'yı kontrol edin. Otomatik indirme yapılmadı."
        fi
    else
        say "Uyarı: $tool bulunamadı; $language kontrolü atlandı. Python kullanılabilir; araç kurulmadı."
    fi
done

"$PYTHON_EXE" - "$PYTHON_EXE" "$RELEASE_DIR" "$USER_BIN" <<'PY'
import os
import shlex
import sys
import tempfile
from pathlib import Path
python, release, user_bin = sys.argv[1:]
command = shlex.join([python, str(Path(release) / "confuser_obfuser.py")])
for name in ("confuser", "confuser-obfuser"):
    with tempfile.NamedTemporaryFile(mode="w", dir=user_bin, delete=False, encoding="utf-8") as stream:
        stream.write('#!/bin/sh\nexec ' + command + ' "$@"\n')
    os.chmod(stream.name, 0o755)
    os.replace(stream.name, Path(user_bin) / name)
PY
WRAPPER="$USER_BIN/confuser"

case ":$PATH:" in
    *":$USER_BIN:"*) path_ready=1 ;;
    *) path_ready=0 ;;
esac

if [ "$path_ready" -eq 0 ]; then
    shell_name=$(basename "${SHELL:-sh}")
    case "$shell_name" in
        zsh)
            if [ "$OS_NAME" = "Darwin" ]; then
                profile_file="$HOME/.zprofile"
            else
                profile_file="$HOME/.zshrc"
            fi
            ;;
        bash)
            if [ "$OS_NAME" = "Darwin" ]; then
                profile_file="$HOME/.bash_profile"
            else
                profile_file="$HOME/.bashrc"
            fi
            ;;
        fish)
            profile_file="$HOME/.config/fish/config.fish"
            ;;
        *)
            profile_file="$HOME/.profile"
            ;;
    esac
    "$PYTHON_EXE" - "$profile_file" "$USER_BIN" "$shell_name" <<'PY'
import shlex
import sys
from pathlib import Path
profile, directory, shell = sys.argv[1:]
quoted = shlex.quote(directory)
line = "fish_add_path " + quoted if shell == "fish" else "export PATH=" + quoted + ':"$PATH"'
path = Path(profile)
path.parent.mkdir(parents=True, exist_ok=True)
if not path.exists() or line not in path.read_text(encoding="utf-8").splitlines():
    with path.open("a", encoding="utf-8") as stream:
        stream.write("\n" + line + "\n")
PY
fi

say ""
say "✓ Confuser Obfuser kuruldu; Python doğrulandı. C/Go durumu yukarıda ayrı gösterildi."
if [ "$path_ready" -eq 1 ]; then
    say "Başlatmak için: confuser"
else
    say "Yeni bir terminal açıp çalıştır: confuser"
    say "Bu terminalde hemen kullanmak için: export PATH=\"$USER_BIN:\$PATH\""
fi
