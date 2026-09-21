$ErrorActionPreference = "Continue"

Set-Location $PSScriptRoot

# run.bat이 이미 이 PowerShell 프로세스 전체를 -ExecutionPolicy Bypass로
# 띄우지만, 사용자가 run.ps1을 직접(.\run.ps1) 실행했을 때도 venv의
# Activate.ps1이 "이 시스템에서 스크립트를 실행할 수 없습니다" 오류로
# 막히지 않도록 이 프로세스 하나에만 한 번 더 걸어둔다. 레지스트리에
# 저장되는 영구 설정이 아니라 이 창을 닫으면 사라지는 임시 허용이다.
try { Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force -ErrorAction SilentlyContinue } catch {}

function Find-Python {
    foreach ($cmd in @("python", "py")) {
        $found = Get-Command $cmd -ErrorAction SilentlyContinue
        if ($found) { return $found.Source }
    }
    return $null
}

# 가상환경이 없으면 만들고, 필요한 패키지가 없으면 설치하고, .env가 없으면
# 예시 파일을 복사해둔다 - 최초 설치를 따로 안 해도 run.bat 더블클릭
# 한 번으로 전부 끝나게 하기 위함. 이미 다 되어 있으면(두 번째 실행부터는
# 거의 항상 이 경우) 아무것도 다시 하지 않아 빠르게 지나간다.
function Ensure-BackendReady {
    $backendPath = Join-Path $PSScriptRoot "backend"
    $venvPath = Join-Path $backendPath ".venv"
    $venvActivate = Join-Path $venvPath "Scripts\Activate.ps1"

    if (-not (Test-Path $venvActivate)) {
        Write-Host "가상환경(.venv)이 없어 새로 만듭니다 (최초 1회만 실행됩니다)..." -ForegroundColor Cyan
        $python = Find-Python
        if (-not $python) {
            Write-Host "`n파이썬을 찾을 수 없습니다. https://www.python.org/downloads/ 에서 설치 후 다시 실행해주세요." -ForegroundColor Red
            Write-Host "설치 화면에서 'Add python.exe to PATH' 옵션을 꼭 체크하세요." -ForegroundColor Yellow
            return $false
        }
        & $python -m venv $venvPath
        if (-not (Test-Path $venvActivate)) {
            Write-Host "`n가상환경 생성에 실패했습니다." -ForegroundColor Red
            return $false
        }
    }

    . $venvActivate

    # "uvicorn이 있는지"만으로는 부족하다 - git pull로 requirements.txt에
    # 새 패키지가 추가된 경우(예: python-multipart), venv 자체는 이미
    # 있고 uvicorn도 이미 설치돼 있어 이 조건만으로는 감지가 안 되고,
    # 새로 추가된 패키지가 없는 채로 서버가 그대로 떠버려 나중에
    # "OOO가 설치되어 있지 않습니다" 오류로 죽는다. 그래서 requirements.txt
    # 내용의 해시를 venv 안에 남겨두고, git pull로 그 내용이 바뀌었으면
    # (즉 저장해둔 해시와 다르면) 매번 다시 설치하도록 한다 - 이미 설치된
    # 패키지는 pip가 알아서 건너뛰므로 매번 다시 해도 거의 즉시 끝난다.
    $requirementsPath = Join-Path $backendPath "requirements.txt"
    $hashMarkerPath = Join-Path $venvPath "requirements.sha256"
    $currentHash = (Get-FileHash $requirementsPath -Algorithm SHA256).Hash
    $installedHash = if (Test-Path $hashMarkerPath) { (Get-Content $hashMarkerPath -Raw).Trim() } else { $null }
    $needsInstall = (-not (Get-Command uvicorn -ErrorAction SilentlyContinue)) -or ($installedHash -ne $currentHash)

    if ($needsInstall) {
        Write-Host "필요한 패키지를 설치/갱신합니다 (requirements.txt 변경 감지 시 매번 실행되며, 몇 분 걸릴 수 있습니다)..." -ForegroundColor Cyan
        Push-Location $backendPath
        pip install -q -r requirements.txt
        if ($LASTEXITCODE -ne 0) {
            # 사내망/백신/VPN이 자체 인증서로 HTTPS를 가로채는 경우
            # "CERTIFICATE_VERIFY_FAILED"로 실패한다 - pypi.org와
            # files.pythonhosted.org만 신뢰하도록 지정해 재시도한다.
            Write-Host "일반 설치가 실패했습니다 (사내망 SSL 인증서 문제일 수 있음). 다시 시도합니다..." -ForegroundColor Yellow
            pip install -q --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt
        }
        $installFailed = ($LASTEXITCODE -ne 0)
        Pop-Location
        if ($installFailed) {
            Write-Host "`n패키지 설치에 실패했습니다. 인터넷 연결 또는 사내망 보안 설정을 확인해주세요." -ForegroundColor Red
            return $false
        }
        Set-Content -Path $hashMarkerPath -Value $currentHash -NoNewline
    }

    $envFile = Join-Path $backendPath ".env"
    $envExample = Join-Path $backendPath ".env.example"
    if ((-not (Test-Path $envFile)) -and (Test-Path $envExample)) {
        Copy-Item $envExample $envFile
        Write-Host "backend\.env 파일이 없어 .env.example을 복사해 만들었습니다 (필요하면 나중에 값을 채워넣으세요)." -ForegroundColor Cyan
    }

    return $true
}

