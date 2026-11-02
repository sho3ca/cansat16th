#!/usr/bin/env python3
"""
【プログラム名】motor_calibration.py
【役割】
  左右モーターの配線極性・取り付け向きに応じた回転方向キャリブレーションツール。
  左輪（モーターA）、右輪（モーターB）を片方ずつ前転信号で低速駆動し、
  ユーザーの目視確認結果を ~/cansat_config.env に永続化（MOTOR_A_INVERT / MOTOR_B_INVERT）する。

【ハードウェア構成・ピンアサイン (BCM番号)】
  - モーターA (左輪): PWMA=13, AIN1=5, AIN2=6
  - モーターB (右輪): PWMB=18, BIN1=23, BIN2=24
  - 共通制御: STBY=11

【出力先】
  ~/cansat_config.env (MOTOR_A_INVERT, MOTOR_B_INVERT を 0 または 1 で保存)
"""

import os
import sys
import time
from gpiozero import Motor, PWMOutputDevice, OutputDevice, Device
from gpiozero.pins.lgpio import LGPIOFactory

Device.pin_factory = LGPIOFactory()

CONFIG_PATH = os.path.expanduser("~/cansat_config.env")

PIN_PWMA = 13
PIN_AIN1 = 5
PIN_AIN2 = 6

PIN_PWMB = 18
PIN_BIN1 = 23
PIN_BIN2 = 24

PIN_STBY = 11

pwm_a = PWMOutputDevice(PIN_PWMA)
pwm_b = PWMOutputDevice(PIN_PWMB)
motor_a = Motor(forward=PIN_AIN1, backward=PIN_AIN2)
motor_b = Motor(forward=PIN_BIN1, backward=PIN_BIN2)
stby = OutputDevice(PIN_STBY)

def stop_all():
    pwm_a.value = 0.0
    pwm_b.value = 0.0
    motor_a.stop()
    motor_b.stop()
    stby.off()

def update_env_variable(key, value):
    lines = []
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            lines = f.readlines()

    lines = [line for line in lines if not line.strip().startswith(f"{key}=")]
    lines.append(f"{key}={value}\n")

    with open(CONFIG_PATH, "w") as f:
        f.writelines(lines)

def test_motor(motor_name, motor_obj, pwm_obj):
    stop_all()
    print(f"\n=======================================================")
    print(f" [{motor_name}] の回転テストを行います。")
    print(f" 車体が浮いているか、車輪が自由に回る状態にしてください。")
    print(f"=======================================================")
    input("Ready? [Enter] を押すと 1.5 秒間前転信号を出力します...")

    stby.on()
    pwm_obj.value = 0.6
    motor_obj.forward()
    time.sleep(1.5)
    stop_all()

    while True:
        print("\nタイヤの回転方向を目視で確認してください:")
        print("  [1] 前進方向（正常）に回った")
        print("  [2] 後退方向（逆向き）に回った")
        choice = input("選択してください [1 or 2]: ").strip()
        if choice == "1":
            return False
        elif choice == "2":
            return True
        print("1 または 2 を入力してください。")

def main():
    try:
        print("\n#######################################################")
        print("      CanSat モーター極性（回転方向）キャリブレーション")
        print("#######################################################")

        invert_a = test_motor("左車輪 (モーターA)", motor_a, pwm_a)
        invert_b = test_motor("右車輪 (モーターB)", motor_b, pwm_b)

        val_a = "1" if invert_a else "0"
        val_b = "1" if invert_b else "0"

        update_env_variable("MOTOR_A_INVERT", val_a)
        update_env_variable("MOTOR_B_INVERT", val_b)

        print("\n=======================================================")
        print(" キャリブレーションが完了しました。設定を保存しました。")
        print(f" 保存先: {CONFIG_PATH}")
        print(f"   MOTOR_A_INVERT = {val_a} ({'反転' if invert_a else '正転'})")
        print(f"   MOTOR_B_INVERT = {val_b} ({'反転' if invert_b else '正転'})")
        print("=======================================================\n")

    except KeyboardInterrupt:
        print("\nキャリブレーションを中断しました。")
    finally:
        stop_all()
        pwm_a.close(); pwm_b.close()
        motor_a.close(); motor_b.close()
        stby.close()

if __name__ == "__main__":
    main()
