@echo off
chcp 65001 >nul
rem 안전보건 법령·고시 개정 추적 시스템 - 더블클릭 실행용
rem
rem PowerShell의 "실행 정책"을 시스템/계정에 영구히 바꾸지 않습니다.
rem 아래 -ExecutionPolicy Bypass는 이 배치파일이 새로 띄우는 PowerShell
rem "이 창 하나"에만 적용되는 임시 허용이고, 창을 닫으면 사라집니다.
rem (Set-ExecutionPolicy처럼 레지스트리에 저장되는 게 아니라, 이 실행에만
rem  적용되는 명령줄 옵션입니다 - 회사 컴퓨터 보안 정책에 영향 없음)
rem
rem run.ps1을 이 cmd 창에서 직접 실행하지 않고, 별도의 새 PowerShell 창으로
rem 띄웁니다. cmd.exe가 배치파일 한 줄로 powershell.exe를 직접 실행하면,
rem 서버 실행 중 Ctrl+C를 눌렀을 때 cmd.exe가 자체적으로
rem "Terminate batch job (Y/N)?"을 물어보면서 창이 통째로 닫혀버리는
rem 문제가 있습니다(run.ps1이 Ctrl+C 후 재시작 메뉴를 띄우도록 만들어도,
rem cmd.exe가 그 전에 창을 죽여버려서 소용이 없음). 새 창에서 띄우면 이
rem cmd.exe 창은 바로 할 일이 끝나고, 실제 서버는 순수 PowerShell 창에서
rem 실행되어 Ctrl+C를 눌러도 그 창 안에서 재시작 메뉴로 넘어갑니다.

rem -NoExit: run.ps1에서 예상치 못한 오류가 나서 스크립트가 중간에
rem 끝나버려도 창이 그 즉시 닫히지 않고 남아있게 합니다. (이게 없으면
rem 오류 메시지를 볼 새도 없이 창이 사라져서 뭐가 문제인지 알 수가 없음)
start "안전보건 법령·고시 모니터링" powershell.exe -NoExit -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1"
