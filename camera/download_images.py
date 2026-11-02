#!/usr/bin/env python3
"""
【プログラム名】download_images.py
【実行環境】Windows PC (ラズパイ側ではなく、手元のパソコンで実行する)
【役割】
  Raspberry Pi内に保存されたカメラ画像を、Windows PCの指定フォルダへ一括ダウンロードする。
  ダウンロード完了後、SDカード容量確保のためにラズパイ側の画像を削除するか選択する。

【動作仕様】
  1. PC側の保存先は C:\\Users\\Shosk\\Documents\\00_F.T.E.関係\\00_プログラム開発 とする。
  2. 実行時にRaspberry PiのIPアドレスの入力を求める。
  3. Windows標準の scp コマンドを呼び出してラズパイ内の .jpg ファイルを全て転送する。
  4. 転送成功後、ssh コマンドを用いてラズパイ側の画像ファイルを削除するか(y/n)で対話的に実行する。
"""

import os
import subprocess
import sys

class ImageDownloader:
    def __init__(self, pi_user="pi", pi_dir="~/cansat_data/images/"):
        self.pi_user = pi_user
        self.pi_dir = pi_dir
        self.pc_save_dir = r"C:\Users\Shosk\Documents\00_F.T.E.関係\00_プログラム開発"
        
        os.makedirs(self.pc_save_dir, exist_ok=True)

    def download(self, ip):
        print(f"\n[1/2] 画像をPCへ転送中...\n保存先: {self.pc_save_dir}")
        
        scp_cmd = ["scp", f"{self.pi_user}@{ip}:{self.pi_dir}*.jpg", self.pc_save_dir]
        result = subprocess.run(scp_cmd)
        
        if result.returncode != 0:
            print("\n[Error] 転送失敗。IPアドレスが違うか、ラズパイ側に画像が1枚も無い可能性があります。", file=sys.stderr)
            return False
            
        print("\n[Success] PCへのダウンロードが完了しました。")
        return True

    def ask_and_delete(self, ip):
        while True:
            ans = input("\nRaspberry Pi内の元画像を削除しますか？ (y/n): ").strip().lower()
            
            if ans in ['y', 'yes']:
                print("[2/2] Raspberry Pi内の画像を削除中...")
                ssh_cmd = ["ssh", f"{self.pi_user}@{ip}", f"rm -f {self.pi_dir}*.jpg"]
                del_result = subprocess.run(ssh_cmd)
                
                if del_result.returncode == 0:
                    print("[Success] ラズパイ内の画像を削除し、SDカード容量を確保しました。")
                else:
                    print("[Error] 削除コマンドの実行に失敗しました。", file=sys.stderr)
                break
            elif ans in ['n', 'no']:
                print("ラズパイ内に画像を残したまま終了します。")
                break
            else:
                print(" 'y' または 'n' を入力してください。")

if __name__ == "__main__":
    print("=== CanSat 画像一括ダウンロードツール ===")
    target_ip = input("Raspberry PiのIPアドレスを入力してください: ").strip()
    
    if target_ip:
        downloader = ImageDownloader()
        if downloader.download(target_ip):
            downloader.ask_and_delete(target_ip)
    else:
        print("IPアドレスが未入力のため終了します。")
