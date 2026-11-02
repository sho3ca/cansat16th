#!/bin/bash
#
# 【プログラム名】setup_hardware.sh
# 【役割】
#  Raspberry PiのOSレベルのハードウェア設定（CMAメモリ拡張等）を自動化する。
#  GitHub経由で配布し、実機環境のセットアップを安全かつ冪等に行う。
#
# 【動作仕様】
#  1. /boot/firmware/config.txt または /boot/config.txt のパスを自動判定する。
#  2. dtoverlay=vc4-kms-v3d 行に cma-128 が未設定の場合のみ、sedコマンドで追記する。
#  3. 実行には sudo 権限が必要。変更を行った場合のみ再起動を促す。

set -e

if [ "$EUID" -ne 0 ]; then
  echo "[Error] 管理者権限が必要です。'sudo bash setup_hardware.sh' で実行してください。"
  exit 1
fi

CONFIG_FILE="/boot/firmware/config.txt"
if [ ! -f "$CONFIG_FILE" ]; then
    CONFIG_FILE="/boot/config.txt"
fi

if grep -q "cma-128" "$CONFIG_FILE"; then
    echo "[Skip] CMAメモリ(128MB)は既に設定されています: $CONFIG_FILE"
else
    echo "[Setup] カメラ用CMAメモリ(128MB)を割り当て中..."
    sed -i 's/dtoverlay=vc4-kms-v3d/dtoverlay=vc4-kms-v3d,cma-128/g' "$CONFIG_FILE"
    echo "[Success] 設定を更新しました。反映には再起動が必要です。"
fi
