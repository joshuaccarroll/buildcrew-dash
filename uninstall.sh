#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# buildcrew-dash Uninstaller
# ═══════════════════════════════════════════════════════════════════════════════

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

INSTALL_DIR="$HOME/.buildcrew-dash"
BIN_DIR="$HOME/.local/bin"

error()   { echo -e "${RED}Error:${NC} $1" >&2; exit 1; }
success() { echo -e "${GREEN}✓${NC} $1"; }
info()    { echo -e "${CYAN}→${NC} $1"; }
warning() { echo -e "${YELLOW}!${NC} $1"; }

main() {
    echo -e "${BOLD}buildcrew-dash Uninstaller${NC}"
    echo ""

    if [[ ! -d "$INSTALL_DIR" && ! -L "$BIN_DIR/buildcrew-dash" ]]; then
        warning "buildcrew-dash does not appear to be installed."
        exit 0
    fi

    echo "This will remove:"
    echo "  $INSTALL_DIR/"
    echo "  $BIN_DIR/buildcrew-dash"
    echo ""
    read -r -p "Continue? [y/N] " confirm
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        echo "Aborted."
        exit 0
    fi

    echo ""

    if [[ -d "$INSTALL_DIR" ]]; then
        info "Removing $INSTALL_DIR..."
        rm -rf "$INSTALL_DIR"
        success "Removed $INSTALL_DIR"
    fi

    if [[ -L "$BIN_DIR/buildcrew-dash" || -f "$BIN_DIR/buildcrew-dash" ]]; then
        info "Removing $BIN_DIR/buildcrew-dash..."
        rm -f "$BIN_DIR/buildcrew-dash"
        success "Removed $BIN_DIR/buildcrew-dash"
    fi

    echo ""
    echo -e "${GREEN}${BOLD}buildcrew-dash uninstalled successfully.${NC}"
    echo ""
}

main "$@"
