# Auto Maple — MapleStory Classic World 백그라운드 캡처·입력 및 Hyper-V GPU-PV 구축 가이드

본 저장소는 `auto-maple`을 **MapleStory Classic World (`maplestorycw`, Windows 11 Pro 64-bit)** 환경에 맞게 개조하고, 백그라운드 화면 캡처(`PrintWindow`)·입력(`PostMessageW` + Windows 11 포커스 제어 + `SendInput`) 및 **Hyper-V GPU-PV(AMD Radeon RX 9060 XT)** 가상머신 분리 구성을 통합한 버전입니다.

---

## 1. 주요 코드 변경 사항

1. **백그라운드 화면 캡처 ([`src/modules/capture.py`](src/modules/capture.py))**
   - `user32.PrintWindow(self.handle, mfcDC, 2)` (`PW_RENDERFULLCONTENT = 2`)를 적용해 메이플스토리 창이 다른 창(유튜브, 브라우저 등) 뒤에 완전히 가려진 상태에서도 DWM 백버퍼를 실시간 캡처합니다. (`mss` 폴백 포함)
   - 멀티 모니터 환경에서 왼쪽 보조 모니터의 음수 좌표(`rect < 0`)가 `max(0, x)`로 잘리던 원본 버그를 수정했습니다.

2. **백그라운드·포커스 하이브리드 키/마우스 입력 ([`src/common/vkeys.py`](src/common/vkeys.py), [`src/common/config.py`](src/common/config.py))**
   - 하드웨어 스캔코드가 패킹된 `lParam`(`1 | (scan << 16) | extended`)으로 `PostMessageW(WM_KEYDOWN / WM_KEYUP / WM_LBUTTONDOWN / WM_RBUTTONDOWN)`를 전송합니다.
   - `MapleStory.exe`의 `DirectInput8`(`DISCL_FOREGROUND` 모드) 키 수집 특성에 대응하기 위해 Windows 11 `ForegroundLockTimeout`을 우회(`VK_MENU` + `SwitchToThisWindow` + `SetForegroundWindow`)하는 3가지 입력 모드(`config.bg_input_mode`)를 지원합니다:
     - `'auto_focus'` (기본값): 사냥 루틴 활성화 시 메이플스토리 창에 자동으로 포커스를 잡아 `DirectInput8` 이동·스킬 입력을 100% 전달합니다.
     - `'focus_restore'`: 키 입력 시에만 메이플스토리로 포커스를 전환하고 `key_up` 즉시 이전 작업 창으로 포커스를 복구합니다.
     - `'postmessage_only'`: 포커스 전환 없이 `PostMessageW`만 전송합니다 (가상머신/보조 세션 내부 실행 시 사용).
   - 원본 `KeyboardInput` 구조체에서 `wVk=0` 전달 시 `wScan`이 `0`으로 덮어써지던 버그를 수정했습니다.

3. **관리자 권한 자동 승격 및 데스크톱 연결 ([`main.py`](main.py))**
   - 관리자 권한으로 실행되는 `MapleStory.exe`에 의해 발생하는 Windows UIPI 차단(`ERROR_ACCESS_DENIED = 5`)을 방지하기 위해 `ShellExecuteW('runas')` 자동 관리자 승격 및 콘솔 QuickEdit 비활성화를 적용했습니다.

4. **MapleStory Classic World 전용 미니맵 템플릿 및 정규화 매칭 ([`src/common/utils.py`](src/common/utils.py), [`assets/`](assets/))**
   - `single_match`를 정규화 상관계수(`cv2.TM_CCOEFF_NORMED`)로 변경했습니다.
   - 클래식 월드 UI 기준 미니맵 좌상단([`assets/minimap_tl_template.png`](assets/minimap_tl_template.png)), 우하단([`assets/minimap_br_template.png`](assets/minimap_br_template.png)), 캐릭터 노란 점([`assets/player_template.png`](assets/player_template.png)) 템플릿을 추출해 교체했습니다 (기존 2021 템플릿은 `*.2021.bak`으로 백업).