function Get-ConfiguredPort {
    # backend\.env의 "PORT=" 값을 읽어 쓴다. 8000번을 못 쓰는 경우(다른
    # 프로그램이 이미 쓰고 있거나, Windows에서 Hyper-V/WSL2/Docker Desktop이
    # 그 번호를 "동적 포트 예약 범위"로 잡아둔 경우 - 서버가 뜨자마자
    # [WinError 10013] 오류로 멈추는 증상으로 나타남)에도, 코드를 고치지
    # 않고 .env에 한 줄만 추가하면 바로 다른 포트로 바꿀 수 있게 하기
    # 위함이다. 값이 없거나 숫자가 아니면 기본값 8000을 쓴다.
    $envFile = Join-Path $PSScriptRoot "backend\.env"
    if (Test-Path $envFile) {
        $match = Select-String -Path $envFile -Pattern '^\s*PORT\s*=\s*(\d+)\s*$' -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($match) {
            return [int]$match.Matches[0].Groups[1].Value
        }
    }
    return 8000
}

function Update-FromGit {
    # 로컬에 커밋되지 않은 변경사항(예: 이 폴더에서 직접 파일을 고친 적이
    # 있는 경우)이 있으면 git pull이 "Your local changes... would be
    # overwritten by merge"로 막힌다 - 그때마다 사용자가 직접 git stash를
    # 해야 했던 번거로움을 없애려고, 있으면 자동으로 잠깐 보관해뒀다가
    # (untracked 파일은 건드리지 않고 추적 중인 파일 변경분만) pull이 끝나면
    # 다시 얹는다. 최신 커밋으로 실제로 업데이트됐는지도 커밋 해시로 비교해
    # "받아졌는지 안 받아졌는지 헷갈림" 문제를 없앤다.
    $beforeCommit = (git rev-parse --short HEAD 2>$null).Trim()

    $hasLocalChanges = -not [string]::IsNullOrWhiteSpace((git status --porcelain))
    if ($hasLocalChanges) {
        Write-Host "  (로컬에 커밋되지 않은 변경사항이 있어 잠깐 보관해두고 받습니다...)" -ForegroundColor DarkGray
        git stash push -m "run.bat 자동 보관 ($(Get-Date -Format 'yyyy-MM-dd HH:mm'))" | Out-Null
    }

    git pull

    if ($hasLocalChanges) {
        git stash pop
        if ($LASTEXITCODE -ne 0) {
            Write-Host "`n[알림] 아까 보관해둔 로컬 변경사항을 최신 코드 위에 자동으로 다시 합치지 못했습니다(내용이 겹치는 부분이 있는 것으로 보입니다)." -ForegroundColor Yellow
            Write-Host "  'git status'로 어느 파일이 겹치는지 확인해 직접 정리해주세요. 보관해둔 내용은 사라지지 않고 'git stash list'에 남아있습니다." -ForegroundColor Yellow
        }
    }

    $afterCommit = (git rev-parse --short HEAD 2>$null).Trim()
    if ($beforeCommit -and $afterCommit -and $beforeCommit -ne $afterCommit) {
        Write-Host "  업데이트됨: $beforeCommit -> $afterCommit" -ForegroundColor Green
    } elseif ($afterCommit) {
        Write-Host "  이미 최신 상태입니다 ($afterCommit)" -ForegroundColor DarkGray
    }
}

