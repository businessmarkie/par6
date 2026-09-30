# PAR6 Waldo Commander -- Windows side of the bootstrap. Run AFTER the reboot
# that activates VirtualMachinePlatform:  powershell -ExecutionPolicy Bypass -File .\wsl_bootstrap.ps1
#
# Registers Ubuntu 24.04, creates your Linux user non-interactively, then hands
# off to wsl_bootstrap.sh (copied into the WSL home so no /mnt/c path with
# spaces has to survive wsl.exe's argument joining).
$ErrorActionPreference = 'Stop'
$Distro = 'Ubuntu-24.04'
$LinuxUser = ($env:USERNAME.ToLower() -replace '[^a-z0-9_-]', '')
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not (Get-CimInstance Win32_ComputerSystem).HypervisorPresent) {
    Write-Host "Hypervisor is not running: VirtualMachinePlatform is still pending a reboot." -ForegroundColor Red
    Write-Host "Reboot (shutdown /r /t 0), then run this script again."
    exit 1
}

$installed = ((wsl.exe -l -q 2>$null | Out-String) -replace "`0", "")
if ($installed -notmatch [regex]::Escape($Distro)) {
    Write-Host "== registering $Distro" -ForegroundColor Cyan
    wsl.exe --install $Distro --no-launch
    if ($LASTEXITCODE -ne 0) { throw "wsl --install $Distro failed ($LASTEXITCODE)" }
}

Write-Host "== creating Linux user '$LinuxUser' (passwordless sudo via the sudo group; set a password later with passwd)" -ForegroundColor Cyan
$setup = "id -u $LinuxUser >/dev/null 2>&1 || (useradd -m -s /bin/bash -G sudo $LinuxUser && passwd -d $LinuxUser); " +
         "printf '[user]\ndefault=$LinuxUser\n\n[boot]\nsystemd=true\n' > /etc/wsl.conf; " +
         "grep -q '^%sudo.*NOPASSWD' /etc/sudoers || echo '%sudo ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/90-wsl-sudo"
wsl.exe -d $Distro -u root -- bash -c $setup
if ($LASTEXITCODE -ne 0) { throw "user setup failed ($LASTEXITCODE)" }
wsl.exe --terminate $Distro   # so /etc/wsl.conf's default user takes effect

Write-Host "== copying wsl_bootstrap.sh into the WSL home and running it" -ForegroundColor Cyan
Get-Content -Raw (Join-Path $Here 'wsl_bootstrap.sh') | wsl.exe -d $Distro -- bash -c "tr -d '\r' > ~/wsl_bootstrap.sh"
wsl.exe -d $Distro -- bash -lc "bash ~/wsl_bootstrap.sh"
if ($LASTEXITCODE -ne 0) { throw "wsl_bootstrap.sh failed ($LASTEXITCODE)" }

Write-Host ""
Write-Host "Ready. Start the app with:" -ForegroundColor Green
Write-Host "  wsl -d $Distro -- bash -lc 'source ~/par6-build/.venv/bin/activate && waldo-commander --robot par6'"
Write-Host "then open http://localhost:8080"
