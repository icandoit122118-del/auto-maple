<#
.SYNOPSIS
    Method 2: Multi-Session Local RDP (Remote Desktop Loopback + Background Render Preservation).
.DESCRIPTION
    1. Enables Windows 11 Pro TermService (Remote Desktop) and configures fSingleSessionPerUser = 0.
    2. Sets RemoteDesktop_SuppressWhenMinimized = 2 so the RDP client continues rendering GUI/DirectX and processing SendInput even when minimized or behind other windows on the host.
    3. Creates a local worker account ('AutoMapleWorker') if requested and launches mstsc.exe loopback (127.0.0.2).
#>
param(
    [switch]$ConfigureHost,
    [switch]$LaunchClient
)

$ErrorActionPreference = "Stop"

# 1. Host Registry Setting: Keep RDP session rendering even when minimized on host
$tsClientPaths = @(
    "HKCU:\Software\Microsoft\Terminal Server Client",
    "HKLM:\Software\Microsoft\Terminal Server Client",
    "HKLM:\Software\Wow6432Node\Microsoft\Terminal Server Client"
)
foreach ($regPath in $tsClientPaths) {
    if (-not (Test-Path $regPath)) {
        New-Item -Path $regPath -Force | Out-Null
    }
    Set-ItemProperty -Path $regPath -Name "RemoteDesktop_SuppressWhenMinimized" -Value 2 -Type DWord -ErrorAction SilentlyContinue
}

if ($ConfigureHost) {
    if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Run with -ConfigureHost as Administrator."
    }
    Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server" -Name "fDenyTSConnections" -Value 0 -Type DWord
    Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server" -Name "fSingleSessionPerUser" -Value 0 -Type DWord
    Set-Service -Name TermService -StartupType Manual
    Start-Service -Name TermService
    Enable-NetFirewallRule -DisplayGroup "Remote Desktop" -ErrorAction SilentlyContinue
    Write-Host "TermService enabled and RemoteDesktop_SuppressWhenMinimized=2 applied." -ForegroundColor Green
}

if ($LaunchClient) {
    Start-Process "mstsc.exe" -ArgumentList "/v:127.0.0.2 /w:1400 /h:850"
}
