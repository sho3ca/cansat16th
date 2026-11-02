#!/usr/bin/env python3
"""
【プログラム名】standalone_camera_test.py
【役割】
  他の自作モジュールに一切依存せず、単一ファイルで完結するカメラ映像確認用Webサーバー。
  ファイルの配置ミス（ModuleNotFoundError）を防ぎ、即座に画角やピントの確認を行う。

【動作仕様】
  1. 外部モジュールをインポートせず、本スクリプト内で直接カメラデバイス(ID:0)を開く。
  2. 取得したフレームをJPEGエンコードし、Flaskでブラウザ (0.0.0.0:5000) へ配信する。
  3. ストリーミング終了時や強制終了時(Ctrl+C)は、確実にカメラリソースを解放する。
"""

import cv2
import sys
from flask import Flask, Response

app = Flask(__name__)

def generate_frames():
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
    <html>
      <head><title>Standalone Vision Test</title></head>
      <body style="text-align:center; background-color:#111; color:#fff;">
        <h2>Standalone Vision Test</h2>
        <img src="/video_feed" width="640" height="480" style="border: 2px solid #555;">
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
    print("Press Ctrl+C to stop.")
    
    try:
        app.run(host='0.0.0.0', port=5000, threaded=True)
    except Exception as e:
        print(f"[Error] {e}", file=sys.stderr)
    finally:
        print("=== Server Stopped ===")
