#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# buildcrew-dash Installer
# https://github.com/joshuaccarroll/buildcrew-dash
# ═══════════════════════════════════════════════════════════════════════════════
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/joshuaccarroll/buildcrew-dash/main/install.sh | bash
#
# Or manually:
#   git clone https://github.com/joshuaccarroll/buildcrew-dash.git
#   cd buildcrew-dash && ./install.sh
#
# ═══════════════════════════════════════════════════════════════════════════════

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# Configuration
REPO="joshuaccarroll/buildcrew-dash"
INSTALL_DIR="$HOME/.buildcrew-dash"
BIN_DIR="$HOME/.local/bin"
PYTHON=""

# Check if this is an upgrade
UPGRADE_MODE=false
if [[ "${1:-}" == "--upgrade" ]]; then
    UPGRADE_MODE=true
fi

print_logo() {
    echo -e "${CYAN}"
    echo "  buildcrew-dash"
    echo "  ──────────────────────────────────────────────────"
    echo "  Terminal Dashboard for BuildCrew"
    echo -e "${NC}"
}

error() {
    echo -e "${RED}Error:${NC} $1" >&2
    exit 1
}

success() {
    echo -e "${GREEN}✓${NC} $1"
}

info() {
    echo -e "${CYAN}→${NC} $1"
}

warning() {
    echo -e "${YELLOW}!${NC} $1"
}

# Download a file using curl or wget
download() {
    local url="$1"
    local dest="$2"

    if command -v curl &> /dev/null; then
        curl -fsSL "$url" -o "$dest"
    elif command -v wget &> /dev/null; then
        wget -qO "$dest" "$url"
    else
        error "Neither curl nor wget found"
    fi
}

# Find a Python binary >= 3.11; sets global PYTHON and prints its path
find_python() {
    local names=("python3" "python3.13" "python3.12" "python3.11")
    local brew_prefixes=("/opt/homebrew/bin" "/usr/local/bin")
    local resolved version major minor

    for name in "${names[@]}"; do
        # Try name as found in PATH
        if resolved=$(command -v "$name" 2>/dev/null); then
            version=$("$resolved" --version 2>&1 | awk '{print $2}') || true
            major=$(echo "$version" | cut -d. -f1)
            minor=$(echo "$version" | cut -d. -f2)
            if [[ -n "$major" ]] && (( major > 3 || ( major == 3 && minor >= 11 ) )); then
                echo "$resolved"
                return 0
            fi
        fi

        # Try Homebrew prefixes (macOS: python3 may be old Xcode CLT version)
        for prefix in "${brew_prefixes[@]}"; do
            resolved="$prefix/$name"
            if [[ -x "$resolved" ]]; then
                version=$("$resolved" --version 2>&1 | awk '{print $2}') || true
                major=$(echo "$version" | cut -d. -f1)
                minor=$(echo "$version" | cut -d. -f2)
                if [[ -n "$major" ]] && (( major > 3 || ( major == 3 && minor >= 11 ) )); then
                    echo "$resolved"
                    return 0
                fi
            fi
        done
    done

    # Fallback: try uv python find (covers uv-managed installations)
    if command -v uv &> /dev/null; then
        resolved=$(uv python find ">=3.11" 2>/dev/null) || true
        if [[ -n "$resolved" && -x "$resolved" ]]; then
            echo "$resolved"
            return 0
        fi
    fi

    return 1
}

check_dependencies() {
    # Check for curl or wget (needed for remote install)
    if ! command -v curl &> /dev/null && ! command -v wget &> /dev/null; then
        error "curl or wget is required but not found"
    fi

    # Find a suitable Python
    info "Looking for Python 3.11+..."
    if ! PYTHON=$(find_python); then
        error "Python 3.11+ not found. Install with: brew install python@3.12"
    fi
    local py_version
    py_version=$("$PYTHON" --version 2>&1 | awk '{print $2}')
    success "Found Python $py_version at $PYTHON"

    # Verify venv module is available
    if ! "$PYTHON" -m venv --help &> /dev/null; then
        error "Python venv module not found. On Debian/Ubuntu: sudo apt install python3-venv"
    fi

    # Verify ensurepip is present (guards against broken Debian/Ubuntu venvs)
    if ! "$PYTHON" -c "import ensurepip" &> /dev/null; then
        error "ensurepip not available. On Debian/Ubuntu: sudo apt install python3-venv"
    fi
}

# Copy the source files we need into INSTALL_DIR
copy_source() {
    local source_dir="$1"

    # Remove stale egg-info before copying to prevent setuptools serving stale metadata
    rm -rf "$INSTALL_DIR/src/buildcrew_dash.egg-info" 2>/dev/null || true

    mkdir -p "$INSTALL_DIR"
    cp -r "$source_dir/src" "$INSTALL_DIR/"
    cp "$source_dir/pyproject.toml" "$INSTALL_DIR/"
    cp "$source_dir/README.md" "$INSTALL_DIR/" 2>/dev/null || true
}

install_local() {
    local source_dir="$1"
    info "Installing from local directory..."
    copy_source "$source_dir"
}

