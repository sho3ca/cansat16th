# CanSat モーター駆動・走行制御 & FPV操縦システム

Raspberry Pi Zero 2 W 上で動作するモータードライバ（TB6612FNG等）の回転方向極性キャリブレーション、SSH経由でのWASDリアルタイム走行制御、およびWebストリーミングカメラ連動操縦を行うシステム。通信途絶時の自動停止フェイルセーフや環境設定の分離設計を備え、安全かつ確実な実機テストを支援する。

---

## 🎮 主な操作

SSHログイン後、`main` ディレクトリに移動して各テストプログラムを起動します。

### 1. 初回・配線変更時: モーター極性キャリブレーション
左右の配線やギアの取り付け向きに合わせて正転・逆転の極性を自動補正します。

```bash
cd ~/cansat16th/main
python3 motor_calibration.py
```
- **手順**: 
  1. 車体を持ち上げて車輪を浮かせた状態にする。
  2. 画面の指示に従って左輪・右輪が前進方向に回ったか（`1`: 正常前進 / `2`: 逆転）を入力する。
  3. 設定値は `~/cansat_config.env` に自動保存され、以降の全走行プログラムに自動適用される。

---

### 2. 手動走行テスト（走行単体・超信地/緩旋回）
キーボード入力によるリアルタイム走行を行います。

```bash
cd ~/cansat16th/main
python3 teleop_wasd.py
```

| キー | 動作 | 補足 |
| :---: | :--- | :--- |
| **`W`** | 前進 (Forward) | キーを押している間のみ走行 |
| **`S`** | 後退 (Backward) | キーを押している間のみ走行 |
| **`A`** | 左旋回 (Left) | 現在の旋回モードに応じた動作 |
| **`D`** | 右旋回 (Right) | 現在の旋回モードに応じた動作 |
| **`M`** | 旋回モード切替 | **超信地旋回（スピン）** ⇔ **緩旋回（片輪減速カーブ）** |
| **`+` / `-`** | 速度調整 | 基準速度を10%刻みで増減（10%〜100%） |
| **`Space`** | 即時停止 | モーター通電遮断・STBY Low |
| **`Q`** | プログラム終了 | 安全停止してGPIOリソースを完全解放 |

> **⚠️ フェイルセーフ仕様**: キー入力を離す（またはSSH通信が途絶する）と、**0.5秒後に自動でモーターが安全停止**します。

---

### 3. FPVカメラ連動走行テスト（Web配信・静止画キャプチャ対応）
ブラウザで機体前方のリアルタイム映像を確認しながら、WASD走行と静止画撮影を行います。

```bash
cd ~/cansat16th/main
libcamerify python3 teleop_wasd_camera.py
```

- **映像の確認**: 同一Wi-Fiに接続したPCやスマホのブラウザで `http://<Raspberry_PiのIPアドレス>:5000` にアクセスする。
- **走行操作**: SSHターミナル側をクリックしてアクティブにし、上記と同様に `W`/`A`/`S`/`D` で走行する。
- **写真の撮影**: 走行中、ターミナルで **`C`** キーを押すと最新フレームを高画質静止画として `~/cansat_data/images/` に即時保存する。
- **安全な終了**: ターミナルで **`Q`** を押す（または `Ctrl + C`）。

---

## 🔄 プログラムの最新化（コード更新）

PC側でGitHubの共通コードを更新した場合、ラズパイ側で以下を実行して最新版に同期します。

```bash
cd ~/cansat16th
git pull
```

---

## 🛠 初回セットアップ手順（新しいmicroSDカード作成時）

### 1. 依存ライブラリのインストール

```bash
sudo apt-get update
sudo apt-get install -y python3-gpiozero python3-lgpio python3-opencv python3-flask python3-numpy
```

### 2. ハードウェア・CMAメモリ設定の適用（カメラ連動時）

```bash
cd ~/cansat16th
chmod +x setup_hardware.sh
sudo ./setup_hardware.sh

# 設定反映のため再起動
sudo reboot
```

---

## 💡 便利コマンド集（エイリアス登録）

ターミナルで以下を実行しておくと、どのディレクトリからでも1単語で起動できます。

```bash
echo "alias drive='cd ~/cansat16th/main && python3 teleop_wasd.py'" >> ~/.bashrc
echo "alias drive-cam='cd ~/cansat16th/main && libcamerify python3 teleop_wasd_camera.py'" >> ~/.bashrc
echo "alias calib-motor='cd ~/cansat16th/main && python3 motor_calibration.py'" >> ~/.bashrc
source ~/.bashrc
```

- **`calib-motor`**: モーター極性キャリブレーションを一発起動
- **`drive`**: 手動走行プログラム（`teleop_wasd.py`）を一発起動
- **`drive-cam`**: カメラストリーミング付き手動走行（`teleop_wasd_camera.py`）を一発起動

---

## 📁 ファイル構成と役割

| ファイル名 | 役割 | 管理場所 |
| :--- | :--- | :--- |
| `motor_calibration.py` | 左右モーターの回転方向テストを行い、極性設定を保存する対話型ツール | GitHub（共通: `main/` 内） |
| `teleop_wasd.py` | フェイルセーフ付きWASD手動走行プログラム（速度調整・旋回切替対応） | GitHub（共通: `main/` 内） |
| `teleop_wasd_camera.py` | Webライブ映像配信（ポート5000）とWASD走行・スナップショット撮影の統合プログラム | GitHub（共通: `main/` 内） |
| `~/cansat_config.env` | 機体ごとのモーター極性（`MOTOR_A_INVERT`, `MOTOR_B_INVERT` 等）の個別設定ファイル | 各自のmicroSD内（Git管理外） |
| `~/cansat_data/images/` | `teleop_wasd_camera.py` で撮影された静止画の保存先ディレクトリ | 各自のmicroSD内（非公開） |
