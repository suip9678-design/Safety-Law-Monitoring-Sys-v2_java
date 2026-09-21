#!/usr/bin/env bash
# backend/, frontend/ 소스를 설치 파일에 넣을 payload/app/ 아래로 복사하고,
# 배포판 기본 .env를 만든다(전체 법령 자동 캐시는 매일 새벽 1시 자동 실행
# 켬 - 설치할 때 이미 캐시를 채워서 배포하는 만큼, 그 뒤로도 증분(공포번호
# 비교) 갱신으로 계속 최신 상태를 유지하기 위함).
#
# 사용법: stage_app.sh [출력폴더] [국가법령정보센터 OC 키]
#   OC 키를 넘기면 배포판 .env에 미리 넣어둔다 - 받는 사람이 설정 화면에서
#   키를 직접 입력하지 않아도 설치 직후부터 실제 법령 데이터로 동작한다.
#   생략하면 키 없이 배포되어, 받는 사람이 대시보드 > 설정에서 직접 입력하기
#   전까지는 데모(예시 데이터) 모드로 동작한다.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT_DIR="${1:-$REPO_ROOT/installer/build/payload/app}"
LAW_API_OC="${2:-}"

rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"

# .venv/.git/캐시/DB 파일 등은 제외하고 소스만 복사한다 (rsync 없이도
# 동작하도록 plain cp + 사후 정리 방식을 쓴다).
cp -r "$REPO_ROOT/backend" "$OUT_DIR/backend"
cp -r "$REPO_ROOT/frontend" "$OUT_DIR/frontend"
find "$OUT_DIR/backend" \( -name '__pycache__' -o -name '.venv' -o -name 'venv' \) -type d -prune -exec rm -rf {} +
find "$OUT_DIR/backend" -name '*.pyc' -delete
find "$OUT_DIR/backend" -maxdepth 1 -name '*.db' -delete
rm -f "$OUT_DIR/backend/.env"

cat > "$OUT_DIR/backend/.env" <<'EOF'
# 배포판 기본 설정 - 설치 후 대시보드 > 설정 화면에서 대부분 다시 바꿀 수 있습니다.
FULL_LAW_CACHE_ENABLED=true
AUTO_SYNC_INTERVAL_HOURS=24
EOF

if [[ -n "$LAW_API_OC" ]]; then
  echo "LAW_API_OC=$LAW_API_OC" >> "$OUT_DIR/backend/.env"
  echo "  국가법령정보센터 OC 키를 배포판 .env에 포함했습니다."
else
  echo "  OC 키 없이 준비했습니다(받는 사람이 설정 화면에서 직접 입력해야 실제 법령 데이터로 동작)."
fi

echo "앱 소스를 $OUT_DIR 에 준비했습니다."
