@echo off
setlocal
chcp 65001 >nul

title Tapo Monitor Installer

echo ==========================================================
echo   Tapo Monitor - 설치 프로그램
echo ==========================================================
echo.

REM 배치 파일이 놓인 폴더에서 실행
cd /d "%~dp0"

REM ---------- 0) 사전 점검: git / node ----------
where git >nul 2>nul
if errorlevel 1 (
    echo [오류] git 이 설치되어 있지 않습니다.
    echo        https://git-scm.com/download/win 에서 설치한 뒤 다시 실행해주세요.
    echo.
    pause
    exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
    echo [오류] Node.js(npm) 이 설치되어 있지 않습니다.
    echo        https://nodejs.org 에서 LTS 버전을 설치한 뒤 다시 실행해주세요.
    echo.
    pause
    exit /b 1
)

REM ---------- 설정 ----------
set "REPO_URL=https://github.com/esimjsim-byte/myco-twin.git"
set "BRANCH=claude/setup-tapo-monitor-project-skv4V"
set "CLONE_DIR=myco-twin"
set "PROJECT_DIR=%CD%\%CLONE_DIR%\tapo-monitor"

REM ---------- 현재 위치 감지 ----------
REM install.bat 이 이미 tapo-monitor 프로젝트 폴더 안에서 실행된 경우
REM (= package.json 에 "tapo-monitor" 가 있고 src\index.ts 가 존재) 추가 clone 하지 않는다.
set "IS_IN_PROJECT=0"
if exist "package.json" if exist "src\index.ts" (
    findstr /c:"\"name\": \"tapo-monitor\"" package.json >nul 2>nul
    if not errorlevel 1 set "IS_IN_PROJECT=1"
)

REM 부모 기준: install.bat 이 myco-twin\ 안(= tapo-monitor 상위) 에서 실행된 경우
set "IS_IN_REPO_ROOT=0"
if "%IS_IN_PROJECT%"=="0" if exist "tapo-monitor\package.json" if exist "tapo-monitor\src\index.ts" (
    set "IS_IN_REPO_ROOT=1"
)

REM ---------- 1) 저장소 준비 ----------
if "%IS_IN_PROJECT%"=="1" (
    echo [1/3] 현재 폴더가 tapo-monitor 프로젝트입니다. clone 을 건너뜁니다.
    set "PROJECT_DIR=%CD%"
    REM 이미 git 관리 중이면 최신 브랜치로 갱신 시도
    if exist "..\.git" (
        pushd ..
        git fetch origin %BRANCH% >nul 2>nul
        git checkout %BRANCH% >nul 2>nul
        git pull origin %BRANCH%
        popd
    )
) else if "%IS_IN_REPO_ROOT%"=="1" (
    echo [1/3] 이미 clone 된 myco-twin 폴더 안입니다. git pull 로 갱신합니다.
    git fetch origin %BRANCH%
    git checkout %BRANCH%
    git pull origin %BRANCH%
    set "PROJECT_DIR=%CD%\tapo-monitor"
) else if exist "%CLONE_DIR%\.git" (
    echo [1/3] 기존 저장소가 발견되어 git pull 로 갱신합니다.
    pushd "%CLONE_DIR%"
    git fetch origin %BRANCH%
    git checkout %BRANCH%
    git pull origin %BRANCH%
    popd
) else (
    echo [1/3] GitHub 저장소를 clone 합니다...
    git clone -b %BRANCH% %REPO_URL% %CLONE_DIR%
)
if errorlevel 1 (
    echo [오류] git clone/pull 실패. 네트워크 또는 권한을 확인해주세요.
    echo.
    pause
    exit /b 1
)
echo.

REM ---------- 2) npm install ----------
echo [2/3] npm 패키지를 설치합니다 (수 분 소요)...
pushd "%PROJECT_DIR%"
call npm install
if errorlevel 1 (
    echo [오류] npm install 실패.
    popd
    pause
    exit /b 1
)
echo.

REM ---------- 3) .env 생성 ----------
echo [3/3] .env 파일을 생성합니다...
if exist ".env" (
    echo       이미 .env 가 존재하여 유지합니다 ^(덮어쓰지 않음^).
) else (
    >  ".env" echo TAPO_EMAIL=hw.kwon@sinsungo.co.kr
    >> ".env" echo TAPO_PASSWORD=123456789
    >> ".env" echo HUB_IP=아직모름
    >> ".env" echo PLUG_IP_1=아직모름
    >> ".env" echo PLUG_IP_2=아직모름
    >> ".env" echo.
    >> ".env" echo TEMP_MAX=28
    >> ".env" echo TEMP_MIN=18
    >> ".env" echo HUMID_MAX=95
    >> ".env" echo HUMID_MIN=50
    >> ".env" echo POLL_INTERVAL_MS=60000
    >> ".env" echo.
    >> ".env" echo PLC_IP=192.168.0.50
    >> ".env" echo PLC_PORT=502
    >> ".env" echo PLC_COIL_FCU=1
    >> ".env" echo PLC_COIL_HUMIDIFIER=2
    >> ".env" echo PLC_COIL_VENTILATION=3
    echo       .env 생성 완료.
)

REM ---------- 빌드 ----------
echo.
echo       TypeScript 빌드...
call npm run build
if errorlevel 1 (
    echo [경고] 빌드 실패. 나중에 'npm run build' 를 직접 실행해주세요.
)
popd

echo.
echo ==========================================================
echo   설치가 완료되었습니다!
echo ==========================================================
echo.
echo   프로젝트 위치 : %PROJECT_DIR%
echo.
echo   다음 단계:
echo     1) 위 폴더의 .env 를 열어 실제 비밀번호와 IP 를 입력하세요.
echo     2) 명령 프롬프트에서:
echo          cd /d "%PROJECT_DIR%"
echo          npm start
echo.
pause
endlocal
