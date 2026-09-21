@echo off
chcp 65001 >nul
rem 설치 파일 만들기 - 더블클릭 실행용. (build_local.ps1을 새 PowerShell 창에서 실행)
rem -ExecutionPolicy Bypass는 이 창 하나에만 적용되는 임시 옵션입니다(run.bat과 동일).
start "설치 파일 만들기" powershell.exe -NoExit -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_local.ps1"