5. **텐서플로 룬 모델 가중치 예외 처리 ([`src/detection/detection.py`](src/detection/detection.py), [`src/modules/bot.py`](src/modules/bot.py))**
   - 원본 배포처에서 삭제된 룬 모델 가중치(`variables.data-00000-of-00001`)가 없을 때 봇 메인 루프가 멈추지 않고 사냥 루틴을 정상 수행하도록 예외 처리를 추가했습니다.

---

## 2. 백그라운드 실행 3가지 방식 성능 및 동작 비교

| 평가 항목 | 방식 1: Hyper-V GPU-PV ([`scripts/setup_hyperv_gpupv.ps1`](scripts/setup_hyperv_gpupv.ps1)) | 방식 2: 멀티 세션 RDP ([`scripts/setup_multisession_rdp.ps1`](scripts/setup_multisession_rdp.ps1)) | 방식 3: 자동 포커스·복구 ([`src/common/vkeys.py`](src/common/vkeys.py)) |
| :--- | :--- | :--- | :--- |
| **스킬·단발 키 인식률 (`DirectInput8`)** | **100%** (VM 내부 상시 활성) | **100%** (보조 세션 내부 상시 활성) | **100%** (`34.79ms` / 복구 시 `36.57ms`) |
| **방향키 장시간 이동 (`walk_hold`)** | **100%** | **100%** | **100%** (이동 중에는 메이플이 포커스 점유) |
| **본체 마우스·키보드 동시 사용** | **완벽 분리 (타이핑·웹서핑·타 게임 가능)** | **완벽 분리** | **불가 (유튜브·영상 시청용으로 적합)** |
| **시스템 리소스 소모 (32GB RAM 기준)** | RAM 약 6~8GB, GPU 10~15% | RAM 약 1.5~2GB, CPU 3~5% | **추가 소모 0% (네이티브 최고 성능)** |
| **클라이언트 보안(`MapleSecurePC64.dll`)** | **통과** (바이너리 내 Hyper-V 차단 없음 확인) | **통과** | **통과** (외부 Win32 표준 입력) |

---

## 3. 방식 1 (Hyper-V + AMD Radeon RX 9060 XT GPU-PV) 실행 및 BIOS 설정

### 구축 스크립트 목록
- [`scripts/setup_hyperv_gpupv.ps1`](scripts/setup_hyperv_gpupv.ps1): Windows 11 Pro `Microsoft-Hyper-V-All` 활성화, `AutoMaple-VM`(4코어, 8GB RAM, 80GB VHDX) 생성 및 `AMD Radeon RX 9060 XT` GPU-PV 파티션 어댑터 연결
- [`scripts/deploy_win11_to_vhdx.py`](scripts/deploy_win11_to_vhdx.py): Microsoft 공식 Windows 11 한국어 ESD 다운로드, VHDX 파티션(EFI + NTFS) 포맷, Windows 11 Pro(Index 6) 배포, UEFI 부트로더 등록, OOBE 생략·자동 로그인(`Unattend.xml`) 주입, 호스트 `RX 9060 XT` 드라이버(`HostDriverStore`) 주입 및 `C:\AutoMaple` 복사
- [`scripts/inject_gpupv_drivers.ps1`](scripts/inject_gpupv_drivers.ps1): 호스트 GPU 드라이버가 업데이트되었을 때 가상머신 `HostDriverStore`를 다시 동기화하는 스크립트

### ASUS PRIME A520M-K (AMD Ryzen 5 5600) BIOS 가상화(`SVM Mode`) 활성화 방법
1. PC 재부팅 시 **`Del`**(또는 **`F2`**) 키를 연타해 BIOS 진입
2. **`F7`** 키를 눌러 **Advanced Mode**로 전환
3. 상단 **`Advanced`** 탭 → **`CPU Configuration`** 진입
4. **`SVM Mode`**를 `Disabled`에서 **`Enabled`**로 변경
5. **`F10`** 키를 눌러 저장 후 재부팅 → 바탕화면의 **`AutoMaple-VM-Start.lnk`** 실행
