; 안전보건 법령·고시 Monitoring - Windows 설치 프로그램
;
; 사용자 폴더(%LOCALAPPDATA%\Programs\SafetyLawMonitor) 안에 (내장된 파이썬
; 실행환경 + 앱 소스 + 미리 채워둔 법령 캐시 DB를) 설치하고, 바탕화면에는
; 실행용 exe 파일 하나만 남긴다.
;
; [왜 Program Files가 아니라 사용자 폴더인가]
; 예전에는 C:\Program Files\SafetyLawMonitor에 설치했는데, 두 가지 문제가
; 있었다.
;   1) 설치할 때 관리자 권한(UAC)이 필요하다 - 회사 PC처럼 관리자 권한이
;      없는 계정에서는 설치 자체가 막힌다.
;   2) 더 심각한 문제: Windows는 Program Files 폴더를 "일반 권한으로는 쓸
;      수 없는" 폴더로 보호한다. 그런데 이 프로그램은 법령 데이터를
;      설치 폴더 안의 SQLite DB 파일(app\backend\safety_law_tracker.db)에
;      계속 기록한다. 설치는 관리자 권한으로 되더라도, 이후 바탕화면
;      아이콘을 더블클릭해 실행하는 프로그램은 일반 권한이라 DB에 쓰지
;      못하고 서버가 시작하다 죽는다.
; 사용자 폴더에 설치하면 둘 다 해결된다(권한 요청 창이 아예 안 뜨고, DB도
; 자유롭게 쓸 수 있다). VS Code, Zoom 같은 프로그램들이 쓰는 방식과 같다.
;
; 빌드: installer/build_installer.sh 가 이 스크립트를 실행하기 전에
; build/payload/python, build/payload/app, launcher/launcher.exe를
; 먼저 준비해둔다. (makensis installer/setup.nsi 로 직접 빌드해도 됨,
; 단 그 전에 위 파일들이 이미 준비되어 있어야 한다.)

Unicode true

!include "MUI2.nsh"
!include "nsDialogs.nsh"
!include "LogicLib.nsh"