install_remote() {
    local tmp_dir
    tmp_dir=$(mktemp -d)
    trap "rm -rf $tmp_dir" EXIT

    info "Downloading buildcrew-dash from GitHub..."
    local archive_url="https://github.com/$REPO/archive/refs/heads/main.tar.gz"
    download "$archive_url" "$tmp_dir/buildcrew-dash.tar.gz"

    info "Extracting..."
    tar -xzf "$tmp_dir/buildcrew-dash.tar.gz" -C "$tmp_dir"

    local extracted_dir
    extracted_dir=$(find "$tmp_dir" -maxdepth 1 -type d -name "buildcrew-dash*" | head -1)
    if [[ -z "$extracted_dir" ]]; then
        error "Failed to extract archive"
    fi

    copy_source "$extracted_dir"
}

# Create venv if needed, or reuse existing healthy one
setup_venv() {
    local venv_python="$INSTALL_DIR/.venv/bin/python"

    if [[ -x "$venv_python" ]] && "$venv_python" --version &> /dev/null; then
        info "Existing venv detected, reusing..."
    else
        info "Creating Python virtual environment..."
        if ! "$PYTHON" -m venv "$INSTALL_DIR/.venv"; then
            error "Failed to create venv. On Debian/Ubuntu: sudo apt install python3-venv"
        fi

        # Bootstrap pip if the venv was created without it
        if [[ ! -x "$INSTALL_DIR/.venv/bin/pip" ]]; then
            info "Bootstrapping pip..."
            "$INSTALL_DIR/.venv/bin/python" -m ensurepip || error "Failed to bootstrap pip in venv"
        fi
    fi
}

main() {
    if [[ "$UPGRADE_MODE" != "true" ]]; then
        print_logo
        echo -e "${BOLD}buildcrew-dash Installer${NC}"
        echo ""
    fi

    info "Checking dependencies..."
    check_dependencies
    success "Dependencies OK"

    # Detect install source.
    # When piped via `curl | bash`, BASH_SOURCE[0] is empty or /dev/stdin.
    # In that case we always download from GitHub.
    local script_dir=""
    if [[ -n "${BASH_SOURCE[0]:-}" && "${BASH_SOURCE[0]}" != "/dev/stdin" ]]; then
        script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    fi

    if [[ "$UPGRADE_MODE" == "true" ]]; then
        info "Upgrading buildcrew-dash..."
        # Remove stale artifacts before copying fresh source
        rm -rf "$INSTALL_DIR/src/buildcrew_dash.egg-info" 2>/dev/null || true
        find "$INSTALL_DIR/src" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

        if [[ -n "$script_dir" && -d "$script_dir/src/buildcrew_dash" ]]; then
            install_local "$script_dir"
        else
            install_remote
        fi
    elif [[ -n "$script_dir" && -d "$script_dir/src/buildcrew_dash" ]]; then
        install_local "$script_dir"
    else
        install_remote
    fi

    success "Source files installed to $INSTALL_DIR"

    # Set up venv (create fresh or reuse existing healthy one)
    setup_venv

    # Upgrade pip — best-effort, do not abort if it fails
    info "Upgrading pip..."
    "$INSTALL_DIR/.venv/bin/pip" install --upgrade pip --quiet || warning "pip upgrade failed, continuing..."

    # Install the package (textual + deps land in the isolated venv)
    info "Installing buildcrew-dash and dependencies..."
    if ! "$INSTALL_DIR/.venv/bin/pip" install "$INSTALL_DIR/" --quiet; then
        error "pip install failed. Check network or run manually: $INSTALL_DIR/.venv/bin/pip install $INSTALL_DIR/"
    fi
    success "Package installed"

    # Symlink the console_scripts entry point into ~/.local/bin
    info "Setting up PATH..."
    mkdir -p "$BIN_DIR"
    ln -sf "$INSTALL_DIR/.venv/bin/buildcrew-dash" "$BIN_DIR/buildcrew-dash"
    success "Symlink created at $BIN_DIR/buildcrew-dash"

    # Warn if ~/.local/bin is not in PATH
    if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
        warning "$BIN_DIR is not in your PATH"
        echo ""
        echo "Add this to your shell config (~/.bashrc, ~/.zshrc, etc.):"
        echo -e "  ${CYAN}export PATH=\"\$HOME/.local/bin:\$PATH\"${NC}"
        echo ""
    fi

    # Verify
    if [[ -x "$BIN_DIR/buildcrew-dash" ]]; then
        success "Installation verified"
    else
        warning "Installation complete, but $BIN_DIR/buildcrew-dash not found or not executable"
    fi

    echo ""
    echo -e "${GREEN}${BOLD}buildcrew-dash installed successfully!${NC}"
    echo ""
    echo -e "${BOLD}Getting started:${NC}"
    echo -e "  ${CYAN}buildcrew-dash${NC}  — start the dashboard"
    echo -e "  (auto-discovers running buildcrew processes)"
    echo ""
    echo -e "${BOLD}To upgrade:${NC}"
    echo -e "  curl -fsSL https://raw.githubusercontent.com/joshuaccarroll/buildcrew-dash/main/install.sh | bash -s -- --upgrade"
    echo ""
    echo -e "${BOLD}Documentation:${NC} https://github.com/joshuaccarroll/buildcrew-dash"
    echo ""
}

main "$@"
