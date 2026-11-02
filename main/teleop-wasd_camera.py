#!/usr/bin/env python3
"""
【プログラム名】teleop_wasd_camera.py
【役割】
  CanSatローバーのPC（SSHターミナル）WASD手動走行制御と、
  Flask/OpenCVによるWebライブ映像ストリーミング（ポート5000）を並行実行する統合プログラム。
  ブラウザで機体前方の映像を確認しながら、キーボード操作で走行および静止画撮影を行う。

【ハードウェア・ピンアサイン (BCM番号)】
  - モーターA (左輪想定): PWMA=13, AIN1=5, AIN2=6
  - モーターB (右輪想定): PWMB=18, BIN1=23, BIN2=24
  - 共通制御: STBY=11
  ※ ~/cansat_config.env から極性（MOTOR_A_INVERT, MOTOR_B_INVERT, SWAP_MOTORS）を自動読込。

【カメラ・Webストリーミング仕様】
  - ポート: 5000 (http://<ラズパイのIP>:5000)
  - 解像度: 640x480
  - 保存先: ~/cansat_data/images/ (タイムスタンプ付きJPEG)
  - 実行環境: V4L2互換モード（libcamerify 経由での起動を推奨）

【操作仕様】
  [W] 前進 | [S] 後退 | [A] 左旋回 | [D] 右旋回
  [M] 旋回モード切替 (超信地スピン ⇔ 緩旋回カーブ)
  [+] 速度UP | [-] 速度DOWN | [Space] 停止
  [C] 静止画スナップショット保存 (ブラウザ映像から即時キャプチャ)
  [Q] 終了 (モーター完全停止・GPIOおよびカメラ解放)
  ※ 無入力状態が 0.5 秒続くと自動停止（フェイルセーフ）

【起動方法】
  libcamerify python3 teleop_wasd_camera.py
"""

import sys
import select
import termios
import tty
import time
import os
import threading
import logging
from datetime import datetime
import cv2
from flask import Flask, Response
from gpiozero import Motor, PWMOutputDevice, OutputDevice, Device
from gpiozero.pins.lgpio import LGPIOFactory

Device.pin_factory = LGPIOFactory()

# Flaskのアクセスログを抑制（キー入力画面の見やすさを維持）
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

app = Flask(__name__)

# ===== 設定・パス初期化 =====
CONFIG_PATH = os.path.expanduser("~/cansat_config.env")
SAVE_DIR = os.path.expanduser("~/cansat_data/images")
os.makedirs(SAVE_DIR, exist_ok=True)

def load_env_config():
    config = {}
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    config[k.strip()] = v.strip().strip('"').strip("'")
    return config

env_config = load_env_config()
INVERT_A = env_config.get("MOTOR_A_INVERT", "0") == "1"
INVERT_B = env_config.get("MOTOR_B_INVERT", "0") == "1"
SWAP_MOTORS = env_config.get("SWAP_MOTORS", "0") == "1"

PIN_PWMA = 13
PIN_AIN1 = 5
PIN_AIN2 = 6

PIN_PWMB = 18
PIN_BIN1 = 23
PIN_BIN2 = 24

PIN_STBY = 11

DEFAULT_SPEED = float(env_config.get("ROVER_DEFAULT_SPEED", 0.8))
TIMEOUT_SEC = 0.5

# ===== GPIO・モーター初期化 =====
pwm_a = PWMOutputDevice(PIN_PWMA)
pwm_b = PWMOutputDevice(PIN_PWMB)
motor_a = Motor(forward=PIN_AIN1, backward=PIN_AIN2)
motor_b = Motor(forward=PIN_BIN1, backward=PIN_BIN2)
stby = OutputDevice(PIN_STBY)

current_speed = DEFAULT_SPEED
turn_mode = "spin"
is_moving = False

# ===== カメラ・ストリーミング共有リソース =====
latest_frame = None
frame_lock = threading.Lock()
camera_running = True