Name "안전보건 법령·고시 Monitoring"
OutFile "build\install.exe"
InstallDir "$LOCALAPPDATA\Programs\SafetyLawMonitor"
; user - 관리자 권한을 요구하지 않는다(설치할 때 "이 앱이 장치를 변경하도록
; 허용하시겠어요?" 창이 뜨지 않는다).
RequestExecutionLevel user
SetCompressor /SOLID lzma

!define APP_NAME "안전보건 법령·고시 Monitoring"
!define DESKTOP_EXE_NAME "안전보건 법령 모니터링.exe"
; 사용자 폴더 설치라 레지스트리도 HKLM(컴퓨터 전체)이 아니라 HKCU(이 사용자)에 쓴다.
!define UNINSTALL_REG_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\SafetyLawMonitor"
!define APP_REG_KEY "Software\SafetyLawMonitor"
; 예전 버전이 관리자 권한으로 설치되던 고정 경로. 그 시절 설치 프로그램에는
; 경로를 고르는 화면이 없어서 항상 이 위치였다.
!define LEGACY_INSTALL_DIR "$PROGRAMFILES64\SafetyLawMonitor"

; 실행 중인 이 프로그램(바탕화면 실행 파일 + 그 아래에서 돌고 있는 서버)을
; 먼저 종료한다. Windows는 "실행 중인 파일"을 지우거나 덮어쓰지 못하게 막기
; 때문에, 이걸 안 하면 프로그램을 켜둔 채로 삭제/재설치했을 때 바탕화면
; 아이콘이나 파이썬 폴더가 지워지지 않고 그대로 남는다(Wine으로 실제 재현함).
;
; 설치 섹션과 제거 섹션은 서로 다른 실행 파일로 컴파일되어 함수를 공유할 수
; 없어서, 매크로로 만들어 양쪽에 각각 펼쳐 넣는다.
!macro StopRunningApp
  ; /T - 자식 프로세스까지 함께 종료한다(런처가 띄운 pythonw.exe 서버가 이
  ; 런처의 자식 프로세스라, 이 옵션 하나로 서버까지 같이 정리된다).
  nsExec::ExecToLog 'taskkill /F /T /IM "${DESKTOP_EXE_NAME}"'
  Pop $0
  ; 바탕화면 실행 파일 이름으로 종료한 뒤 남은 것(설치 폴더의 launcher.exe
  ; 복사본, 런처보다 오래 살아남은 서버 pythonw.exe)을 정리한다. 실행 파일
  ; 경로가 이 프로그램의 설치 폴더 안인 것만 골라서 종료하므로, 이름만 같은
  ; 다른 프로그램(다른 회사의 launcher.exe, 사용자가 쓰는 다른 파이썬 등)은
  ; 건드리지 않는다. uninstall.exe는 설치 폴더 안에서 실행될 수 있어(재설치가
  ; 부르는 `_?=` 방식) 자기 자신을 종료시키지 않도록 제외한다.
  nsExec::ExecToLog 'powershell -NoProfile -WindowStyle Hidden -Command "Get-Process -ErrorAction SilentlyContinue | Where-Object { $$_.Path -like $\'*SafetyLawMonitor*$\' -and $$_.ProcessName -ne $\'uninstall$\' } | Stop-Process -Force"'
  Pop $0
  ; 종료된 프로세스가 붙잡고 있던 파일 핸들이 실제로 풀릴 때까지 잠깐 기다린다.
  Sleep 1500
!macroend

Var PrevInstallDir    ; 이미 설치된 기존 버전의 설치 폴더(없으면 빈 문자열)
Var PrevIsLegacy      ; 기존 설치가 예전의 관리자 권한(Program Files) 설치인지 "1"/""
Var ChoiceDialog
Var RadioInstall
Var RadioReinstall
Var RadioUninstall
Var ChoiceAction      ; "install" | "reinstall" | "uninstall" - 아래 선택 화면에서 정해짐

; ---------- UI 페이지 ----------
!define MUI_ABORTWARNING
!insertmacro MUI_PAGE_WELCOME

; 이미 설치되어 있을 때만 보여주는 선택 화면("설치/재설치/삭제") - 일반
; 사용자는 "프로그램 추가/제거"를 직접 찾아 삭제하는 걸 어려워해서, 이
; 설치 파일 하나로 새로 설치/기존 위에 새 버전 덮어쓰기/삭제만 하기를
; 전부 고를 수 있게 한다. 처음 설치하는 경우엔 이 화면 자체가 나타나지
; 않고 바로 설치가 진행된다(아래 ChoicePageCreate 참고).
Page custom ChoicePageCreate ChoicePageLeave

!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$DESKTOP\${DESKTOP_EXE_NAME}"
!define MUI_FINISHPAGE_RUN_TEXT "지금 바로 실행"
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "Korean"

; 이미 설치된 버전이 있는지 찾는다. 지금 방식(사용자 폴더, HKCU)을 먼저
; 보고, 없으면 예전 방식(관리자 권한 + Program Files, HKLM)도 확인한다.
Function FindPreviousInstall
  StrCpy $PrevInstallDir ""
  StrCpy $PrevIsLegacy ""

  ReadRegStr $0 HKCU "${APP_REG_KEY}" "InstallDir"
  ${If} $0 != ""
  ${AndIf} ${FileExists} "$0\uninstall.exe"
    StrCpy $PrevInstallDir $0
    Return
  ${EndIf}

  ; 예전(관리자 권한) 설치 흔적
  ReadRegStr $0 HKLM "${UNINSTALL_REG_KEY}" "UninstallString"
  ${If} $0 != ""
  ${AndIf} ${FileExists} "${LEGACY_INSTALL_DIR}\uninstall.exe"
    StrCpy $PrevInstallDir "${LEGACY_INSTALL_DIR}"
    StrCpy $PrevIsLegacy "1"
  ${EndIf}
FunctionEnd

; 기존 설치를 조용히(/S) 제거한다. _?= 옵션으로 제거 프로그램을 임시 위치로
; 복사하지 않고 그 자리에서 곧바로, 끝날 때까지 기다리며 실행한다.
Function RemovePreviousInstall
  ${If} $PrevIsLegacy == "1"
    ; 예전 버전은 관리자 권한으로 설치되어 있어, 지울 때도 Windows가 권한
    ; 요청 창을 띄운다. 사용자가 거기서 "아니오"를 눌러 제거가 안 되더라도
    ; 새 설치는 다른 폴더(사용자 폴더)로 진행되니 문제는 없다.
    MessageBox MB_OK|MB_ICONINFORMATION "예전 버전이 관리자 권한으로 설치되어 있어, 이를 지우는 동안 Windows가 권한을 묻는 창을 띄울 수 있습니다. '예'를 눌러주세요.$\r$\n$\r$\n(권한이 없어 지우지 못하더라도 새 버전 설치는 그대로 진행됩니다.)"
  ${EndIf}
  ExecWait '"$PrevInstallDir\uninstall.exe" /S _?=$PrevInstallDir'
FunctionEnd

Function ChoicePageCreate
  Call FindPreviousInstall
  ${If} $PrevInstallDir == ""
    ; 처음 설치하는 경우 - 고를 게 없으니 이 화면은 건너뛰고 바로 설치로 넘어간다.
    StrCpy $ChoiceAction "install"
    Abort
  ${EndIf}

  nsDialogs::Create 1018
  Pop $ChoiceDialog
  ${If} $ChoiceDialog == error
    Abort
  ${EndIf}

  !insertmacro MUI_HEADER_TEXT "이미 설치되어 있습니다" "어떻게 진행할지 선택해주세요."

  ${NSD_CreateLabel} 0 0u 100% 24u "안전보건 법령·고시 Monitoring이(가) 이 컴퓨터에 이미 설치되어 있습니다.$\r$\n(설치 위치: $PrevInstallDir)"
  Pop $0

  ${NSD_CreateRadioButton} 10u 32u 100% 12u "설치 - 삭제 없이 기존 파일 위에 새 버전을 덮어씁니다"
  Pop $RadioInstall

  ${NSD_CreateRadioButton} 10u 48u 100% 12u "재설치 - 기존 프로그램을 삭제한 뒤 새로 설치합니다 (권장)"
  Pop $RadioReinstall
  ${NSD_Check} $RadioReinstall

  ${NSD_CreateRadioButton} 10u 64u 100% 12u "삭제만 하기 - 새로 설치하지 않고 이 컴퓨터에서 프로그램만 제거합니다"
  Pop $RadioUninstall

  ${NSD_CreateLabel} 10u 88u 100% 24u "어떤 경우를 선택하시든, 그동안 모아둔 법령·고시 데이터(DB 파일)는 삭제되지 않고 그대로 유지됩니다."
  Pop $0

  nsDialogs::Show
FunctionEnd

Function ChoicePageLeave
  ${NSD_GetState} $RadioInstall $0
  ${If} $0 == ${BST_CHECKED}
    StrCpy $ChoiceAction "install"
  ${EndIf}
  ${NSD_GetState} $RadioReinstall $0
  ${If} $0 == ${BST_CHECKED}
    StrCpy $ChoiceAction "reinstall"
  ${EndIf}
  ${NSD_GetState} $RadioUninstall $0
  ${If} $0 == ${BST_CHECKED}
    StrCpy $ChoiceAction "uninstall"
  ${EndIf}

  ${If} $ChoiceAction == "uninstall"
    Call RemovePreviousInstall
    MessageBox MB_OK|MB_ICONINFORMATION "프로그램을 제거했습니다.$\r$\n$\r$\n그동안 모아둔 법령·고시 데이터(DB 파일)는 다음 위치에 그대로 남아 있습니다:$\r$\n$PrevInstallDir\app\backend$\r$\n$\r$\n필요 없으시면 이 폴더를 직접 삭제하셔도 됩니다."
    Quit
  ${ElseIf} $ChoiceAction == "reinstall"
    Call RemovePreviousInstall
  ${EndIf}
  ; "install"(삭제 없이 덮어쓰기)이면 아무것도 안 하고 바로 설치 페이지로 넘어간다.
FunctionEnd

; ---------- 설치 ----------
Section "Install"
  ; 사용자 폴더 설치 - $DESKTOP 등이 "모든 사용자"가 아니라 "지금 로그인한
  ; 사용자"의 폴더를 가리키게 한다.
  SetShellVarContext current

  ; 프로그램을 켜둔 채로 새 버전을 설치하는 경우를 대비해 먼저 종료시킨다.
  !insertmacro StopRunningApp

  SetOutPath "$INSTDIR\python"
  File /r "build\payload\python\*.*"

  SetOutPath "$INSTDIR\app"
  File /r /x "*.db" "build\payload\app\*.*"

  ; 설치 파일에 든 초기 DB는 이 PC에 DB가 아직 없을 때만 넣는다. 삭제/재설치
  ; 후에도 사용자가 모아둔 데이터가 남아 있으므로, 그걸 초기 DB로 덮어쓰면
  ; 등록한 법령·검토 이력이 재설치 순간 사라진다.
  SetOutPath "$INSTDIR\app\backend"
  ${IfNot} ${FileExists} "$INSTDIR\app\backend\safety_law_tracker.db"
    File /nonfatal "build\payload\app\backend\safety_law_tracker.db"
  ${EndIf}

  SetOutPath "$INSTDIR"
  File "launcher\launcher.exe"

  ; 바탕화면에는 실제 실행 파일을 그대로 하나 복사한다 (바로가기가 아님).
  SetOutPath "$DESKTOP"
  File "/oname=${DESKTOP_EXE_NAME}" "launcher\launcher.exe"
  SetOutPath "$INSTDIR"

  ; 바탕화면의 실행 파일이 설치 폴더를 찾아올 수 있도록 실제 설치 경로를
  ; 적어둔다(사용자 폴더 경로에는 계정 이름이 들어가 PC마다 달라서, 실행
  ; 파일에 미리 박아둘 수가 없다 - launcher/main.go의 resolveInstallDir 참고).
  WriteRegStr HKCU "${APP_REG_KEY}" "InstallDir" "$INSTDIR"

  ; 프로그램 추가/제거에 표시될 제거 항목 등록
  WriteUninstaller "$INSTDIR\uninstall.exe"
  WriteRegStr HKCU "${UNINSTALL_REG_KEY}" "DisplayName" "${APP_NAME}"
  WriteRegStr HKCU "${UNINSTALL_REG_KEY}" "UninstallString" "$\"$INSTDIR\uninstall.exe$\""
  WriteRegStr HKCU "${UNINSTALL_REG_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegDWORD HKCU "${UNINSTALL_REG_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINSTALL_REG_KEY}" "NoRepair" 1
SectionEnd

; ---------- 제거 ----------
; 법령 데이터(SQLite DB)는 사용자 데이터라, 여기서는 프로그램 파일(파이썬
; 실행환경 + 앱 소스코드)만 지우고 DB/설정(.env)은 그대로 남겨둔다 -
; 나중에 다시 설치해도 데이터가 유지되고, 실수로 지웠다가 법령 이력이
; 통째로 날아가는 일을 막기 위함이다.
Section "Uninstall"
  SetShellVarContext current

  ; 실행 중이면 먼저 종료 - 안 그러면 아래 Delete/RMDir이 조용히 실패해서
  ; 바탕화면 아이콘과 파이썬 폴더가 남는다.
  !insertmacro StopRunningApp

  Delete "$DESKTOP\${DESKTOP_EXE_NAME}"
  Delete "$INSTDIR\launcher.exe"
  Delete "$INSTDIR\server.log"
  Delete "$INSTDIR\uninstall.exe"

  RMDir /r "$INSTDIR\python"
  RMDir /r "$INSTDIR\app\frontend"
  RMDir /r "$INSTDIR\app\backend\app"
  Delete "$INSTDIR\app\backend\requirements.txt"
  Delete "$INSTDIR\app\backend\.env.example"
  ; $INSTDIR\app\backend\*.db 와 .env는 일부러 지우지 않는다.

  DeleteRegKey HKCU "${APP_REG_KEY}"
  DeleteRegKey HKCU "${UNINSTALL_REG_KEY}"

  ; /S(조용히 실행) 모드일 때는 안내창을 띄우지 않는다 - 재설치 과정에서
  ; 설치 파일이 기존 버전을 미리 지울 때도 이 제거 코드가 그대로 쓰이는데,
  ; 그때는 뒤이어 새 설치가 곧바로 진행되니 중간에 안내창이 뜨면 오히려
  ; 헷갈린다.
  IfSilent skip_uninstall_msg
    MessageBox MB_OK|MB_ICONINFORMATION "프로그램을 제거했습니다.$\r$\n$\r$\n그동안 모아둔 법령·고시 데이터(DB 파일)는 다음 위치에 그대로 남아 있습니다:$\r$\n$INSTDIR\app\backend$\r$\n$\r$\n필요 없으시면 이 폴더를 직접 삭제하셔도 됩니다."
  skip_uninstall_msg:

  ; 그래도 프로그램 파일이 남았다면(다른 프로그램이 붙잡고 있는 경우) 재부팅이나
  ; 문의 대신 할 수 있는 것을 안내한다.
  IfSilent done_leftover_check
  ${If} ${FileExists} "$INSTDIR\python\pythonw.exe"
    MessageBox MB_OK|MB_ICONEXCLAMATION "일부 파일이 사용 중이라 완전히 지우지 못했습니다.$\r$\n$\r$\n열려 있는 안전보건 프로그램 창을 모두 닫은 뒤, 설치 파일(install.exe)을 다시 실행해 '삭제만 하기'를 한 번 더 눌러주세요."
  ${EndIf}
  done_leftover_check:
SectionEnd
