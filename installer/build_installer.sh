#!/usr/bin/env bash
# 배포용 Windows 설치 파일(SafetyLawMonitor_Setup.exe)을 만드는 전체 과정을
# 순서대로 실행한다.
#
# 사용법:
#   installer/build_installer.sh [--db <미리 캐시해둔 safety_law_tracker.db 경로>]
#                                [--oc <국가법령정보센터 OC 키>] [--skip-fetch]
#
#   --db <path>     이미 "전체 법령 자동 캐시"를 한 번 돌려서 다 채워둔
#                   safety_law_tracker.db 파일을 설치 파일 안에 포함시킨다.
#                   생략하면 빈 DB로 시작해서, 설치 후 첫 실행 때부터
#                   캐시를 새로 받아야 한다(대기시간이 길어짐).
#   --oc <key>      국가법령정보센터 OpenAPI의 OC 키를 설치 파일 안에 미리
#                   넣어둔다. IT를 잘 모르는 사람에게 배포할 때 권장 -
#                   받는 사람이 설정 화면에서 키를 입력하는 과정 없이 설치
#                   직후부터 실제 법령 데이터로 바로 쓸 수 있다. 생략하면
#                   받는 사람이 직접 입력하기 전까지 데모 모드로 동작한다.
#   --skip-fetch    Python 실행환경/wheel을 다시 받지 않고 이미 받아둔
#                   build/payload/python을 그대로 재사용한다(재빌드 반복
#                   시 시간 절약용).
#
# 필요한 도구: bash, curl, unzip, python3(+pip), go, makensis(NSIS).
#   (go-winres는 없으면 이 스크립트가 자동으로 go install 해서 받아온다.)
# 필요한 네트워크: nuget.org(파이썬 실행환경), pypi.org(라이브러리 wheel),
#   proxy.golang.org(Go 모듈 - 트레이 아이콘 라이브러리/아이콘 임베딩 도구).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALLER_DIR="$REPO_ROOT/installer"
BUILD_DIR="$INSTALLER_DIR/build"
PAYLOAD_PY="$BUILD_DIR/payload/python"
PAYLOAD_APP="$BUILD_DIR/payload/app"

DB_PATH=""
LAW_API_OC=""
SKIP_FETCH=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --db) DB_PATH="$2"; shift 2 ;;
    --oc) LAW_API_OC="$2"; shift 2 ;;
    --skip-fetch) SKIP_FETCH="1"; shift ;;
    *) echo "알 수 없는 옵션: $1" >&2; exit 1 ;;
  esac
done

if [[ -n "$DB_PATH" && ! -f "$DB_PATH" ]]; then
  echo "지정한 DB 파일을 찾을 수 없습니다: $DB_PATH" >&2
  exit 1
fi

echo "[1/5] Python 실행환경 준비"
if [[ -n "$SKIP_FETCH" && -f "$PAYLOAD_PY/python.exe" ]]; then
  echo "  --skip-fetch: 기존 $PAYLOAD_PY 재사용"
else
  bash "$INSTALLER_DIR/scripts/fetch_python_runtime.sh" "$PAYLOAD_PY"
fi

echo "[2/5] 라이브러리(wheel) 준비"
if [[ -n "$SKIP_FETCH" && -d "$PAYLOAD_PY/Lib/site-packages/fastapi" ]]; then
  echo "  --skip-fetch: 기존 site-packages 재사용"
else
  # backend/requirements.txt에서 자동으로 만든다(별도 복사본을 두면 패키지를 추가할 때
  # 갱신을 빠뜨려 설치본이 시작하다 죽는다 - pypdf/python-multipart 누락으로 실제 발생).
  # uvicorn[standard] 대신 순정 uvicorn만 쓴다: standard의 uvloop는 유닉스 전용이라
  # Windows용 wheel이 없는데, `pip download --platform win_amd64`는 조건부 의존성을
  # 빌드 OS(Linux) 기준으로 평가해 uvloop를 요구해버린다(pip의 알려진 한계).
  # 이 앱은 웹소켓/--reload를 배포판에서 쓰지 않아 순정 uvicorn으로 충분하다.
  WIN_REQ="$BUILD_DIR/requirements-windows.txt"
  sed 's/uvicorn\[standard\]/uvicorn/' "$REPO_ROOT/backend/requirements.txt" > "$WIN_REQ"
  bash "$INSTALLER_DIR/scripts/fetch_wheels.sh" "$WIN_REQ" "$PAYLOAD_PY"
fi

echo "[3/5] 앱 소스 준비"
bash "$INSTALLER_DIR/scripts/stage_app.sh" "$PAYLOAD_APP" "$LAW_API_OC"

if [[ -n "$DB_PATH" ]]; then
  echo "  미리 캐시해둔 DB 포함: $DB_PATH"
  cp "$DB_PATH" "$PAYLOAD_APP/backend/safety_law_tracker.db"
fi

echo "[4/6] 바탕화면 실행 파일 아이콘/버전 정보 리소스 준비"
if ! command -v go-winres >/dev/null 2>&1; then
  echo "  go-winres가 없어 설치합니다..."
  GOBIN="$(go env GOPATH)/bin" go install github.com/tc-hib/go-winres@latest
  # Windows(Git Bash)에서는 GOPATH가 C:... 형식이라 PATH에 그대로 못 붙여 cygpath로 바꾼다.
  WINRES_DIR="$(go env GOPATH)/bin"
  if command -v cygpath >/dev/null 2>&1; then WINRES_DIR="$(cygpath -u "$WINRES_DIR")"; fi
  export PATH="$WINRES_DIR:$PATH"
fi
( cd "$INSTALLER_DIR/launcher" && go-winres make --arch amd64 )

echo "[5/6] 바탕화면 실행 파일(launcher.exe) 빌드"
# -s -w: 디버그 심볼/DWARF 정보를 빼고 빌드한다(실행 파일이 9MB -> 6MB로
# 줄어 설치 파일 용량도 그만큼 작아진다. 사용자 PC에서 디버거를 붙일 일은
# 없고, 문제 확인은 서버 로그(server.log)로 한다).
( cd "$INSTALLER_DIR/launcher" && \
  GOOS=windows GOARCH=amd64 CGO_ENABLED=0 go build -ldflags "-H=windowsgui -s -w" -o launcher.exe . )

echo "[6/6] 설치 프로그램(NSIS) 빌드"
( cd "$INSTALLER_DIR" && makensis -INPUTCHARSET UTF8 setup.nsi )

echo
echo "완료: $BUILD_DIR/SafetyLawMonitor_Setup.exe"