function Start-Server {
    Set-Location $PSScriptRoot

    Write-Host "`n[1/3] 최신 코드 받는 중 (git pull)..." -ForegroundColor Cyan
    Update-FromGit

    Write-Host "`n[2/3] 실행 환경 준비 중 (가상환경/패키지 확인)..." -ForegroundColor Cyan
    if (-not (Ensure-BackendReady)) {
        Set-Location $PSScriptRoot
        return
    }

    $backendPath = Join-Path $PSScriptRoot "backend"
    Set-Location $backendPath

    $uvicorn = Get-Command uvicorn -ErrorAction SilentlyContinue
    if (-not $uvicorn) {
        Write-Host "`n가상환경에서 uvicorn을 찾을 수 없습니다." -ForegroundColor Red
        Set-Location $PSScriptRoot
        return
    }

    $port = Get-ConfiguredPort
    Write-Host "`n[3/3] 서버 실행 중... (작업을 일시중지하고 메뉴로 가려면 Ctrl+C를 누르세요)" -ForegroundColor Cyan
    Write-Host "브라우저에서 http://localhost:$port 접속하세요.`n" -ForegroundColor Green

    # 1. PowerShell이 Ctrl+C를 맞고 죽는 것을 방지
    [Console]::TreatControlCAsInput = $true

    # 2. 서버를 실행하고 해당 프로세스 정보를 $process 변수에 담음 (PassThru)
    $startedAt = Get-Date
    $userStopped = $false
    $process = Start-Process -FilePath $uvicorn.Source -ArgumentList @("app.main:app", "--reload", "--port", "$port") -NoNewWindow -PassThru

    # 3. 서버가 살아있는 동안 반복해서 키 입력을 감시
    try {
        while (-not $process.HasExited) {
            if ([Console]::KeyAvailable) {
                $key = [Console]::ReadKey($true)

                # Ctrl + C 가 눌렸는지 확인
                if ($key.Key -eq [ConsoleKey]::C -and $key.Modifiers -match 'Control') {
                    Write-Host "`n[알림] Ctrl+C 감지됨. 서버 프로세스를 중지합니다..." -ForegroundColor Yellow
                    # uvicorn --reload는 내부적으로 실제 앱을 돌리는 별도의 자식
                    # 프로세스를 새로 띄운다. Stop-Process는 우리가 잡고 있는
                    # $process.Id(리로더/감독 프로세스)만 죽이고 그 자식은 그대로
                    # 남겨둔다 - 그러면 화면에는 멈춘 것처럼 보여도 실제 서버는
                    # 포트 8000에서 계속 살아서 요청을 처리한다(전체 법령 캐시처럼
                    # 오래 도는 작업의 진행 건수가 Ctrl+C 이후에도 계속 올라가는
                    # 증상으로 나타남). taskkill /T로 자식 프로세스까지 함께
                    # 종료해야 한다.
                    & taskkill /PID $process.Id /T /F 2>$null | Out-Null
                    $userStopped = $true
                    break
                }
            }
            # CPU 점유율이 치솟지 않도록 0.2초 대기
            Start-Sleep -Milliseconds 200
        }
    } finally {
        # 4. 루프를 빠져나오면 다시 일반적인 입력 상태로 되돌림 (Read-Host 작동을 위해)
        [Console]::TreatControlCAsInput = $false
    }

    # 사용자가 Ctrl+C로 직접 멈춘 게 아닌데도 몇 초 만에 프로세스가 바로
    # 죽었다면, 서버 코드 자체의 문제라기보다 시작 단계(포트 바인딩)에서
    # 실패했을 가능성이 크다. 특히 Windows의 [WinError 10013]("액세스
    # 권한에 의해 숨겨진 소켓에 액세스를 시도했습니다")은 그 포트를 이미
    # 다른 프로그램이 쓰고 있거나, Hyper-V/WSL2/Docker Desktop이 그 포트를
    # "동적 포트 예약 범위"로 잡아둔 경우 흔히 나는 오류다(이 저장소의
    # 개발 환경은 Linux라 이 시나리오를 직접 재현하지는 못했다 - 실제
    # Windows 사용자가 겪은 사례를 바탕으로 추가한 진단 메시지다). 위쪽에
    # 이미 출력된 uvicorn/Python 자신의 원본 오류 메시지에 이어서, 무엇을
    # 확인하면 되는지 구체적인 다음 행동을 안내한다.
    $elapsedSeconds = ((Get-Date) - $startedAt).TotalSeconds
    if ((-not $userStopped) -and $process.HasExited -and $elapsedSeconds -lt 5 -and $process.ExitCode -ne 0) {
        Write-Host "`n[진단] 서버가 시작하자마자(약 $([math]::Round($elapsedSeconds, 1))초 만에) 멈췄습니다 - 대부분 포트 ${port}번을 쓸 수 없어서입니다." -ForegroundColor Yellow
        Write-Host "  1) 이미 이 포트를 쓰는 다른 프로그램이 있는지 확인:" -ForegroundColor Gray
        Write-Host "     netstat -ano | findstr :$port" -ForegroundColor DarkGray
        Write-Host "  2) [WinError 10013] 오류였다면, Hyper-V/WSL2/Docker Desktop이 이 포트를 예약해둔 경우가 흔합니다. 아래 명령으로 확인하세요:" -ForegroundColor Gray
        Write-Host "     netsh interface ipv4 show excludedportrange protocol=tcp" -ForegroundColor DarkGray
        Write-Host "  3) 위 범위 안에 $port번이 들어 있다면, backend\.env 파일을 열어 아래 줄을 추가한 뒤 다시 실행하세요 (예: 8080번으로 변경):" -ForegroundColor Gray
        Write-Host "     PORT=8080" -ForegroundColor DarkGray
        Write-Host "     (그 뒤로는 http://localhost:8080 으로 접속하면 됩니다)" -ForegroundColor Gray
    }

    Set-Location $PSScriptRoot
}

