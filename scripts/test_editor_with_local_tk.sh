#!/usr/bin/env bash
# Headless tests using verified Ubuntu Tk dependencies, without a system install.
set -euo pipefail
PM99_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PM99_TK_ROOT="${PM99_ROOT}/.local/test-dependencies/python3-tk"
PM99_TK_DEB="${PM99_TK_ROOT}/python3-tk_3.12.3-0ubuntu1_amd64.deb"
PM99_BLT_DEB="${PM99_TK_ROOT}/tk8.6-blt2.5_2.5.3+dfsg-7build1_amd64.deb"
[[ "$(sha256sum "${PM99_TK_DEB}" | cut -d ' ' -f 1)" == "33483780e4ee964a876d91fb9680f3f26da4167c7052eb28301b4abf6301c0dd" ]]
[[ "$(sha256sum "${PM99_BLT_DEB}" | cut -d ' ' -f 1)" == "dd015b5e0c59ed98f98333264bfcd4516149312030ba02b18c31a7940c887e5e" ]]
# Extraction reestablishes the exact checked package bytes, rather than trusting
# potentially modified installed module/extension copies. All output is local.
dpkg-deb --extract "${PM99_TK_DEB}" "${PM99_TK_ROOT}/extracted"
dpkg-deb --extract "${PM99_BLT_DEB}" "${PM99_TK_ROOT}/extracted"
export PYTHONDONTWRITEBYTECODE=1
export LD_LIBRARY_PATH="${PM99_TK_ROOT}/extracted/usr/lib${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
export PYTHONPATH="${PM99_TK_ROOT}/extracted/usr/lib/python3.12:${PM99_TK_ROOT}/extracted/usr/lib/python3.12/lib-dynload${PYTHONPATH:+:${PYTHONPATH}}"
cd "${PM99_ROOT}/upstream/pm99-skezmod-db-editor"
exec "${PM99_ROOT}/.local/venvs/season-pipeline/bin/python" -m pytest "$@"
