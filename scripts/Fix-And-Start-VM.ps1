$ErrorActionPreference = "Continue"

Write-Host "AutoMaple-VM 상태 확인 및 연결 창 실행 중..." -ForegroundColor Cyan
$vm = Get-VM -Name "AutoMaple-VM" -ErrorAction SilentlyContinue
if ($vm -and $vm.State -ne "Running") {
    Start-VM -Name "AutoMaple-VM"
}

Write-Host "가상 컴퓨터 연결(vmconnect) 창을 엽니다. (이 창은 최소화해 두셔도 됩니다)" -ForegroundColor Green
Start-Process -FilePath "C:\Windows\System32\vmconnect.exe" -ArgumentList "localhost", "AutoMaple-VM" -Wait