function Clear-PendingKeys {
    # 버퍼에 남아있는 불필요한 키 입력 제거
    while ([Console]::KeyAvailable) { [Console]::ReadKey($true) | Out-Null }
}

# --- 메인 실행부 ---
# 아래 전체를 try/catch로 감싸서, 예상 못한 오류(예: git이 설치 안 됨,
# 잘못된 폴더에서 실행함 등)로 스크립트가 중간에 죽어도 오류 메시지를
# 볼 수 있게 창을 붙잡아둡니다. run.bat에 -NoExit도 같이 있어서 이중으로
# 창이 안 닫히게 되어 있지만, 이 스크립트를 PowerShell에서 직접(.\run.ps1)
# 실행했을 때도 똑같이 오류가 안 보이고 사라지는 걸 막아줍니다.
try {
    Start-Server
    Clear-PendingKeys

    # 서버가 중지되면 여기서 무한 대기하며 명령어 대기
    while ($true) {
        Write-Host "`n=================================================" -ForegroundColor DarkGray
        Write-Host "서버가 중지되었습니다." -ForegroundColor Yellow
        $cmd = (Read-Host "▶ 다시 시작(git pull 포함)하려면 run(또는 start), 종료하려면 exit 입력").Trim().ToLower()

        if ($cmd -eq "run" -or $cmd -eq "start") {
            Start-Server
            Clear-PendingKeys
        } elseif ($cmd -eq "exit" -or $cmd -eq "quit") {
            break
        } else {
            Write-Host "run, start, exit 중 하나를 입력해주세요." -ForegroundColor Red
        }
    }
} catch {
    Write-Host "`n[오류] 예상치 못한 문제가 발생해서 중단됐습니다:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host $_.InvocationInfo.PositionMessage -ForegroundColor DarkGray
    Write-Host "`n이 화면을 캡처해서 알려주시면 원인을 확인할 수 있습니다." -ForegroundColor Yellow
    Write-Host "아무 키나 누르면 계속합니다..." -ForegroundColor DarkGray
    [Console]::ReadKey($true) | Out-Null
}
