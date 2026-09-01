#!/bin/sh

# Confuser Obfuser installer for macOS and Linux.
set -eu

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

install_macos_tools() {
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
    if ! have python3; then
        brew install python@3.14
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
    have python3 || missing="$missing python3"
    have clang || missing="$missing clang"
    have go || missing="$missing go"
    [ -z "$missing" ] && return

    if have apt-get; then
        sudo apt-get update
        sudo apt-get install -y python3 python3-venv python3-pip clang golang-go
    elif have dnf; then
        sudo dnf install -y python3 python3-pip clang golang
    elif have pacman; then
        sudo pacman -Sy --needed python python-pip clang go
    else
        say "Hata: Eksik araçlar:$missing"
        say "Desteklenen bir paket yöneticisi bulunamadı (apt, dnf veya pacman)."
        exit 1
    fi
}

case "$OS_NAME" in
    Darwin) install_macos_tools ;;
    Linux) install_linux_tools ;;
    *)
        say "Hata: install.sh yalnızca macOS ve Linux'u destekliyor."
        exit 1
        ;;
esac

for required_tool in python3 clang go; do
    if ! have "$required_tool"; then
        say "Hata: $required_tool kurulumdan sonra bulunamadı."
        exit 1
    fi
done

say "İzole uygulama ortamı hazırlanıyor..."
mkdir -p "$INSTALL_ROOT" "$USER_BIN"
python3 -m venv "$INSTALL_ROOT/venv"
"$INSTALL_ROOT/venv/bin/python" -m pip install --upgrade pip
"$INSTALL_ROOT/venv/bin/python" -m pip install --upgrade "$PROJECT_DIR"

WRAPPER="$USER_BIN/confuser-obfuser"
printf '%s\n' '#!/bin/sh' "exec \"$INSTALL_ROOT/venv/bin/confuser-obfuser\" \"\$@\"" > "$WRAPPER"
chmod 755 "$WRAPPER"

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
            mkdir -p "$(dirname "$profile_file")"
            path_line="fish_add_path \"$USER_BIN\""
            ;;
        *)
            profile_file="$HOME/.profile"
            ;;
    esac
    if [ "$shell_name" != "fish" ]; then
        path_line="export PATH=\"$USER_BIN:\$PATH\""
    fi
    if [ ! -f "$profile_file" ] || ! grep -F "$path_line" "$profile_file" >/dev/null 2>&1; then
        printf '\n%s\n' "$path_line" >> "$profile_file"
    fi
fi

CHECK_DIR=$(mktemp -d)
say "Python motoru kontrol ediliyor..."
"$WRAPPER" "$PROJECT_DIR/examples/demo.py" -o "$CHECK_DIR/demo.obf.py" --seed 42 --validate
say "C/Clang AST motoru kontrol ediliyor..."
"$WRAPPER" "$PROJECT_DIR/examples/demo.c" -o "$CHECK_DIR/demo.obf.c" --seed 42 --validate
say "Go AST motoru kontrol ediliyor..."
"$WRAPPER" "$PROJECT_DIR/examples/demo.go" -o "$CHECK_DIR/demo.obf.go" --seed 42 --validate

say ""
say "✓ Confuser Obfuser kuruldu ve üç motor doğrulandı."
if [ "$path_ready" -eq 1 ]; then
    say "Başlatmak için: confuser-obfuser"
else
    say "Yeni bir terminal açıp çalıştır: confuser-obfuser"
    say "Bu terminalde hemen kullanmak için: export PATH=\"$USER_BIN:\$PATH\""
fi
