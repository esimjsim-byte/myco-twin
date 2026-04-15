@echo off
setlocal
chcp 65001 >nul

title Tapo Monitor - 자동 시작 해제

cd /d "%~dp0"
set "PROJECT_DIR=%CD%"
set "TASK_NAME=TapoMonitor"
set "VBS_WRAPPER=%PROJECT_DIR%\run-tapo-monitor.vbs"

echo ==========================================================
echo   Tapo Monitor - 자동 시작 해제
echo ==========================================================
echo.

REM 실행 중인 작업이 있다면 먼저 종료
schtasks /End /TN "%TASK_NAME%" >nul 2>nul

REM 등록된 작업 삭제
schtasks /Delete /TN "%TASK_NAME%" /F
if errorlevel 1 (
    echo [알림] 해당 이름의 작업이 등록되어 있지 않습니다.
) else (
    echo [완료] Task Scheduler 에서 "%TASK_NAME%" 작업이 제거되었습니다.
)

REM VBS 래퍼 정리
if exist "%VBS_WRAPPER%" (
    del /q "%VBS_WRAPPER%"
    echo [완료] 래퍼 파일 삭제: %VBS_WRAPPER%
)

echo.
echo   참고: 이미 실행 중인 node.exe 프로세스가 있다면
echo         아래 명령으로 수동 종료할 수 있습니다:
echo           taskkill /IM node.exe /F
echo.
pause
endlocal
