import concurrent.futures
import ctypes
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request

ESD_URL = "http://dl.delivery.mp.microsoft.com/filestreamingservice/files/68319007-ebd8-401b-bece-299f3cb76357/26100.4349.250607-1500.ge_release_svc_refresh_CLIENTCONSUMER_RET_x64FRE_ko-kr.esd"
VM_DIR = r"D:\HyperV\AutoMaple-VM"
ESD_PATH = os.path.join(VM_DIR, "win11_ko-kr.esd")
VHDX_PATH = os.path.join(VM_DIR, "AutoMaple-VM.vhdx")
STATUS_PATH = os.path.join(VM_DIR, "deploy_status.json")

user32 = ctypes.WinDLL('user32', use_last_error=True)
shell32 = ctypes.windll.shell32

def update_status(step, message, pct=0, extra=None):
    data = {
        "step": step,
        "message": message,
        "percent": round(pct, 1),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")
    }
    if extra:
        data.update(extra)
    try:
        with open(STATUS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass
    print(f"[{step}] ({pct:.1f}%) {message}", flush=True)

def download_esd_parallel(url, dest_path, num_threads=8):
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=15) as resp:
        total_size = int(resp.headers.get("Content-Length", 0))

    if not os.path.exists(dest_path) or os.path.getsize(dest_path) != total_size:
        with open(dest_path, "wb") as f:
            f.truncate(total_size)

    chunk_size = total_size // num_threads
    downloaded = [0] * num_threads
    resume_offsets = [0] * num_threads

    # Detect already-downloaded bytes in each chunk so interrupted downloads resume instantly
    with open(dest_path, "rb") as f:
        for i in range(num_threads):
            s = i * chunk_size
            e = (total_size - 1) if i == num_threads - 1 else (s + chunk_size - 1)
            pos = e
            while pos > s:
                step_pos = max(s, pos - 262144)
                f.seek(step_pos)
                buf = f.read(pos - step_pos + 1)
                if any(buf):
                    break
                pos = step_pos
            # Back up 2MB from last non-zero block for safety
            safe_pos = max(s, pos - 2 * 1048576) if pos < e else (e + 1)
            resume_offsets[i] = safe_pos
            downloaded[i] = safe_pos - s

    if sum(downloaded) >= total_size:
        update_status("download", "Existing ESD fully downloaded.", 100.0, {"size_mb": round(total_size / 1048576, 1)})
        return

    initial_done = sum(downloaded)
    update_status("download", f"Resuming Windows 11 ESD from {initial_done / 1048576:.0f}/{total_size / 1048576:.0f} MB...", (initial_done / total_size) * 100.0)
    t_start = time.time()

    def fetch_range(idx, start, end):
        if start > end:
            return
        r = urllib.request.Request(url)
        r.add_header("Range", f"bytes={start}-{end}")
        with urllib.request.urlopen(r, timeout=30) as response, open(dest_path, "r+b") as out_f:
            out_f.seek(start)
            while True:
                buf = response.read(1024 * 1024)
                if not buf:
                    break
                out_f.write(buf)
                downloaded[idx] += len(buf)

    futures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as ex:
        for i in range(num_threads):
            s = resume_offsets[i]
            e = (total_size - 1) if i == num_threads - 1 else ((i + 1) * chunk_size - 1)
            futures.append(ex.submit(fetch_range, i, s, e))

        while not all(f.done() for f in futures):
            done_bytes = sum(downloaded)
            pct = (done_bytes / total_size) * 100.0 if total_size else 0
            elapsed = max(0.1, time.time() - t_start)
            speed_mbps = ((done_bytes - initial_done) / 1048576) / elapsed
            update_status("download", f"Downloading Windows 11 ESD ({done_bytes / 1048576:.0f}/{total_size / 1048576:.0f} MB, {speed_mbps:.1f} MB/s)", pct)
            time.sleep(2.0)

        for f in futures:
            f.result()

    update_status("download", "Download completed.", 100.0)

