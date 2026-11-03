#!/usr/bin/env bash
# wsl_setup_rtl.sh - Ara RTL environment setup in WSL (run as root)
# GitHub is unreachable directly from this WSL (SNI-blocked); all github
# traffic goes through the gh-proxy.com mirror via git insteadOf rewrite.
set -exo pipefail
cd /root/work/ara

log() { echo "[$(date +%H:%M:%S)] $*"; }
MIRROR="https://gh-proxy.com/"

# 0) route all git github traffic through the mirror (idempotent)
git config --global url."${MIRROR}https://github.com/".insteadOf "https://github.com/"

# 1) bender
if ! command -v bender >/dev/null 2>&1; then
  log "installing bender (via mirror)"
  curl -sL --retry 3 -o /tmp/bender.tar.xz \
    ${MIRROR}https://github.com/pulp-platform/bender/releases/download/v0.32.1/bender-x86_64-unknown-linux-gnu.tar.xz
  tar -xJf /tmp/bender.tar.xz -C /tmp
  install -m755 /tmp/bender-x86_64-unknown-linux-gnu/bender /usr/local/bin/bender
fi
bender --version

# 2) python deps for repo scripts
pip3 install --break-system-packages -q -r python-requirements.txt || true

# 3) verilator submodule (pinned commit checked out by `make verilator`)
if [ ! -d toolchain/verilator/.git ]; then
  log "init verilator submodule"
  git submodule update --init toolchain/verilator
fi

# 4) RTL deps via bender + patches
log "hardware checkout"
make -C hardware checkout
log "hardware apply-patches"
make -C hardware apply-patches

# 5) verilator build (pinned 06263ec, make -j8)
log "building verilator (10-20 min)"
make verilator
log "verilator: $(install/verilator/bin/verilator --version)"

log "RTL SETUP DONE"
