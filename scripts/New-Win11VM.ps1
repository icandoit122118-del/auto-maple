#Requires -RunAsAdministrator
<#
  Hyper-V Windows 11 가상머신 생성 스크립트 (2세대, TPM, Secure Boot)
  사용: 관리자 PowerShell에서
    .\New-Win11VM.ps1 -IsoPath "D:\ISO\Win11.iso"
#>
param(
    [Parameter(Mandatory)][string]$IsoPath,
    [string]$VMName     = "Win11-VM",
    [string]$VMRoot     = "D:\HyperV",
    [int]$MemoryGB      = 8,
    [int]$CpuCount      = 4,
    [int]$DiskGB        = 64   # 동적 확장: 실제 점유는 설치 후 약 25~30GB
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $IsoPath)) { throw "ISO 파일을 찾을 수 없습니다: $IsoPath" }
if (Get-VM -Name $VMName -ErrorAction SilentlyContinue) { throw "이미 같은 이름의 VM이 있습니다: $VMName" }

$vhdPath = Join-Path $VMRoot "$VMName\$VMName.vhdx"
New-Item -ItemType Directory -Path (Split-Path $vhdPath) -Force | Out-Null

# 가상 스위치 (기본 스위치가 없으면 NAT 용 Default Switch 사용)
$switch = (Get-VMSwitch -Name "Default Switch" -ErrorAction SilentlyContinue)
if (-not $switch) { $switch = Get-VMSwitch | Select-Object -First 1 }

New-VHD -Path $vhdPath -SizeBytes ($DiskGB * 1GB) -Dynamic | Out-Null

New-VM -Name $VMName -Generation 2 -MemoryStartupBytes ($MemoryGB * 1GB) `
       -VHDPath $vhdPath -Path $VMRoot -SwitchName $switch.Name | Out-Null

Set-VM -Name $VMName -ProcessorCount $CpuCount -AutomaticCheckpointsEnabled $false `
       -DynamicMemory:$false

# Secure Boot + 가상 TPM (Windows 11 요구사항)
Set-VMFirmware -VMName $VMName -EnableSecureBoot On -SecureBootTemplate "MicrosoftWindows"
Set-VMKeyProtector -VMName $VMName -NewLocalKeyProtector
Enable-VMTPM -VMName $VMName

# ISO 연결 및 DVD 우선 부팅
Add-VMDvdDrive -VMName $VMName -Path $IsoPath
$dvd = Get-VMDvdDrive -VMName $VMName
Set-VMFirmware -VMName $VMName -FirstBootDevice $dvd

Write-Host "`n'$VMName' 생성 완료." -ForegroundColor Green
Write-Host "  vCPU: $CpuCount / RAM: ${MemoryGB}GB / 디스크: ${DiskGB}GB(동적) / 위치: $vhdPath"
Write-Host "다음: vmconnect localhost $VMName  → Start-VM -Name $VMName  → 부팅 직후 아무 키나 눌러 설치 시작"