def drive_single_motor(motor_obj, pwm_obj, speed, direction, invert=False):
    if direction == "stop":
        pwm_obj.value = 0.0
        motor_obj.stop()
        return

    actual_dir = direction
    if invert:
        actual_dir = "rev" if direction == "fwd" else "fwd"

    pwm_obj.value = max(0.0, min(1.0, abs(speed)))
    if actual_dir == "fwd":
        motor_obj.forward()
    elif actual_dir == "rev":
        motor_obj.backward()

def set_motors(speed_a, speed_b, dir_a="stop", dir_b="stop"):
    global is_moving
    if dir_a == "stop" and dir_b == "stop":
        pwm_a.value = 0.0
        pwm_b.value = 0.0
        motor_a.stop()
        motor_b.stop()
        stby.off()
        is_moving = False
        return

    stby.on()
    if not SWAP_MOTORS:
        drive_single_motor(motor_a, pwm_a, speed_a, dir_a, invert=INVERT_A)
        drive_single_motor(motor_b, pwm_b, speed_b, dir_b, invert=INVERT_B)
    else:
        drive_single_motor(motor_a, pwm_a, speed_b, dir_b, invert=INVERT_A)
        drive_single_motor(motor_b, pwm_b, speed_a, dir_a, invert=INVERT_B)
    is_moving = True

def rover_stop():
    set_motors(0, 0, "stop", "stop")

def rover_forward():
    set_motors(current_speed, current_speed, "fwd", "fwd")

def rover_backward():
    set_motors(current_speed, current_speed, "rev", "rev")

def rover_left():
    if turn_mode == "spin":
        set_motors(current_speed * 0.7, current_speed * 0.7, "rev", "fwd")
    else:
        set_motors(current_speed * 0.35, current_speed, "fwd", "fwd")

def rover_right():
    if turn_mode == "spin":
        set_motors(current_speed * 0.7, current_speed * 0.7, "fwd", "rev")
    else:
        set_motors(current_speed, current_speed * 0.35, "fwd", "fwd")

# ===== Webストリーミング配信関数 =====
def generate_frames():
    global latest_frame
    cap = cv2.VideoCapture(0)

    if not cap.isOpened():
        sys.stdout.write("\r\n[Error] カメラ ID:0 を開けませんでした。\r\n")
        sys.stdout.flush()
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    try:
        while camera_running:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.05)
                continue

            with frame_lock:
                latest_frame = frame.copy()

            ret, jpeg = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
            if not ret:
                continue

            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
    finally:
        cap.release()

@app.route('/')
def index():
    return """
    <!DOCTYPE html>
    <html lang="ja">
      <head>
        <meta charset="utf-8">
        <title>CanSat FPV Live Stream</title>
      </head>
      <body style="text-align:center; background-color:#121212; color:#fff; font-family:sans-serif;">
        <h2>CanSat FPV Live Camera Feed</h2>
        <img src="/video_feed" width="640" height="480" style="border: 2px solid #00ff88; border-radius: 4px;" alt="Camera Stream">
        <p style="color:#aaa;">SSHターミナルから WASD で走行、[C] で静止画を撮影</p>
      </body>
    </html>
    """

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

def capture_photo():
    with frame_lock:
        if latest_frame is not None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:19]
            filepath = os.path.join(SAVE_DIR, f"snap_{timestamp}.jpg")
            cv2.imwrite(filepath, latest_frame)
            sys.stdout.write(f"\r\n[Capture] 保存完了: {os.path.basename(filepath)}\r\n")
            sys.stdout.flush()
        else:
            sys.stdout.write("\r\n[Warning] フレーム未取得です。ブラウザで http://<IP>:5000 を開いてください。\r\n")
            sys.stdout.flush()

