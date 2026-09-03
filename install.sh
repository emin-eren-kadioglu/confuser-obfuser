#!/bin/sh

# Confuser Obfuser installer for macOS and Linux.
set -eu

from_github=0
skip_tools=0
release_ref=${CONFUSER_RELEASE_REF:-v0.3.0}
for option in "$@"; do
    case "$option" in
        --from-github) from_github=1 ;;
        --install-tools) : ;; # Compatibility: prompts are now enabled by default.
        --no-tools) skip_tools=1 ;;
        *) printf 'Error: unknown option: %s\n' "$option" >&2; exit 1 ;;
    esac
done

if [ "$from_github" -eq 1 ]; then
    source_tmp=$(mktemp -d "${TMPDIR:-/tmp}/confuser-source.XXXXXX")
    trap 'rm -rf -- "$source_tmp"' 0
    case "$release_ref" in
        main) archive_path=refs/heads/main ;;
        *) archive_path=refs/tags/$release_ref ;;
    esac
    curl -fsSL "https://github.com/emin-eren-kadioglu/confuser-obfuser/archive/$archive_path.tar.gz" -o "$source_tmp/source.tar.gz"
    mkdir "$source_tmp/source"
    tar -xzf "$source_tmp/source.tar.gz" -C "$source_tmp/source" --strip-components=1
    if [ "$skip_tools" -eq 1 ]; then
        sh "$source_tmp/source/install.sh" --no-tools
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

confirm_install() {
    say "$1"
    say "$2"
    if [ "$skip_tools" -eq 1 ] || [ "${CI:-}" = "true" ]; then
        say "Skipped: tool installation is disabled. No download started."
        return 1
    fi
    # stdin may contain the installer itself (curl | sh), so use the terminal.
    answer=""
    if ! { printf 'Install %s? [y/N]: ' "$3" >/dev/tty; } 2>/dev/null ||
       ! { IFS= read -r answer </dev/tty; } 2>/dev/null; then
        say "Skipped: no interactive confirmation available. No download started."
        return 1
    fi
    case "$answer" in
        y|Y|yes|YES|Yes) return 0 ;;
        *) say "Skipped: $3 was not approved. No download started."; return 1 ;;
    esac
}

ensure_brew() {
    if ! have brew; then
        confirm_install "Homebrew is not installed." \
            "Homebrew and its developer-tool dependencies may download several GB and require administrator access." "Homebrew" || return 1
        brew_script=$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh) || return 1
        /bin/bash -c "$brew_script" || return 1
        if [ -x /opt/homebrew/bin/brew ]; then
            eval "$(/opt/homebrew/bin/brew shellenv)"
        elif [ -x /usr/local/bin/brew ]; then
            eval "$(/usr/local/bin/brew shellenv)"
        fi
    fi
    if ! have brew; then
        say "Warning: Homebrew could not be installed."
        return 1
    fi
}

apt_refreshed=0
install_tool() {
    # The caller must obtain consent for this one tool before entering here.
    if [ "$OS_NAME" = Darwin ]; then
        case "$1" in
            clang)
                xcode-select --install || return 1
                say "Complete the Apple Command Line Tools dialog, then run this installer again."
                return 0
                ;;
            python3)
                ensure_brew || return 1
                brew install python@3.14 || return 1
                PATH="$(brew --prefix python@3.14)/libexec/bin:$PATH"
                export PATH
                ;;
            go) ensure_brew && brew install go || return 1 ;;
        esac
    elif have apt-get; then
        package_name=$1
        [ "$1" != go ] || package_name=golang-go
        if [ "$apt_refreshed" -eq 0 ]; then
            as_root apt-get update || return 1
            apt_refreshed=1
        fi
        as_root apt-get install -y "$package_name" || return 1
    elif have dnf; then
        package_name=$1
        [ "$1" != go ] || package_name=golang
        as_root dnf install -y "$package_name" || return 1
    elif have pacman; then
        package_name=$1
        [ "$1" != python3 ] || package_name=python
        as_root pacman -S --needed --noconfirm "$package_name" || return 1
    else
        say "Warning: no supported package manager found (apt, dnf or pacman). Install $1 manually."
        return 1
    fi
}

case "$OS_NAME" in
    Darwin|Linux) ;;
    *)
        say "Error: install.sh supports only macOS and Linux."
        exit 1
        ;;
esac

if ! python_ready; then
    if confirm_install "Python 3.10+ is required but was not found." \
        "Python and dependencies may download hundreds of MB and require administrator access." "Python"; then
        install_tool python3 || say "Warning: Python installation failed."
    fi
fi

if ! python_ready; then
    say "Error: Python 3.10+ is required. Install Python, then run this installer again."
    exit 1
fi

for optional_tool in clang go; do
    if ! have "$optional_tool"; then
        download_note="This tool and dependencies may download hundreds of MB and require administrator access."
        if [ "$OS_NAME" = Darwin ] && [ "$optional_tool" = clang ]; then
            download_note="Apple Command Line Tools may download several GB and require a graphical setup dialog."
        fi
        if confirm_install "$optional_tool is not installed (optional for Python use)." "$download_note" "$optional_tool"; then
            install_tool "$optional_tool" || say "Warning: $optional_tool installation failed; Python installation will continue."
        fi
    fi
done

say "Preparing the application (no pip or additional Python packages are downloaded)..."
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
say "Checking the Python engine..."
"$PYTHON_EXE" "$RELEASE_DIR/confuser_obfuser.py" "$PROJECT_DIR/examples/demo.py" -o "$CHECK_DIR/demo.obf.py" --seed 42 --validate
# Validation never downloads tools. Optional failures must not prevent Python use.
export GOTOOLCHAIN=local GOPROXY=off GOSUMDB=off
for language in c go; do
    tool=clang
    [ "$language" != go ] || tool=go
    if have "$tool"; then
        if "$PYTHON_EXE" "$RELEASE_DIR/confuser_obfuser.py" "$PROJECT_DIR/examples/demo.$language" -o "$CHECK_DIR/demo.obf.$language" --seed 42 --validate --timeout 60; then
            say "$language engine validated."
        else
            say "Warning: $language validation failed. Check your toolchain/SDK. Python remains available."
        fi
    else
        say "Warning: $tool was not found; $language validation skipped. Python remains available."
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
say "OK - Confuser Obfuser installed; Python validated. C/Go status is shown separately above."
if [ "$path_ready" -eq 1 ]; then
    say "Run: confuser"
else
    say "Open a new terminal and run: confuser"
    say "To use it in this terminal: export PATH=\"$USER_BIN:\$PATH\""
fi