UNATTEND_XML = """<?xml version="1.0" encoding="utf-8"?>
<unattend xmlns="urn:schemas-microsoft-com:unattend">
    <settings pass="specialize">
        <component name="Microsoft-Windows-Shell-Setup" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS">
            <ComputerName>AUTOMAPLE-VM</ComputerName>
        </component>
    </settings>
    <settings pass="oobeSystem">
        <component name="Microsoft-Windows-International-Core" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS">
            <InputLocale>0412:00000412</InputLocale>
            <SystemLocale>ko-KR</SystemLocale>
            <UILanguage>ko-KR</UILanguage>
            <UserLocale>ko-KR</UserLocale>
        </component>
        <component name="Microsoft-Windows-Shell-Setup" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS">
            <OOBE>
                <HideEULAPage>true</HideEULAPage>
                <HideLocalAccountScreen>true</HideLocalAccountScreen>
                <HideOEMRegistrationScreen>true</HideOEMRegistrationScreen>
                <HideOnlineAccountScreens>true</HideOnlineAccountScreens>
                <HideWirelessSetupInOOBE>true</HideWirelessSetupInOOBE>
                <ProtectYourPC>3</ProtectYourPC>
            </OOBE>
            <UserAccounts>
                <LocalAccounts>
                    <LocalAccount wcm:action="add" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State">
                        <Password>
                            <Value></Value>
                            <PlainText>true</PlainText>
                        </Password>
                        <Description>AutoMaple User</Description>
                        <DisplayName>AutoMaple</DisplayName>
                        <Group>Administrators</Group>
                        <Name>AutoMaple</Name>
                    </LocalAccount>
                </LocalAccounts>
            </UserAccounts>
            <AutoLogon>
                <Password>
                    <Value></Value>
                    <PlainText>true</PlainText>
                </Password>
                <Enabled>true</Enabled>
                <Username>AutoMaple</Username>
            </AutoLogon>
        </component>
    </settings>
</unattend>
"""

