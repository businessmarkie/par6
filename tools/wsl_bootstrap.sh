#!/usr/bin/env bash
# PAR6 Waldo Commander -- Linux side of the bootstrap. Runs inside Ubuntu 24.04
# on WSL2 (launched by wsl_bootstrap.ps1, or by hand: `bash ~/wsl_bootstrap.sh`).
#
# The par6 backend is Linux-only (socketcan, MuJoCo via pixi), but its release
# wheel is self-contained -- `par6d` and the whole C++ closure ride inside it --
# so nothing here needs Rust, pixi or a compiler. The wheel is manylinux_2_39,
# which is why the distro is 24.04 (glibc 2.39) and not 22.04.
#
# Version pairing, verified by import on 2026-09-29 (see the handoff doc):
#   * Waldo `main` declares waldoctl v0.12.0 but only imports on v0.13.x, and
#     par6 v0.6.0+ needs v0.14.0 -- so no par6 release runs against `main`.
#   * Waldo's PR stack #50..#63 (top: feat/supervised-restart) pins waldoctl
#     v0.14.0 and parol6 v0.10.0, and par6 v0.7.0 pins v0.14.0 as well. That is
#     the PAR6 pairing this script installs. Upstream's own par6 e2e job was red
#     on that branch on 2026-09-18, so expect to debug the first run.
#   * PAROL6-only on Waldo main: WALDO_REF=main WALDOCTL_REF=v0.13.1 PAROL6_REF=v0.7.0 PAR6_WHEEL=
set -euo pipefail

WALDO_REF="${WALDO_REF:-feat/supervised-restart}"
WALDOCTL_REF="${WALDOCTL_REF:-v0.14.0}"
PAROL6_REF="${PAROL6_REF:-v0.8.1}"      # newest published tag that is concrete on waldoctl v0.14 (branch pins the unpublished v0.10.0)
PAR6_WHEEL="${PAR6_WHEEL-https://github.com/Jepson2k/par6/releases/download/v0.7.0/par6-0.7.0-cp310-abi3-manylinux_2_39_x86_64.whl}"
RUCKIG_PIN="ruckig @ git+https://github.com/pantor/ruckig@2249d57ffaa19ecdadeaab62daf97857813629ff"
ROOT="${PAR6_ROOT:-$HOME/par6-build}"
WITH_CHROME="${WITH_CHROME:-0}"   # WITH_CHROME=1 also installs Chrome for the `screen` (selenium) tests

step() { printf '\n\033[1;36m== %s\033[0m\n' "$*"; }

step "apt packages"
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3 python3-venv python3-pip git curl build-essential libgl1
echo "glibc $(ldd --version | head -1 | awk '{print $NF}')  (par6 wheel needs >= 2.39)"; python3 --version

step "repos -> $ROOT (WSL filesystem, not /mnt/c: the 9p mount is several times slower)"
mkdir -p "$ROOT" && cd "$ROOT"
if [ -d Waldo-Commander ]; then
  git -C Waldo-Commander fetch -q origin "$WALDO_REF" && git -C Waldo-Commander checkout -q FETCH_HEAD
else
  git clone -q --branch "$WALDO_REF" https://github.com/Jepson2k/Waldo-Commander.git
fi
echo "Waldo-Commander at $(git -C Waldo-Commander log -1 --format='%h %ad %s' --date=short)"
# par6 is cloned for its assets/ (URDFs, meshes) and tools/; the runtime comes from the wheel.
[ -d par6 ] || git clone -q --depth 1 https://github.com/Jepson2k/par6.git

step "python venv"
[ -d .venv ] || python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -U pip

