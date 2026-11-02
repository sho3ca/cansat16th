#!/usr/bin/env python3
"""
【プログラム名】camera_web_test_simple.py
【役割】
  赤色検知などの画像処理を行わず、純粋にカメラの映像（画角・ピント・明るさ）のみを
  ブラウザへストリーミング配信する基本テスト用サーバー。

【動作仕様】
  1. camera_controller.py から VisionController をインポートして初期化する。
  2. 取得したフレームを加工せずにそのままJPEGエンコードして配信する。
  3. 終了時(Ctrl+C)は確実にカメラリソースを解放する。
"""

import cv2
import sys
from flask import Flask, Response
from camera_controller import VisionController

app = Flask(__name__)
camera = None

def generate_frames():
    global camera
    if camera is None:
        camera = VisionController()

    while True:
        ret, frame = camera.cap.read()
        if not ret:
            break

        ret, jpeg = cv2.imencode('.jpg', frame)
        if not ret:
            continue

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')

@app.route('/')
def index():
    html = """
    <html>
      <head><title>CanSat Pure Vision Test</title></head>
      <body style="text-align:center; background-color:#111; color:#fff;">
        <h2>CanSat Pure Vision Test (No Detection)</h2>
        <img src="/video_feed" width="640" height="480" style="border: 2px solid #555;">
      </body>
    </html>
    """
    return html

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    print("=== Pure Vision Test Server Started ===")
    print("Access via Browser: http://<Raspberry_Pi_IP>:5000")
    print("Press Ctrl+C to stop.")
    
    try:
        app.run(host='0.0.0.0', port=5000, threaded=True)
    except Exception as e:
        print(f"[Error] {e}", file=sys.stderr)
    finally:
        if camera:
            camera.release()
        print("=== Server Stopped ===")
