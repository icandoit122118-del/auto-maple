<#
.SYNOPSIS
    Copies the host's AMD Radeon RX 9060 XT GPU-PV drivers into the AutoMaple-VM VHDX (HostDriverStore).
.DESCRIPTION
    Mounts D:\HyperV\AutoMaple-VM\AutoMaple-VM.vhdx while the VM is stopped, copies the active Display adapter drivers
    from C:\Windows\System32\DriverStore\FileRepository into <VHDX>:\Windows\System32\HostDriverStore\FileRepository,
    and dismounts the VHDX.
#>
param(
    [string]$VmName = "AutoMaple-VM",
    [string]$VhdxPath = "D:\HyperV\AutoMaple-VM\AutoMaple-VM.vhdx"
)

$ErrorActionPreference = "Stop"

if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run this script as Administrator."
}

$vm = Get-VM -Name $VmName -ErrorAction SilentlyContinue
if ($vm -and $vm.State -ne "Off") {
    Write-Host "Stopping VM '$VmName' to inject GPU-PV drivers..." -ForegroundColor Cyan
    Stop-VM -Name $VmName -Force
}

Write-Host "Mounting VHDX: $VhdxPath" -ForegroundColor Cyan
$disk = Mount-VHD -Path $VhdxPath -Passthru
try {
    $driveLetter = ($disk | Get-Disk | Get-Partition | Where-Object { $_.DriveLetter } | Select-Object -ExpandProperty DriveLetter | Select-Object -First 1)
    if (-not $driveLetter) {
        throw "Could not find a Windows partition with a drive letter inside $VhdxPath. Install Windows on the VM first."
    }
    $targetRepo = "${driveLetter}:\Windows\System32\HostDriverStore\FileRepository"
    New-Item -ItemType Directory -Force -Path $targetRepo | Out-Null

    # Find active display drivers (AMD / u0* / amdfendr* / atikmdag*)
    $gpuInfList = Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty InstalledDisplayDrivers
    $driverFolders = @()
    foreach ($line in $gpuInfList) {
        foreach ($p in ($line -split ',')) {
            if ($p -match 'DriverStore\\FileRepository\\([^\\]+)') {
                $driverFolders += $Matches[1]
            }
        }
    }
    $driverFolders = $driverFolders | Select-Object -Unique
    foreach ($folder in $driverFolders) {
        $src = Join-Path "C:\Windows\System32\DriverStore\FileRepository" $folder
        $dst = Join-Path $targetRepo $folder
        if (Test-Path $src) {
            Write-Host "Copying GPU driver folder: $folder" -ForegroundColor Green
            Copy-Item -Path $src -Destination $dst -Recurse -Force
        }
    }
    Write-Host "AMD Radeon RX 9060 XT GPU-PV driver injection complete." -ForegroundColor Green
} finally {
    Dismount-VHD -Path $VhdxPath
}
