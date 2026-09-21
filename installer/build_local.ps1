# 설치 파일(SafetyLawMonitor_Setup.exe)을 이 PC에서 한 번에 만든다.
# 하는 일: (1) Go/NSIS/Python이 없으면 winget으로 설치 (2) backend\safety_law_tracker.db가 있으면
# 법령 마스터를 뺀 배포용 DB를 만들어 포함(없으면 DB 없이 빌드) (3) installer/build_installer.sh 실행.
# 사내 보안 프록시 때문에 필요한 우회(curl 인증서 해지 확인, pip 신뢰 호스트)는
# 이번 실행에만 환경변수로 적용하고 PC 전역 설정은 건드리지 않는다.
param([switch]$SkipFetch)   # 파이썬/wheel을 이미 받아둔 경우 재사용(재빌드용)
$ErrorActionPreference = "Stop"

# 콘솔 "빠른 편집 모드"를 끈다. 켜져 있으면 창을 마우스로 클릭(글자 선택)하는 순간
# 프로그램 출력이 멈춰서 빌드가 멈춘 것처럼 보이고, Esc/Enter를 눌러야 다시 흐른다.
try {
    if (-not ('Win32.ConMode' -as [type])) {
        Add-Type -Namespace Win32 -Name ConMode -MemberDefinition @'
[DllImport("kernel32.dll")] public static extern IntPtr GetStdHandle(int n);
[DllImport("kernel32.dll")] public static extern bool GetConsoleMode(IntPtr h, out uint m);
[DllImport("kernel32.dll")] public static extern bool SetConsoleMode(IntPtr h, uint m);
'@
    }
    $hIn = [Win32.ConMode]::GetStdHandle(-10)   # STD_INPUT_HANDLE
    $mode = 0
    if ([Win32.ConMode]::GetConsoleMode($hIn, [ref]$mode)) {
        # 0x40 = ENABLE_QUICK_EDIT_MODE 끄기, 0x80 = ENABLE_EXTENDED_FLAGS(이게 있어야 반영됨)
        [void][Win32.ConMode]::SetConsoleMode($hIn, [uint32](([int]$mode -bor 0x80) -band (-bnot 0x40)))
    }
} catch { }   # 콘솔이 아니거나 실패해도 빌드에는 영향 없음
$installer = $PSScriptRoot
$root = Split-Path -Parent $installer
$build = Join-Path $installer "build"
New-Item -Force -ItemType Directory $build | Out-Null

function Add-ToolDirs {
    foreach ($d in "C:\Program Files\Go\bin", "C:\Program Files (x86)\NSIS", "C:\Program Files\NSIS") {
        if ((Test-Path $d) -and ($env:Path -notlike "*$d*")) { $env:Path += ";$d" }
    }
}
function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
    Add-ToolDirs
}

Add-ToolDirs
foreach ($t in @(@{ cmd = "go"; id = "GoLang.Go" }, @{ cmd = "makensis"; id = "NSIS.NSIS" })) {
    if (Get-Command $t.cmd -ErrorAction SilentlyContinue) { continue }
    Write-Host "[준비] $($t.id) 설치 중... (관리자 권한 확인 창이 뜨면 허용해주세요)"
    winget install --id $t.id --exact --silent --accept-source-agreements --accept-package-agreements
    Refresh-Path
    if (-not (Get-Command $t.cmd -ErrorAction SilentlyContinue)) {
        throw "$($t.id) 설치 후에도 $($t.cmd) 를 찾을 수 없습니다. 이 창을 닫고 다시 실행해보세요."
    }
}

$git = (Get-Command git -ErrorAction Stop).Source
$bash = Join-Path (Split-Path (Split-Path $git)) "bin\bash.exe"
if (-not (Test-Path $bash)) { throw "Git Bash를 찾을 수 없습니다: $bash" }

# 실제로 실행되는 Python 3을 찾는다(Microsoft Store 안내용 가짜 python은 제외).
# 빌드(pip으로 wheel 받기)에 어차피 필요하므로 .venv 대신 PC에 설치된 Python을 쓴다.
function Find-Python {
    foreach ($n in "python", "python3") {
        $c = Get-Command $n -ErrorAction SilentlyContinue
        if ($c) {
            & $c.Source -c "import sqlite3, pip" 2>$null
            if ($LASTEXITCODE -eq 0) { return $c.Source }
        }
    }
}
$py = Find-Python
if (-not $py) {
    Write-Host "[준비] Python.Python.3.12 설치 중... (관리자 권한 확인 창이 뜨면 허용해주세요)"
    winget install --id Python.Python.3.12 --exact --silent --accept-source-agreements --accept-package-agreements
    Refresh-Path
    $py = Find-Python
    if (-not $py) { throw "Python 설치 후에도 실행되는 python을 찾을 수 없습니다. 이 창을 닫고 다시 실행해보세요." }
}

$srcDb = Join-Path $root "backend\safety_law_tracker.db"
$distDb = Join-Path $build "dist.db"
Remove-Item $distDb -ErrorAction SilentlyContinue
$buildArgs = @("installer/build_installer.sh")
if (Test-Path $srcDb) {
    Write-Host "[1/2] 배포용 DB 만드는 중 (법령 마스터 제외)"
    & $py (Join-Path $installer "scripts\make_dist_db.py") $srcDb $distDb
    if ($LASTEXITCODE -ne 0) { throw "배포용 DB 생성 실패" }
    Write-Host "  ※ 이 DB에는 OC/KOSHA 인증키가 들어 있어 설치 파일을 받는 사람 모두 같은 키를 쓰게 됩니다."
    $buildArgs += @("--db", "installer/build/dist.db")
}
else {
    Write-Host "[1/2] backend\safety_law_tracker.db 가 없어 DB를 포함하지 않고 만듭니다."
    Write-Host "  ※ 받는 사람은 빈 상태로 시작하며, 설정 화면에서 OC 키를 직접 입력해야 실제 법령 데이터로 동작합니다."
}

$curlHome = Join-Path $build "curlhome"
New-Item -Force -ItemType Directory $curlHome | Out-Null
Set-Content (Join-Path $curlHome ".curlrc") "ssl-no-revoke" -Encoding ascii
$env:CURL_HOME = $curlHome
$env:PIP_TRUSTED_HOST = "pypi.org files.pythonhosted.org"
$env:PYTHONUTF8 = "1"   # pip이 UTF-8 한글 주석이 든 requirements를 cp949로 읽다 실패하는 것을 막는다

Write-Host "[2/2] 설치 파일 빌드 (10~20분 걸릴 수 있습니다)"
Set-Location $root
if ($SkipFetch) { $buildArgs += "--skip-fetch" }
& $bash @buildArgs
if ($LASTEXITCODE -ne 0) { throw "빌드 실패 (위 로그 확인)" }

$exe = Join-Path $build "SafetyLawMonitor_Setup.exe"
Write-Host ("`n완료: {0} ({1:N0} MB)" -f $exe, ((Get-Item $exe).Length / 1MB))
explorer.exe $build
