#!/usr/bin/env python3
"""
【プログラム名】standalone_camera_test.py
【役割】
  単一ファイルで完結するカメラストリーミング用Webサーバーに、
  SSHターミナルからのキーボード入力による静止画保存機能を追加した検証ツール。

【動作仕様】
  1. Flaskによる映像配信を行いつつ、別スレッドでターミナル入力を監視する。
  2. PCやスマホのブラウザで http://<ラズパイのIPアドレス>:5000 にアクセスし、映像を確認。
  3. ブラウザからのアクセス時、カメラから取得した最新フレームをグローバル変数に保持する。
  4. ターミナルで 'c' と入力してEnterを押すと、排他制御を用いて安全に最新フレームを保存する。
  5. 保存先は ~/cansat_data/images とし、タイムスタンプ付きのファイル名で出力する。
"""

import cv2
import sys
import os
import threading
from datetime import datetime
from flask import Flask, Response

app = Flask(__name__)

latest_frame = None
frame_lock = threading.Lock()

save_dir = os.path.expanduser("~/cansat_data/images")
os.makedirs(save_dir, exist_ok=True)

def keyboard_listener():
    while True:
        try:
            cmd = input()
            if cmd.strip().lower() == 'c':
                with frame_lock:
                    if latest_frame is not None:
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        filepath = os.path.join(save_dir, f"manual_{timestamp}.jpg")
                        cv2.imwrite(filepath, latest_frame)
                        print(f"\n[Capture] 写真を保存しました: {filepath}")
                        print("引き続き撮影可能です (c + Enter): ")
                    else:
                        print("\n[Warning] カメラ映像がありません。ブラウザでアクセスしてください。")
        except EOFError:
            break

def generate_frames():
    global latest_frame
    cap = cv2.VideoCapture(0)
    
    if not cap.isOpened():
        print("[Error] Cannot access camera ID:0", file=sys.stderr)
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            with frame_lock:
                latest_frame = frame.copy()

            ret, jpeg = cv2.imencode('.jpg', frame)
            if not ret:
                continue

            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
    finally:
        cap.release()
        print("[Vision] Camera resource released.")

@app.route('/')
def index():
    html = """
    <!DOCTYPE html>
    <html lang="ja">
      <head>
        <meta charset="utf-8">
        <title>Standalone Vision Test with Capture</title>
      </head>
      <body style="text-align:center; background-color:#111; color:#fff;">
        <h2>Standalone Vision Test</h2>
        <img src="/video_feed" width="640" height="480" style="border: 2px solid #555;" alt="Live Camera Feed">
      </body>
    </html>
    """
    return html

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    print("=== Standalone Vision Test Started ===")
    print("Access via Browser: http://<Raspberry_Pi_IP>:5000")
    print("【操作】ターミナルで 'c' を入力して Enter を押すと写真を保存します。")
    print("Press Ctrl+C to stop.\n")
    
    t = threading.Thread(target=keyboard_listener, daemon=True)
    t.start()
    
    try:
        app.run(host='0.0.0.0', port=5000, threaded=True)
    except Exception as e:
        print(f"[Error] {e}", file=sys.stderr)
    finally:
        print("=== Server Stopped ===")
