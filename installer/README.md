# Windows 설치 파일 만들기

`install.exe`를 만드는 빌드 파이프라인입니다. 이 설치 파일을
실행하면 사용자 PC의
**`C:\Users\<사용자>\AppData\Local\Programs\SafetyLawMonitor\`** 안에
파이썬 실행환경 + 앱 소스가 통째로 설치되고, **바탕화면에는 실행용 `.exe`
파일 하나만** 남습니다(바로가기가 아니라 실제 실행 파일). 사용자 PC에
파이썬이 설치되어 있지 않아도 바로 실행되고, **관리자 권한도 필요 없습니다**
(설치할 때 권한 요청 창이 뜨지 않음).

> **사용자 폴더에 설치하는 이유** - 예전에는 `C:\Program Files\`에
> 설치했는데 두 가지 문제가 있었습니다. (1) 설치할 때마다 관리자 권한이
> 필요해 회사 PC에서는 설치가 막힐 수 있고, (2) 더 중요하게는 Windows가
> `Program Files` 폴더를 쓰기 금지로 보호하기 때문에, 설치는 되더라도
> 이후 일반 권한으로 실행되는 프로그램이 법령 데이터 DB
> (`app\backend\safety_law_tracker.db`)에 기록을 못 해 서버가 시작하다
> 죽습니다. 사용자 폴더 설치로 두 문제를 모두 없앴습니다(VS Code, Zoom 등이
> 쓰는 것과 같은 방식).

## IT를 모르는 사람에게 배포할 때 (요약)

1. 아래 둘 중 한 방법으로 `install.exe`를 만든다.
   - **GitHub에서 버튼으로 만들기(권장)**: 저장소 `Actions` 탭 >
     "Windows 설치 파일 빌드" > `Run workflow`. 끝나면 결과 페이지 아래
     Artifacts에서 내려받는다. 자세한 건
     `.github/workflows/build-installer.yml` 맨 위 주석 참고.
   - **직접 빌드**: 아래 "한 번에 빌드하기" 참고(Linux 환경 필요).
2. **OC 키를 꼭 넣어서 빌드한다**(`--oc` 옵션 또는 저장소 시크릿
   `LAW_API_OC`). 넣지 않으면 받는 사람이 대시보드 설정 화면에서 키를 직접
   입력해야 하고, 그 전까지는 예시 데이터(데모 모드)로만 보입니다.
3. 받는 사람에게 **`install.exe` 와 `installer/설치안내.txt`
   두 파일**을 함께 보낸다. `설치안내.txt`는 IT를 전혀 모르는 사람 기준으로
   쓴 설치·사용 설명서입니다(특히 처음 실행할 때 뜨는 "Windows의 PC 보호"
   경고창을 넘기는 방법이 들어 있습니다 - 코드 서명 인증서가 없는 설치
   파일은 이 경고가 반드시 뜹니다).

## 한 번에 빌드하기

```bash
installer/build_installer.sh                      # 빈 DB로 빌드 (설치 후 첫 실행부터 캐시를 새로 받음)
installer/build_installer.sh --oc <OC키>           # 국가법령정보센터 OC 키를 미리 넣어서 빌드 (배포 시 권장)
installer/build_installer.sh --db path/to/safety_law_tracker.db   # 미리 캐시해둔 DB를 포함해서 빌드
installer/build_installer.sh --skip-fetch          # 파이썬/wheel을 다시 받지 않고 재빌드(반복 작업용)
```

결과물: `installer/build/install.exe` (DB 포함 시 약 85MB)

`--oc`로 넣은 키는 배포판 `backend/.env`의 `LAW_API_OC` 값으로 들어갑니다.
받는 사람이 설정 화면에서 다른 키로 바꾸는 것도 그대로 가능합니다.

## 미리 캐시된 DB로 배포하기 (대기시간 단축)

설치 직후 첫 실행부터 바로 쓸 수 있게 하려면, 실제 OC 키로 동작하는
환경에서 대시보드 > 설정 > **전체 법령 자동 캐시**의 "지금 바로 시작"을
한 번 돌려 `backend/safety_law_tracker.db`를 완전히 채운 뒤, 그 파일
경로를 `--db`로 넘겨서 빌드하세요. 이 DB가 설치 파일 안에 그대로 들어가
설치 직후부터 캐시가 채워진 상태로 시작합니다(그 뒤로는 공포번호가 바뀐
것만 증분으로 갱신되어 계속 빠릅니다).

## 필요한 도구

- `bash`, `curl`, `unzip`
- `python3` + `pip` (Windows용 wheel을 내려받는 데만 씀 - 실행 환경 자체와는 무관)
- `go` (`GOOS=windows GOARCH=amd64`로 바탕화면 실행 파일을 크로스 컴파일)
- `makensis` (NSIS) - Ubuntu/Debian: `sudo apt-get install nsis`
- `go-winres` (exe 아이콘/버전 정보 리소스 임베딩) - 없으면
  `build_installer.sh`가 자동으로 `go install`해서 받아온다.

네트워크: `nuget.org`(공식 파이썬 재배포판), `pypi.org`(Windows용
라이브러리 wheel), `proxy.golang.org`(Go 모듈 - 트레이 아이콘 라이브러리와
아이콘 임베딩 도구)에 접근할 수 있어야 합니다. (python.org 직접 다운로드는
막혀 있는 네트워크 환경이 있어, 파이썬 재단이 NuGet에 공식 배포하는 동일한
CPython 재배포판을 대신 사용합니다.)

## 어떻게 동작하는지

1. `scripts/fetch_python_runtime.sh` - nuget.org의 공식 `python` 패키지에서
   Windows용 Python(그대로 재배포 가능한 정식 빌드, python.exe/표준
   라이브러리/sqlite3 포함)을 받아 `build/payload/python`에 푼다.
2. `scripts/fetch_wheels.sh` - 빌드 때 `backend/requirements.txt`에서 자동으로 만든 목록(
   requirements.txt와 동일하나 `uvicorn[standard]`의 유닉스 전용 `uvloop`
   의존성만 뺐다 - Windows에는 애초에 존재하지 않는 패키지라 `pip
   download --platform win_amd64`가 marker를 잘못 평가해 실패하는 pip의
   알려진 한계를 피하기 위함)에 있는 패키지들의 win_amd64 wheel을 PyPI에서
   받아 `site-packages`에 풀어 넣는다.
3. `scripts/stage_app.sh` - `backend/`, `frontend/` 소스를
   `build/payload/app`에 복사하고, 배포판 기본 `.env`
   (`FULL_LAW_CACHE_ENABLED=true`)를 만든다.
4. `launcher/main.go` - 바탕화면 실행 파일. 실행되면 먼저 설치 폴더를
   찾는다(실행 파일 옆 -> 설치 프로그램이 `HKCU\Software\SafetyLawMonitor`에
   적어둔 경로 -> 기본 위치 -> 예전 `Program Files` 위치 순). 사용자 폴더
   경로에는 계정 이름이 들어가 PC마다 다르기 때문에, 예전처럼 경로를 실행
   파일에 박아둘 수 없어서다. 그 다음 서버가 떠 있는지
   확인하고, 없으면 콘솔 창 없이(`pythonw.exe` + `CREATE_NO_WINDOW`)
   백그라운드로 `-m uvicorn ...`을 띄운 뒤 `/api/health`가 응답할 때까지
   기다렸다가 기본 브라우저를 연다(로그는 설치 폴더의 `server.log`에 남음).
   서버/브라우저를 여는 핵심 동작은 트레이 아이콘 등록 성공 여부와
   무관하게 항상 먼저 끝내둔다. 그 위에 `getlantern/systray`로 작업표시줄
   트레이 아이콘("대시보드 열기"/"종료" 메뉴)을 얹어, 실행해도 검은 콘솔
   창이 뜨지 않고 일반 프로그램처럼 동작한다. 같은 프로그램이 이미 떠
   있으면(이름 붙은 뮤텍스로 확인) 트레이 아이콘을 새로 만들지 않고
   브라우저만 다시 연다.
5. `setup.nsi` - 위 결과물들을
   `%LOCALAPPDATA%\Programs\SafetyLawMonitor\`에 설치하고, 바탕화면에 실행
   파일을 복사하는 NSIS 스크립트(`RequestExecutionLevel user` - 관리자 권한
   요청 창이 뜨지 않는다). 설치/제거 전에 실행 중인 프로그램을 먼저 종료시킨다
   (Windows는 실행 중인 파일을 지우거나 덮어쓰지 못해서, 이게 없으면 프로그램을
   켜둔 채 삭제했을 때 바탕화면 아이콘과 파이썬 폴더가 남는다). 예전
   버전(관리자 권한 + Program Files)이 설치된 PC도 알아보고 함께 정리한다.
   제거 시에는 프로그램 파일(파이썬/소스코드)만 지우고 `*.db`/`.env`는 남겨,
   실수로 법령 데이터가 통째로 날아가지 않게 했다.

## 검증한 것 / 못 한 것

이 빌드 환경은 Linux라 실제 Windows에서 설치 파일을 직접 실행해볼 수는
없습니다. 대신 Wine(Windows 에뮬레이션, 32/64비트 모두 준비해서)으로 설치
파일 실행부터 삭제까지 한 바퀴를 확인했습니다:

- 번들된 `python.exe`/`pythonw.exe`가 정상 동작 (`python --version` 등)
- fastapi/uvicorn/SQLAlchemy/APScheduler 등 모든 의존성이 정상 import
- 실제 FastAPI 서버가 떠서 `/api/health`에 정상 응답
- **설치 파일 실행 -> 사용자 폴더
  (`C:\users\<사용자>\AppData\Local\Programs\SafetyLawMonitor`)에 설치되고,
  바탕화면에 한글 이름의 실행 파일이 복사되며,
  `HKCU\Software\SafetyLawMonitor\InstallDir`에 설치 경로가 기록되는 것까지 확인**
- **바탕화면 실행 파일을 실행하면 레지스트리로 설치 폴더를 찾아 서버를 띄우고,
  `/api/health`가 `{"status":"ok","demo_mode":false}`로 응답하며(=`--oc`로 넣은
  키가 실제로 먹는다는 뜻), 대시보드 HTML이 200으로 내려오는 것까지 확인**
- **DB 파일(`app/backend/safety_law_tracker.db`)이 설치 폴더 안에 정상적으로
  생성되는 것 확인** - 예전 `Program Files` 설치에서는 이 쓰기가 권한 때문에
  막혔을 위치다
- **프로그램이 켜진 상태에서 제거를 실행해도, 서버가 먼저 종료되고 파이썬
  폴더·바탕화면 아이콘·실행 파일이 모두 지워지며 DB와 `.env`만 남는 것 확인**
  (이 종료 처리를 넣기 전에는 실제로 바탕화면 아이콘과 파이썬 폴더가 남는 걸
  재현했다)
- 트레이 아이콘 등록: 화면(디스플레이)이 없는 환경에서 실행했더니
  `getlantern/systray`가 등록에 실패하는 걸 확인했다 - 그런데 이때도
  서버 실행/브라우저 열기 같은 핵심 기능은 (트레이 등록 이전에 먼저
  끝내두는 구조라) 전혀 영향을 안 받는 것까지 확인했다. 이후 가상
  디스플레이(Xvfb)를 붙여서 다시 실행하니 트레이 등록도 에러 없이
  끝났다 - 실제 Windows는 로그인한 사용자라면 항상 화면이 있는
  세션이라, 이 실패는 "화면이 아예 없는" 테스트 환경에서만 나타나는
  것으로 보인다(그래도 혹시를 대비해 핵심 기능은 트레이와 분리해뒀다).

이 과정에서 실제 버그 세 가지를 발견해 고쳤습니다:
1. `zoneinfo.ZoneInfo("Asia/Seoul")`가 Windows에는 기본으로 없는 IANA
   시간대 데이터베이스를 필요로 해, 그대로 배포하면 서버가 아예 시작조차
   못 하고 죽는 문제 (`tzdata` 패키지를 `backend/requirements.txt`에도
   추가해서 모든 배포 방식에서 함께 고쳤다).
2. (초기 버전) 서버를 새 콘솔 창에서 띄워 검은 창이 계속 떠 있던 문제 -
   `pythonw.exe` + 트레이 아이콘 방식으로 바꿔 해결했다.
3. 프로그램을 켜둔 채 삭제하면 바탕화면 아이콘과 파이썬 폴더가 지워지지
   않고 남는 문제 - 설치/제거 전에 실행 중인 프로세스를 먼저 종료하도록
   고쳤다.

다만 다음은 실제 Windows에서 직접 확인이 필요합니다:

- 처음 실행할 때 뜨는 SmartScreen("Windows의 PC 보호") 경고 - 코드 서명
  인증서가 없어 반드시 뜬다. `설치안내.txt`에 넘기는 방법을 적어뒀지만,
  실제 문구가 Windows 버전마다 조금씩 다를 수 있다.
- 실제 사용자 세션에서 트레이 아이콘이 정상적으로 보이는지, 아이콘
  모양이 의도대로 나오는지
- 실제 브라우저가 자동으로 열리는지
- 제거할 때 쓰는 `taskkill`/PowerShell 정리 명령이 실제 Windows에서
  의도대로 동작하는지 (Wine에는 PowerShell이 없어 `taskkill` 경로만
  확인됐다. 실제 Windows에서는 PowerShell 정리가 한 겹 더 동작한다.)
- 회사 백신/보안 프로그램이 서명 없는 설치 파일을 차단하는 경우
  (이건 IT 담당자의 허용이 필요할 수 있다)
