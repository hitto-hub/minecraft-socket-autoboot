#!/usr/bin/env python3
import os
import sys
import socket
import time
import select
import subprocess
import logging

# --- ログの設定 ---
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# --- 設定値 ---
# Docker Compose のファイルパス
COMPOSE_FILE = '/home/hitto/mc/compose.yaml'
# 接続先（Docker で起動される Minecraft サーバー）が待ち受けるホストとポート
TARGET_HOST = '127.0.0.1'
TARGET_PORT = 25564    # ※ systemd ソケットが 25565 で受け付けるため、別ポートにする例
# サーバー起動待ちのポーリング間隔（秒）
POLL_INTERVAL = 2

# --- Docker Compose サーバーの稼働状況確認 ---
def is_minecraft_running():
    logging.debug("is_minecraft_running: Docker Compose の状態を確認します。")
    try:
        result = subprocess.run(
            ["docker", "compose", "-f", COMPOSE_FILE, "ps", "--quiet"],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            logging.error("docker compose ps に失敗しました: %s", result.stderr)
            return False
        # 出力が空の場合、実行中のコンテナが無いと判断する
        output = result.stdout.strip()
        logging.debug("docker compose ps の出力: '%s'", output)
        return bool(output)
    except Exception as e:
        logging.exception("Docker Compose の状態確認中に例外が発生しました。")
        return False

# --- Docker Compose によるサーバー起動 ---
def start_minecraft_server():
    logging.info("Minecraft サーバーが実行されていないため、docker compose up -d を実行します。")
    try:
        result = subprocess.run(
            ["docker", "compose", "-f", COMPOSE_FILE, "up", "-d"],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            logging.error("docker compose up に失敗しました: %s", result.stderr)
            sys.exit(1)
        logging.info("docker compose up の実行が完了しました。")
    except Exception as e:
        logging.exception("docker compose up の実行中に例外が発生しました。")
        sys.exit(1)

# --- サーバーが接続可能になるまで待機 ---
def wait_for_server():
    logging.info("Minecraft サーバーが %s:%d で接続可能になるのを待ちます。", TARGET_HOST, TARGET_PORT)
    while True:
        try:
            with socket.create_connection((TARGET_HOST, TARGET_PORT), timeout=5):
                logging.info("Minecraft サーバーが起動し、接続可能になりました。")
                return
        except Exception as e:
            logging.debug("サーバーはまだ接続可能ではありません: %s", e)
            time.sleep(POLL_INTERVAL)

# --- docker compose 状態の確認・起動 ---
def ensure_minecraft_server_running():
    if not is_minecraft_running():
        start_minecraft_server()
    else:
        logging.info("既に Minecraft サーバーは実行中です。")

# --- ソケット間の双方向データ転送 ---
def forward_data(src, dst):
    logging.debug("forward_data: 双方向のデータ転送を開始します。")
    src.setblocking(0)
    dst.setblocking(0)
    sockets = [src, dst]
    while True:
        try:
            r, _, x = select.select(sockets, [], sockets, 1)
            if x:
                logging.debug("forward_data: エラーが検出されました。転送を中断します。")
                break
            if not r:
                continue
            for sock in r:
                data = sock.recv(4096)
                if not data:
                    logging.debug("forward_data: データがなくなりました。")
                    return
                if sock is src:
                    dst.sendall(data)
                else:
                    src.sendall(data)
        except Exception as e:
            logging.exception("forward_data: 例外が発生しました。")
            return

def main():
    # systemd により渡されたソケットを標準入力 (fd 0) 経由で取得
    logging.debug("main: systemd から渡されたソケットを取得します。")
    try:
        sock_in = socket.socket(fileno=sys.stdin.fileno())
        peer = sock_in.getpeername()
        logging.info("main: 接続元の情報: %s", peer)
    except Exception as e:
        logging.exception("main: 受け取ったソケットのオープンに失敗しました。")
        sys.exit(1)

    # Docker Compose による Minecraft サーバーの状態確認・起動
    ensure_minecraft_server_running()
    # サーバーが接続可能になるまで待機
    wait_for_server()

    # Docker Compose で起動したサーバーへの接続を確立
    logging.debug("main: Minecraft サーバー(%s:%d) への接続を試みます。", TARGET_HOST, TARGET_PORT)
    try:
        sock_out = socket.create_connection((TARGET_HOST, TARGET_PORT))
        logging.info("main: Minecraft サーバーへの接続に成功しました。")
    except Exception as e:
        logging.exception("main: Minecraft サーバーへの接続に失敗しました。")
        sys.exit(1)

    # 受け取ったソケット (クライアントからの接続) とサーバーへのソケットでデータを転送
    forward_data(sock_in, sock_out)
    sock_in.close()
    sock_out.close()
    logging.info("main: 接続をクローズしました。")

if __name__ == "__main__":
    main()