step "waldo-commander (CI order: ruckig pin, [dev] without the parol6 pin, parol6 --no-deps)"
pip install -q "$RUCKIG_PIN"
# The branch pins parol6 v0.10.0, a tag that did not exist on 2026-09-29. pip fails
# the whole resolve on a dead direct URL, so -- exactly as Waldo's CI does -- the
# parol6 line is dropped for this one resolve and parol6 is installed separately,
# --no-deps, at a tag that is published. Restore the pristine pyproject afterwards.
( cd Waldo-Commander && sed -i.bak -e '\#parol6 @ git+https://github.com/PCrnjak/PAROL6-python-API.git@v#d' pyproject.toml )
pip install -q -e "./Waldo-Commander[dev]"
( cd Waldo-Commander && mv pyproject.toml.bak pyproject.toml )
pip install -q --no-deps "parol6 @ git+https://github.com/PCrnjak/PAROL6-python-API.git@$PAROL6_REF"
pip install -q interpolatepy msgspec numba ormsgpack psutil toppra
# Make the contract version explicit rather than whatever the branch happened to pin.
pip install -q --force-reinstall --no-deps "waldoctl @ git+https://github.com/Jepson2k/waldoctl.git@$WALDOCTL_REF"

if [ -n "$PAR6_WHEEL" ]; then
  step "par6 backend (self-contained wheel, --no-deps so waldoctl stays as set above)"
  pip install -q --no-deps "$PAR6_WHEEL"
fi

step "import checks"
python - <<'PY'
import importlib.metadata as m, inspect, sys
ver = lambda p: m.version(p) if m.packages_distributions().get(p.replace('-', '_')) or True else '?'
for p in ("waldo-commander", "waldoctl", "parol6", "par6"):
    try: print(f"  {p:16} {m.version(p)}")
    except m.PackageNotFoundError: print(f"  {p:16} not installed")
failed = False
try:
    import waldo_commander.components.control; print("  waldo import chain: OK")
except Exception as e:
    failed = True; print(f"  waldo import chain: FAIL -> {e.__class__.__name__}: {e}")
try:
    import parol6
    for n in ("RobotClient", "AsyncRobotClient"):
        c = getattr(parol6, n)
        if inspect.isabstract(c): failed = True; print(f"  parol6.{n}: ABSTRACT -> {sorted(c.__abstractmethods__)}")
        else: print(f"  parol6.{n}: concrete")
except Exception as e:
    failed = True; print(f"  parol6: FAIL -> {e.__class__.__name__}: {e}")
try:
    import par6.robot; print("  par6.robot import: OK")
except ModuleNotFoundError as e:
    print(f"  par6: not installed ({e.name})")
except Exception as e:
    failed = True; print(f"  par6.robot import: FAIL -> {e.__class__.__name__}: {e}")
if failed:
    sys.exit("\nA pairing above is inconsistent. The verified table is in the handoff doc "
             "(Findings -> waldoctl pins); set WALDO_REF / WALDOCTL_REF / PAR6_WHEEL and rerun.")
PY
waldo-commander --help >/dev/null && echo "  waldo-commander entry point: OK"

if [ -n "$PAR6_WHEEL" ]; then
  step "smoke test: spawn the bundled par6d --sim and read joint angles"
  python - <<'PY'
from par6 import Robot
try:
    with Robot() as robot:              # spawns `par6d --sim`, waits for PAR6D_READY
        rbt = robot.create_sync_client()
        print("  PAR6 simulator answered; joint angles:", rbt.angles())
except Exception as exc:                # a failing smoke test must not hide the traceback
    import traceback; traceback.print_exc()
    raise SystemExit(f"par6d --sim smoke test failed: {exc}")
PY
fi

if [ "$WITH_CHROME" = "1" ]; then
  step "google chrome (for Waldo's browser-driven screen tests)"
  curl -fsSL -o /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq /tmp/chrome.deb
fi

cat <<EOT

== done ==
Activate:   source $ROOT/.venv/bin/activate
Run:        waldo-commander --robot par6        # PAROL6 sim instead: waldo-commander --robot parol6
            then open http://localhost:8080 from Windows (WSL2 forwards localhost)
Test:       cd $ROOT/Waldo-Commander && WALDO_PAR6_E2E=1 pytest tests/test_par6_backend.py -v
Pairing:    Waldo $WALDO_REF + waldoctl $WALDOCTL_REF + parol6 $PAROL6_REF + par6 wheel ${PAR6_WHEEL##*/}
EOT
