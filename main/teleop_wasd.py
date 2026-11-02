#!/usr/bin/env python3
"""
【プログラム名】teleop_wasd.py
【役割】
  PC（SSHターミナル）のキーボード入力によるCanSatローバーのリアルタイム手動走行制御プログラム。
  ~/cansat_config.env からモーター極性設定（MOTOR_A_INVERT, MOTOR_B_INVERT）を自動読込し、
  配線反転をソフトウェア上で補正した上でWASD操縦を提供する。

【ハードウェア構成・ピンアサイン (BCM番号)】
  - モーターA (左輪): PWMA=13, AIN1=5, AIN2=6
  - モーターB (右輪): PWMB=18, BIN1=23, BIN2=24
  - 共通制御: STBY=11

【操作仕様】
  [W] 前進 | [S] 後退 | [A] 左旋回 | [D] 右旋回
  [M] 旋回モード切替 (超信地スピン ⇔ 緩旋回カーブ)
  [+] 速度UP | [-] 速度DOWN | [Space] 停止 | [Q] 終了
  ※ キーを離すと0.5秒後に自動停止（フェイルセーフ）
"""

import sys
import select
import termios
import tty
import time
import os
from gpiozero import Motor, PWMOutputDevice, OutputDevice, Device
from gpiozero.pins.lgpio import LGPIOFactory

Device.pin_factory = LGPIOFactory()

CONFIG_PATH = os.path.expanduser("~/cansat_config.env")

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
    drive_single_motor(motor_a, pwm_a, speed_a, dir_a, invert=INVERT_A)
    drive_single_motor(motor_b, pwm_b, speed_b, dir_b, invert=INVERT_B)
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
    global current_speed, turn_mode
    rover_stop()
    last_command_time = time.time()

    mode_label = "超信地旋回 (スピン)" if turn_mode == "spin" else "緩旋回 (カーブ)"
    sys.stdout.write("\r\n=======================================================\r\n")
    sys.stdout.write(" CanSat WASD 手動操縦コンソール\r\n")
    sys.stdout.write(f" 極性設定: 左輪反転={INVERT_A} | 右輪反転={INVERT_B}\r\n")
    sys.stdout.write(f" 基準速度: {int(current_speed * 100)}% | 旋回モード: [{mode_label}]\r\n")
    sys.stdout.write(" [W] 前進 | [S] 後退 | [A] 左旋回 | [D] 右旋回\r\n")
    sys.stdout.write(" [M] 旋回切替 | [+] 速度UP | [-] 速度DOWN | [Space] 停止 | [Q] 終了\r\n")
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
                    elif key == 'q':
                        sys.stdout.write("\r\n終了します...\r\n")
                        sys.stdout.flush()
                        break
                else:
                    if is_moving and (now - last_command_time > TIMEOUT_SEC):
                        rover_stop()

                time.sleep(0.01)

    except KeyboardInterrupt:
        sys.stdout.write("\r\n強制終了シグナルを受信しました。\r\n")
        sys.stdout.flush()
    finally:
        rover_stop()
        pwm_a.close(); pwm_b.close()
        motor_a.close(); motor_b.close()
        stby.close()
        print("GPIOリソースを解放し、安全停止しました。")

if __name__ == "__main__":
    main()
