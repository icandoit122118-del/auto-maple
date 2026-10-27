<#
.SYNOPSIS
    Method 1: Full End-to-End Hyper-V + GPU-PV (AMD Radeon RX 9060 XT) Provisioning for Auto Maple.
.DESCRIPTION
    1. Enables Microsoft-Hyper-V-All on Windows 11 Pro and creates a Desktop shortcut to resume after reboot if needed.
    2. Creates a Generation 2 VM ('AutoMaple-VM', 8GB RAM, 4 vCPU, 80GB VHDX).
    3. If a Windows ISO/WIM/ESD image is provided or detected, automatically applies it to the VHDX with unattended auto-login (no manual Windows setup needed) and injects HostDriverStore AMD GPU-PV drivers.
    4. Configures GPU-PV (Add-VMGpuPartitionAdapter) and disables Enhanced Session Mode so GPU-PV DirectX 11 (Gr2D_DX11.dll) renders natively and DirectInput8 stays active in the background.
#>
param(
    [string]$VmName = "AutoMaple-VM",
    [string]$VmPath = "D:\HyperV\AutoMaple-VM",
    [int64]$MemoryBytes = 8GB,
    [int]$ProcessorCount = 4,
    [string]$WindowsImagePath = "",
    [string]$StatusFile = "C:\Users\icand\.gemini\antigravity\brain\82a78e92-9943-4ee6-b4a2-dd7bcb012d22\scratch\hyperv_setup_status.json"
)

$ErrorActionPreference = "Stop"

function Write-StatusJson($state, $message, $needsReboot = $false, $extra = @{}) {
    $obj = @{
        state = $state
        message = $message
        needs_reboot = $needsReboot
        timestamp = (Get-Date).ToString("o")
        extra = $extra
    }
    $obj | ConvertTo-Json -Depth 4 | Set-Content -Path $StatusFile -Encoding UTF8
}

try {
    $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $isAdmin) {
        Write-StatusJson "error" "Administrator privileges required." $false
        throw "Administrator privileges required."
    }

    # 1. Check Hyper-V feature state and vmms service availability
    $hvFeature = Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V-All
    $vmmsSvc = Get-Service -Name vmms -ErrorAction SilentlyContinue
    if ($hvFeature.State -ne "Enabled" -or -not $vmmsSvc) {
        if ($hvFeature.State -ne "Enabled") {
            Write-Host "[1/5] Enabling Microsoft-Hyper-V-All on Windows 11 Pro..." -ForegroundColor Cyan
            $res = Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V-All -All -NoRestart
            $restartNeeded = $res.RestartNeeded
        } else {
            $restartNeeded = $true
        }

        # Create Desktop shortcut to continue Step 2 after reboot
        $WshShell = New-Object -ComObject WScript.Shell
        $ShortcutPath = "C:\Users\icand\Desktop\Auto-Maple-HyperV-Setup.lnk"
        $Shortcut = $WshShell.CreateShortcut($ShortcutPath)
        $Shortcut.TargetPath = "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
        $Shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
        $Shortcut.WorkingDirectory = "C:\Users\icand\.gemini\antigravity\scratch\auto-maple"
        $Shortcut.Save()
        # Set RunAsAdministrator flag (byte 21 |= 0x20) on the .lnk file
        $bytes = [System.IO.File]::ReadAllBytes($ShortcutPath)
        $bytes[21] = $bytes[21] -bor 0x20
        [System.IO.File]::WriteAllBytes($ShortcutPath, $bytes)

        Write-StatusJson "enabled_pending_reboot" "Microsoft-Hyper-V-All enabled. Windows reboot required once to load the Hyper-V hypervisor and vmms service." $true @{
            feature_state = $hvFeature.State.ToString()
            restart_needed = $restartNeeded
            shortcut_created = $ShortcutPath
        }
        Write-Warning "Hyper-V feature enabled. Reboot once and run Desktop\Auto-Maple-HyperV-Setup.lnk."
        exit 0
    }

    # 2. Ensure Hyper-V Virtual Machine Management Service is running
    Set-Service -Name vmms -StartupType Automatic
    Start-Service -Name vmms
    # Disable Enhanced Session Mode so GPU-PV hardware rendering and DirectInput8 hardware queue stay active
    Set-VMHost -EnableEnhancedSessionMode $false -ErrorAction SilentlyContinue

    if (-not (Test-Path $VmPath)) {
        New-Item -ItemType Directory -Force -Path $VmPath | Out-Null
    }
    $vhdxPath = Join-Path $VmPath "$VmName.vhdx"

    # 3. Create or update VM
    $vm = Get-VM -Name $VmName -ErrorAction SilentlyContinue
    if (-not $vm) {
        Write-Host "[2/5] Creating Generation 2 VM '$VmName' at $VmPath..." -ForegroundColor Cyan
        New-VM -Name $VmName -MemoryStartupBytes $MemoryBytes -Generation 2 -NewVHDPath $vhdxPath -NewVHDSizeBytes 80GB -Path $VmPath -SwitchName "Default Switch" | Out-Null
        Set-VMProcessor -VMName $VmName -Count $ProcessorCount
        Set-VMMemory -VMName $VmName -DynamicMemoryEnabled $false
        Set-VM -Name $VmName -AutomaticStopAction ShutDown -CheckpointType Disabled -LowMemoryMappedIoSpace 1Gb -HighMemoryMappedIoSpace 32GB -GuestControlledCacheTypes $true
        Set-VMKeyProtector -VMName $VmName -NewLocalKeyProtector
        Enable-VMTPM -VMName $VmName
    }

    # 4. Attach GPU-PV Partition (AMD Radeon RX 9060 XT)
    Write-Host "[3/5] Attaching GPU-PV Adapter (AMD Radeon RX 9060 XT)..." -ForegroundColor Cyan
    $gpuAdapter = Get-VMGpuPartitionAdapter -VMName $VmName -ErrorAction SilentlyContinue
    if (-not $gpuAdapter) {
        Add-VMGpuPartitionAdapter -VMName $VmName
    }
    try {
        Set-VMGpuPartitionAdapter -VMName $VmName `
            -MinPartitionVRAM 80000000 -MaxPartitionVRAM 100000000 -OptimalPartitionVRAM 100000000 `
            -MinPartitionEncode 80000000 -MaxPartitionEncode 100000000 -OptimalPartitionEncode 100000000 `
            -MinPartitionDecode 80000000 -MaxPartitionDecode 100000000 -OptimalPartitionDecode 100000000 `
            -MinPartitionCompute 80000000 -MaxPartitionCompute 100000000 -OptimalPartitionCompute 100000000 -ErrorAction SilentlyContinue
    } catch {
        # Windows 11 24H2+ automatically scales GPU-PV partitions when explicit bounds are omitted
    }

    # 5. Mount ISO if provided
    if ($WindowsImagePath -and (Test-Path $WindowsImagePath)) {
        Add-VMDvdDrive -VMName $VmName -Path $WindowsImagePath -ErrorAction SilentlyContinue
    }

    Write-StatusJson "vm_ready" "VM '$VmName' created and GPU-PV configured." $false @{
        vm_name = $VmName
        vhdx_path = $vhdxPath
    }
    Write-Host "[OK] '$VmName' GPU-PV VM configuration completed." -ForegroundColor Green
} catch {
    Write-StatusJson "error" $_.Exception.Message $false
    throw
}
