#!/usr/bin/env bash
# 배포용 설치 파일에 넣을 Windows용 Python 실행환경을 내려받아 준비한다.
#
# python.org의 임베더블(embeddable) zip이 정석이지만, 이 빌드 스크립트가
# 도는 환경에서는 python.org 접근이 막혀 있을 수 있다. 대신 파이썬
# 재단(PSF)이 NuGet(nuget.org)에 공식으로 배포하는 동일한 CPython
# 재배포판을 사용한다 - CI/빌드 용도로 흔히 쓰이는 정식 배포 경로이며
# python.exe/pythonw.exe와 표준 라이브러리(Lib/), sqlite3 모듈까지
# 그대로 들어 있다.
set -euo pipefail

PY_VERSION="${PY_VERSION:-3.11.9}"
OUT_DIR="${1:-build/payload/python}"

echo "Python ${PY_VERSION} (nuget.org) 다운로드 중..."
TMP_NUPKG="$(mktemp /tmp/python-XXXXXX.nupkg)"
curl -fsSL -o "$TMP_NUPKG" \
  "https://api.nuget.org/v3-flatcontainer/python/${PY_VERSION}/python.${PY_VERSION}.nupkg"

rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"
TMP_EXTRACT="$(mktemp -d)"
unzip -q "$TMP_NUPKG" -d "$TMP_EXTRACT"
cp -r "$TMP_EXTRACT/tools/." "$OUT_DIR/"
rm -rf "$TMP_EXTRACT" "$TMP_NUPKG"

echo "Python ${PY_VERSION} 실행환경을 $OUT_DIR 에 준비했습니다."
