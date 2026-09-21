#!/usr/bin/env bash
# backend/requirements.txt에 있는 패키지들의 Windows(win_amd64)용 wheel을
# PyPI에서 내려받아, 번들된 Python의 site-packages에 그대로 풀어 넣는다.
# (Windows용 python.exe를 이 빌드 환경에서 직접 실행할 수 없으므로, pip
# install 대신 wheel을 다운로드해 압축만 풀어서 넣는 방식 - wheel 설치는
# 본질적으로 파일 복사이기 때문에 이 방식으로도 충분하다.)
set -euo pipefail

REQ_FILE="${1:-backend/requirements.txt}"
PY_PAYLOAD_DIR="${2:-build/payload/python}"
PY_TAG="${PY_TAG:-311}"
SITE_PACKAGES="$PY_PAYLOAD_DIR/Lib/site-packages"
# Windows(Git Bash)의 python3는 Store 안내 스텁일 수 있어, 실제로 실행되는 쪽을 쓴다.
PYBIN=python3
python3 -c "" >/dev/null 2>&1 || PYBIN=python

WHEEL_DIR="$(mktemp -d)"
echo "Windows(win_amd64)용 wheel 다운로드 중..."
"$PYBIN" -m pip download \
  --platform win_amd64 \
  --python-version "$PY_TAG" \
  --implementation cp \
  --abi "cp${PY_TAG}" \
  --only-binary=:all: \
  -r "$REQ_FILE" \
  -d "$WHEEL_DIR"

mkdir -p "$SITE_PACKAGES"
for whl in "$WHEEL_DIR"/*.whl; do
  echo "설치: $(basename "$whl")"
  "$PYBIN" -m zipfile -e "$whl" "$SITE_PACKAGES"
done

rm -rf "$WHEEL_DIR"
echo "의존성을 $SITE_PACKAGES 에 준비했습니다."