class NonBlockingKeyReader:
    def __enter__(self):
        self.fd = sys.stdin.fileno()
        self.old_settings = termios.tcgetattr(self.fd)
        tty.setraw(self.fd)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old_settings)

    def read_key(self, timeout=0.05):
        rlist, _, _ = select.select([self.fd], [], [], timeout)
        if rlist:
            char = sys.stdin.read(1)
            return char.lower()
        return None

def main():
    global current_speed, turn_mode, camera_running
    rover_stop()
    last_command_time = time.time()

    # Flask サーバーをバックグラウンドスレッドで起動
    server_thread = threading.Thread(
        target=lambda: app.run(host='0.0.0.0', port=5000, threaded=True, use_reloader=False),
        daemon=True
    )
    server_thread.start()

    mode_label = "超信地旋回 (スピン)" if turn_mode == "spin" else "緩旋回 (カーブ)"
    sys.stdout.write("\r\n=======================================================\r\n")
    sys.stdout.write(" CanSat WASD 手動操縦 & FPVカメラサーバー\r\n")
    sys.stdout.write(" Web映像配信: http://<ラズパイIP>:5000\r\n")
    sys.stdout.write(f" 極性設定: 左輪反転={INVERT_A} | 右輪反転={INVERT_B} | 入替={SWAP_MOTORS}\r\n")
    sys.stdout.write(f" 基準速度: {int(current_speed * 100)}% | 旋回モード: [{mode_label}]\r\n")
    sys.stdout.write(" [W] 前進 | [S] 後退 | [A] 左旋回 | [D] 右旋回\r\n")
    sys.stdout.write(" [M] 旋回切替 | [+] 速度UP | [-] 速度DOWN | [Space] 停止\r\n")
    sys.stdout.write(" [C] 静止画キャプチャ保存 | [Q] 終了\r\n")
    sys.stdout.write(" ※ キーを離すと0.5秒で安全停止します\r\n")
    sys.stdout.write("=======================================================\r\n\r\n")
    sys.stdout.flush()

    try:
        with NonBlockingKeyReader() as reader:
            while True:
                key = reader.read_key(timeout=0.05)
                now = time.time()

                if key:
                    last_command_time = now
                    if key == 'w':
                        rover_forward()
                    elif key == 's':
                        rover_backward()
                    elif key == 'a':
                        rover_left()
                    elif key == 'd':
                        rover_right()
                    elif key == ' ':
                        rover_stop()
                    elif key == 'm':
                        turn_mode = "curve" if turn_mode == "spin" else "spin"
                        lbl = "緩旋回 (カーブ)" if turn_mode == "curve" else "超信地旋回 (スピン)"
                        sys.stdout.write(f"\r\n=> 旋回モード切替: [{lbl}]\r\n")
                        sys.stdout.flush()
                    elif key in ('+', '='):
                        current_speed = min(1.0, round(current_speed + 0.1, 1))
                        sys.stdout.write(f"\r=> 速度設定: {int(current_speed * 100)}%   \r\n")
                        sys.stdout.flush()
                    elif key in ('-', '_'):
                        current_speed = max(0.1, round(current_speed - 0.1, 1))
                        sys.stdout.write(f"\r=> 速度設定: {int(current_speed * 100)}%   \r\n")
                        sys.stdout.flush()
                    elif key == 'c':
                        capture_photo()
                    elif key == 'q':
                        sys.stdout.write("\r\n終了処理中...\r\n")
                        sys.stdout.flush()
                        break
                else:
                    if is_moving and (now - last_command_time > TIMEOUT_SEC):
                        rover_stop()

                time.sleep(0.01)

    except KeyboardInterrupt:
        sys.stdout.write("\r\n強制終了を受信しました。\r\n")
        sys.stdout.flush()
    finally:
        camera_running = False
        rover_stop()
        pwm_a.close(); pwm_b.close()
        motor_a.close(); motor_b.close()
        stby.close()
        print("GPIOおよびカメラリソースを安全に解放しました。")

if __name__ == "__main__":
    main()