def main():
    os.makedirs(VM_DIR, exist_ok=True)
    # 1. Download ESD
    download_esd_parallel(ESD_URL, ESD_PATH, num_threads=8)

    # 2. Find Windows 11 Pro Index in ESD
    update_status("wiminfo", "Inspecting ESD image indexes...", 10.0)
    wim_out = subprocess.check_output(["dism.exe", "/English", "/Get-WimInfo", f"/WimFile:{ESD_PATH}"], text=True, errors="ignore")
    # Find Index for Windows 11 Pro (usually Index 6 in Consumer ESD, or last Pro index)
    index = "6"
    matches = re.findall(r"Index\s*:\s*(\d+)\s+Name\s*:\s*([^\r\n]+)", wim_out)
    for idx, name in matches:
        if "Pro" in name and "Education" not in name and "Workstations" not in name and "N" not in name.split():
            index = idx
            break
    update_status("wiminfo", f"Selected ESD Index {index} from {matches}", 20.0)

    # 3. Stop VM if running, Mount VHDX, Partition EFI (S:) + Windows (W:)
    update_status("partition", "Mounting and partitioning AutoMaple-VM.vhdx...", 30.0)
    ps_part = f"""
    $ErrorActionPreference = 'Stop'
    Stop-VM -Name 'AutoMaple-VM' -Force -ErrorAction SilentlyContinue
    Dismount-VHD -Path '{VHDX_PATH}' -ErrorAction SilentlyContinue
    $vhd = Mount-VHD -Path '{VHDX_PATH}' -Passthru
    $diskNum = $vhd.DiskNumber
    $disk = Get-Disk -Number $diskNum
    if ($disk.PartitionStyle -ne 'RAW') {{
        Clear-Disk -Number $diskNum -RemoveData -RemoveOEM -Confirm:$false
    }}
    Initialize-Disk -Number $diskNum -PartitionStyle GPT
    $efi = New-Partition -DiskNumber $diskNum -Size 260MB -GptType '{{c12a7328-f81f-11d2-ba4b-00a0c93ec93b}}'
    Format-Volume -Partition $efi -FileSystem FAT32 -NewFileSystemLabel 'System' -Confirm:$false | Out-Null
    Add-PartitionAccessPath -DiskNumber $diskNum -PartitionNumber $efi.PartitionNumber -AccessPath 'S:'
    $win = New-Partition -DiskNumber $diskNum -UseMaximumSize -GptType '{{ebd0a0a2-b9e5-4433-87c0-68b6b72699c7}}'
    Format-Volume -Partition $win -FileSystem NTFS -NewFileSystemLabel 'Windows' -Confirm:$false | Out-Null
    Add-PartitionAccessPath -DiskNumber $diskNum -PartitionNumber $win.PartitionNumber -AccessPath 'W:'
    """
    subprocess.run([r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe", "-NoProfile", "-Command", ps_part], check=True)

    try:
        # 4. Apply Windows 11 Pro image to W:\
        update_status("apply_image", f"Applying Windows 11 Pro (Index {index}) to VHDX (W:\\)...", 40.0)
        subprocess.run(["dism.exe", "/English", "/Apply-Image", f"/ImageFile:{ESD_PATH}", f"/Index:{index}", "/ApplyDir:W:\\"], check=True)

        # 5. Configure UEFI bootloader with bcdboot
        update_status("bcdboot", "Configuring UEFI bootloader on S:\\...", 75.0)
        subprocess.run(["bcdboot.exe", r"W:\Windows", "/s", "S:", "/f", "UEFI"], check=True)

        # 6. Inject Unattend.xml (skip OOBE, auto-login as AutoMaple)
        update_status("unattend", "Injecting Unattend.xml for zero-touch login...", 80.0)
        panther_dir = r"W:\Windows\Panther"
        os.makedirs(panther_dir, exist_ok=True)
        with open(os.path.join(panther_dir, "Unattend.xml"), "w", encoding="utf-8") as f:
            f.write(UNATTEND_XML)

        # 7. Inject Host AMD Radeon RX 9060 XT GPU-PV Drivers into W:\Windows\System32\HostDriverStore\FileRepository
        update_status("gpupv_driver", "Injecting AMD Radeon RX 9060 XT GPU-PV drivers into VHDX...", 85.0)
        ps_drv = r"""
        $targetRepo = "W:\Windows\System32\HostDriverStore\FileRepository"
        New-Item -ItemType Directory -Force -Path $targetRepo | Out-Null
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
                Copy-Item -Path $src -Destination $dst -Recurse -Force
            }
        }
        """
        subprocess.run([r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe", "-NoProfile", "-Command", ps_drv], check=True)

        # 8. Copy Auto Maple project into W:\AutoMaple inside the VM
        update_status("copy_automaple", "Copying Auto Maple into VM (W:\\AutoMaple)...", 92.0)
        shutil.copytree(r"C:\Users\icand\.gemini\antigravity\scratch\auto-maple", r"W:\AutoMaple", dirs_exist_ok=True, ignore=shutil.ignore_patterns('.git'))

    finally:
        # Dismount VHDX
        update_status("dismount", "Dismounting AutoMaple-VM.vhdx...", 95.0)
        subprocess.run([r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe", "-NoProfile", "-Command", f"Dismount-VHD -Path '{VHDX_PATH}' -ErrorAction SilentlyContinue"], check=False)

    # 9. Configure VM Boot Order and Start AutoMaple-VM
    update_status("start_vm", "Starting AutoMaple-VM and opening VMConnect...", 98.0)
    ps_start = """
    $hdd = Get-VMHardDiskDrive -VMName 'AutoMaple-VM' | Select-Object -First 1
    if ($hdd) {
        Set-VMFirmware -VMName 'AutoMaple-VM' -FirstBootDevice $hdd
    }
    Start-VM -Name 'AutoMaple-VM'
    Start-Process 'vmconnect.exe' -ArgumentList 'localhost', 'AutoMaple-VM'
    """
    subprocess.run([r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe", "-NoProfile", "-Command", ps_start], check=True)
    update_status("done", "AutoMaple-VM is running with Windows 11 Pro + RX 9060 XT GPU-PV!", 100.0)

if __name__ == "__main__":
    if "--elevated" not in sys.argv:
        hdesk = user32.OpenDesktopW("Default", 0, False, 0x10000000)
        if hdesk:
            user32.SetThreadDesktop(hdesk)
        if os.path.exists(STATUS_PATH):
            os.remove(STATUS_PATH)
        shell32.ShellExecuteW(None, "runas", sys.executable, f'"{__file__}" --elevated', VM_DIR, 0)
        for _ in range(600):
            if os.path.exists(STATUS_PATH):
                try:
                    st = json.loads(open(STATUS_PATH, "r", encoding="utf-8").read())
                    print(f"[{st.get('step')}] {st.get('percent')}% - {st.get('message')}", flush=True)
                    if st.get("step") in ("done", "error"):
                        break
                except Exception:
                    pass
            time.sleep(3.0)
        sys.exit(0)
    try:
        main()
    except Exception as e:
        import traceback
        update_status("error", f"{e}\n{traceback.format_exc()}", 0.0)
        sys.exit(1)
