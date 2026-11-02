# CanSat カメラモジュール動作検証 & 撮影システム

Raspberry Pi Camera Module V2の映像（画角・ピント・明るさ）をブラウザでリアルタイムに確認し、ターミナルからのキー操作で静止画を撮影・保存するシステム。他の制御モジュールに依存せず単独で動作するため、ハードウェアの切り分けテストに最適。

---

## 📷 主な操作

SSHログイン後、カメラテスト用ディレクトリに移動して専用コマンドで起動します。

```bash
cd ~/cansat16th/camera
libcamerify python3 standalone_camera_test.py
# エイリアス設定済みの場合は `camtest` のみで起動可能
```

### テスト中の操作手順
- **映像の確認**: 同一Wi-Fi（テザリング等）に接続したPC・スマホのブラウザで `http://<Raspberry_PiのIPアドレス>:5000` にアクセスする。
- **写真の撮影**: サーバーが動いているラズパイのターミナル画面で `c` と入力して `Enter` を押す。
- **安全な終了**: ラズパイのターミナル画面で `Ctrl + C` を押す。（※そのままブラウザやターミナルを閉じるとカメラがロックされるため必ず実施すること）
- **画像のPC転送**: ラズパイ側ではなく **Windows PC側のコマンドプロンプト** で `python download_images.py` を実行し、一括ダウンロードとラズパイ内の画像消去を行う。

---

## 🔄 プログラムの最新化（コード更新）

PC側でGitHubの共通コードを更新した場合、ラズパイ側で以下を実行して最新版に同期します。

```bash
cd ~/cansat16th
git pull
```

---

## 🛠 初回セットアップ手順（新しいmicroSDカード作成時）

新しいmicroSDカードを作成し、何も導入されていない初期状態からカメラ環境を構築する手順です。

### 1. リポジトリ取得と依存ライブラリのインストール

```bash
# 認証情報をSDカード内に保存（2回目以降のトークン入力を省略）
git config --global credential.helper store

# リポジトリをクローン（既に存在する場合はスキップ）
git clone https://github.com/sho3ca/cansat16th.git ~/cansat16th

# OpenCVとFlask等の必要なパッケージを一括インストール
sudo apt-get update
sudo apt-get install -y python3-opencv python3-flask python3-numpy
```

### 2. ハードウェア（メモリ）設定の適用と再起動

カメラと画像処理を同時に動かすための専用グラフィックメモリ領域（CMA 128MB）を確保する設定スクリプトを実行します。

```bash
cd ~/cansat16th
chmod +x setup_hardware.sh
sudo ./setup_hardware.sh

# 設定反映のため必ず再起動する
sudo reboot
```

---

## 💡 便利コマンド集

SSH接続中のターミナルで実行すると役立つエイリアス設定およびメンテナンスコマンドです。

### 1. カメラテスト一発起動コマンド（`camtest`）
どこにいても `camtest` と打つだけでディレクトリ移動と `libcamerify` 付きの起動を自動で行います。

```bash
echo "alias camtest='cd ~/cansat16th/camera && libcamerify python3 standalone_camera_test.py'" >> ~/.bashrc
source ~/.bashrc
```

### 2. ラズパイ内の保存画像の一括削除
テストで溜まった画像をラズパイのターミナルから直接手動で消去してSDカードの容量を空けます。

```bash
rm -f ~/cansat_data/images/*.jpg
```

---

## 📁 ファイル構成と役割

| ファイル名 | 役割 | 管理場所 |
| :--- | :--- | :--- |
| `standalone_camera_test.py` | 映像配信とキーボード撮影を行う独立型テストスクリプト | GitHub（共通: `camera/` 内） |
| `setup_hardware.sh` | CMAメモリ拡張などOS根幹の設定を行うセットアップスクリプト | GitHub（共通: リポジトリ直下） |
| `download_images.py` | Windows上で実行し、画像をPCへ転送・削除する管理ツール | 各自のWindows PC内 |
| `~/cansat_data/images/` | 撮影された高画質な静止画データの一時保存先 | 各自のmicroSD内（非公開） |
