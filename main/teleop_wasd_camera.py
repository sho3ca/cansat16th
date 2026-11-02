#!/usr/bin/env python3
"""
【プログラム名】teleop_wasd_camera.py
【役割】
  CanSatローバーのリアルタイムFPV走行制御および低遅延Webストリーミングサーバー。
  - OS/C++レイヤーの不要なカメラログ（stderr）を抑制し、クリーンなターミナル表示を維持。
  - Webブラウザ側に操作ガイドとHUDステータスを表示し、ブラウザ上からのWASDキー操作にも対応。

【操作仕様 (ターミナルまたはブラウザ画面)】
  [W] 前進 | [S] 後退 | [A] 左旋回 | [D] 右旋回
  [M] 旋回切替 | [+] 速度UP | [-] 速度DOWN | [Space] 停止
  [C] 静止画キャプチャ保存 | [Q] 終了
  ※ 無入力状態が 0.5 秒続くと自動停止（フェイルセーフ）

【起動方法】
  libcamerify python3 teleop_wasd_camera.py 2>/dev/null
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

# libcamera / OpenCV の C++ レベル stderr 警告を抑制
os.environ["OPENCV_LOG_LEVEL"] = "SILENT"
os.environ["LIBCAMERA_LOG_LEVELS"] = "*:ERROR"

import cv2
from flask import Flask, Response, jsonify, request
from gpiozero import Motor, PWMOutputDevice, OutputDevice, Device
from gpiozero.pins.lgpio import LGPIOFactory

Device.pin_factory = LGPIOFactory()

# Flask HTTPアクセスログを完全非表示
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)
logging.getLogger('flask').setLevel(logging.ERROR)

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

pwm_a = PWMOutputDevice(PIN_PWMA)
pwm_b = PWMOutputDevice(PIN_PWMB)
motor_a = Motor(forward=PIN_AIN1, backward=PIN_AIN2)
motor_b = Motor(forward=PIN_BIN1, backward=PIN_BIN2)
stby = OutputDevice(PIN_STBY)

current_speed = DEFAULT_SPEED
turn_mode = "spin"
is_moving = False
last_command_time = time.time()

latest_frame = None
frame_lock = threading.Lock()
camera_running = True
last_capture_status = "未撮影"

# ===== モーター駆動関数 =====
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

def capture_photo():
    global last_capture_status
    with frame_lock:
        if latest_frame is not None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:19]
            filename = f"snap_{timestamp}.jpg"
            filepath = os.path.join(SAVE_DIR, filename)
            cv2.imwrite(filepath, latest_frame)
            last_capture_status = f"保存済: {filename}"
            sys.stdout.write(f"\r\n[Capture] 保存完了: {filename}\r\n")
            sys.stdout.flush()
            return True
        else:
            last_capture_status = "警告: 映像フレーム未取得"
            return False

def execute_command(cmd):
    global current_speed, turn_mode, last_command_time
    now = time.time()
    last_command_time = now

    if cmd == 'w':
        rover_forward()
    elif cmd == 's':
        rover_backward()
    elif cmd == 'a':
        rover_left()
    elif cmd == 'd':
        rover_right()
    elif cmd == ' ':
        rover_stop()
    elif cmd == 'm':
        turn_mode = "curve" if turn_mode == "spin" else "spin"
        lbl = "緩旋回 (カーブ)" if turn_mode == "curve" else "超信地旋回 (スピン)"
        sys.stdout.write(f"\r\n=> 旋回モード切替: [{lbl}]\r\n")
        sys.stdout.flush()
    elif cmd in ('+', '='):
        current_speed = min(1.0, round(current_speed + 0.1, 1))
        sys.stdout.write(f"\r=> 速度設定: {int(current_speed * 100)}%   \r\n")
        sys.stdout.flush()
    elif cmd in ('-', '_'):
        current_speed = max(0.1, round(current_speed - 0.1, 1))
        sys.stdout.write(f"\r=> 速度設定: {int(current_speed * 100)}%   \r\n")
        sys.stdout.flush()
    elif cmd == 'c':
        capture_photo()

# ===== カメラストリーミング & Web UI =====
def generate_frames():
    global latest_frame
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    try:
        while camera_running:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.04)
                continue

            with frame_lock:
                latest_frame = frame.copy()

            ret, jpeg = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 65])
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
      <title>CanSat FPV コックピット</title>
      <style>
        body { background-color: #0f1117; color: #e6edf3; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; text-align: center; margin: 0; padding: 15px; }
        .container { max-width: 800px; margin: auto; }
        .stream-box
