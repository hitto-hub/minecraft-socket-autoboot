#!/usr/bin/env python3
import os
import sys
import socket
import time
import select
import subprocess
import logging
import signal
from mcstatus import JavaServer

# --- ログの設定 ---
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# --- 設定値 ---
COMPOSE_FILE = '/opt/minecraft-on-demand/compose.yaml'
TARGET_HOST = '127.0.0.1'
TARGET_PORT = 25564         # Docker コンテナ側のポート（systemd のソケットと被らないように設定）
POLL_INTERVAL = 2           # サーバー待機のポーリング間隔（秒）
WAIT_AFTER_TCP = 3          # TCP 接続確認後に追加で待機する秒数
CONNECT_RETRIES = 3         # 接続確立試行回数
CONNECT_RETRY_DELAY = 2     # 接続試行間の待機秒数
SERVER_READY_TIMEOUT = 60   # mcstatus によるサーバー起動完了待ちのタイムアウト（秒）

# --- シャットダウンフラグとシグナルハンドラー ---
shutdown_flag = False

def signal_handler(signum, frame):
    global shutdown_flag
    logging.info("シグナル %s を受信しました。終了処理を開始します。", signum)
    shutdown_flag = True

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

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
        output = result.stdout.strip()
        logging.debug("docker compose ps の出力: '%s'", output)
        return bool(output)
    except Exception:
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
    except Exception:
        logging.exception("docker compose up の実行中に例外が発生しました。")
        sys.exit(1)

# --- サーバーがプロトコルレベルで起動完了するまで待機（mcstatus を使用） ---
def wait_for_server_ready(host, port, timeout=SERVER_READY_TIMEOUT):
    logging.info("mcstatus を使用して、Minecraft サーバーの起動完了（プロトコルレベル）を待ちます。")
    server = JavaServer.lookup(f"{host}:{port}")
    start_time = time.time()
    while time.time() - start_time < timeout and not shutdown_flag:
        try:
            # サーバーに ping を送り、ステータス取得を試みる
            status = server.status()
            if status.version.name:
                logging.info("Minecraft サーバーが起動しました: バージョン %s", status.version.name)
                return True
        except Exception as e:
            logging.debug("Minecraft サーバーの起動確認中: %s", e)
        time.sleep(2)
    logging.error("指定したタイムアウト内に Minecraft サーバーの起動確認ができませんでした。")
    return False

# --- docker compose 状態の確認・起動 ---
def ensure_minecraft_server_running():
    if not is_minecraft_running():
        start_minecraft_server()
    else:
        logging.info("既に Minecraft サーバーは実行中です。")

# --- 接続確立のための再試行 ---
def connect_to_server_with_retry(retries=CONNECT_RETRIES, delay=CONNECT_RETRY_DELAY):
    attempt = 0
    while attempt < retries and not shutdown_flag:
        try:
            sock = socket.create_connection((TARGET_HOST, TARGET_PORT))
            logging.info("Minecraft サーバーへの接続に成功しました。")
            return sock
        except Exception as e:
            attempt += 1
            logging.warning("接続試行 %d/%d に失敗しました: %s。%d秒後に再試行します。",
                            attempt, retries, e, delay)
            time.sleep(delay)
    logging.error("Minecraft サーバーへの接続に %d 回失敗しました。", retries)
    sys.exit(1)

# --- ソケット間の双方向データ転送 ---
def forward_data(src, dst):
    logging.debug("forward_data: 双方向のデータ転送を開始します。")
    src.setblocking(0)
    dst.setblocking(0)
    sockets = [src, dst]
    while not shutdown_flag:
        try:
            r, _, x = select.select(sockets, [], sockets, 1)
            if x:
                logging.debug("forward_data: エラーが検出されました。転送を中断します。")
                break
            if not r:
                continue
            for sock in r:
                try:
                    data = sock.recv(4096)
                except ConnectionResetError:
                    logging.warning("forward_data: Connection reset by peer が検出されました。転送を終了します。")
                    return
                if not data:
                    logging.debug("forward_data: データがなくなりました。")
                    return
                # 受信元に応じた転送処理
                if sock is src:
                    dst.sendall(data)
                else:
                    src.sendall(data)
        except Exception:
            logging.exception("forward_data: 例外が発生しました。")
            return

# --- systemd socket の接続数を取得 ---
def get_socket_connected_count():
    try:
        result = subprocess.run(
            ["systemctl", "show", "minecraft-on-demand.socket", "-p", "NConnections"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            logging.error("socket 接続数チェックに失敗: %s", result.stderr)
            return None
        for line in result.stdout.splitlines():
            if line.startswith("NConnections="):
                key, value = line.split("=", 1)
                return int(value.strip())
        return None
    except Exception:
        logging.exception("socket 接続数チェック中に例外が発生しました。")
        return None

# --- Minecraft サーバーの停止処理 ---
def shutdown_minecraft_server():
    logging.info("全ての接続が切断されました。Minecraft サーバーを停止します。")
    try:
        result = subprocess.run(
            ["docker", "compose", "-f", COMPOSE_FILE, "stop"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            logging.info("Minecraft サーバーを正常に停止しました。")
        else:
            logging.error("サーバー停止に失敗: %s", result.stderr)
    except Exception:
        logging.exception("Minecraft サーバー停止中に例外が発生しました。")

def main():
    logging.debug("main: systemd から渡されたソケットを取得します。")
    try:
        sock_in = socket.socket(fileno=sys.stdin.fileno())
        peer = sock_in.getpeername()
        logging.info("main: 接続元の情報: %s", peer)
    except Exception:
        logging.exception("main: 受け取ったソケットのオープンに失敗しました。")
        sys.exit(1)

    # Docker Compose によるサーバー状態確認・起動
    ensure_minecraft_server_running()

    # TCP 接続可能の確認
    logging.info("Minecraft サーバーが %s:%d で TCP 接続可能になるのを待ちます。", TARGET_HOST, TARGET_PORT)
    while not shutdown_flag:
        try:
            with socket.create_connection((TARGET_HOST, TARGET_PORT), timeout=5):
                logging.info("TCP 接続が確認されました。")
                break
        except Exception as e:
            logging.debug("TCP 接続待機中: %s", e)
            time.sleep(POLL_INTERVAL)
    if shutdown_flag:
        sys.exit(0)

    # mcstatus によるサーバー起動完了待ち
    if not wait_for_server_ready(TARGET_HOST, TARGET_PORT):
        sys.exit(1)

    # TCP 接続確認後、アプリケーション初期化のために追加待機
    logging.info("TCP 接続確認後、アプリケーション初期化のために %d 秒待機します。", WAIT_AFTER_TCP)
    time.sleep(WAIT_AFTER_TCP)

    # クライアントからの初期データをバッファリング（ハンドシェイク等のデータがある可能性）
    sock_in.setblocking(0)
    try:
        initial_data = sock_in.recv(4096)
    except BlockingIOError:
        initial_data = b""
    except Exception:
        logging.exception("main: クライアントから初期データを読み込めませんでした。")
        initial_data = b""
    finally:
        sock_in.setblocking(1)
    logging.info("初期データのサイズ: %d bytes", len(initial_data))

    logging.debug("main: Minecraft サーバー(%s:%d) への接続を試みます。", TARGET_HOST, TARGET_PORT)
    sock_out = connect_to_server_with_retry()

    # もし初期データがあれば、すぐにサーバーへ送信
    if initial_data:
        try:
            sock_out.sendall(initial_data)
            logging.info("初期データをサーバーへ転送しました。")
        except Exception:
            logging.exception("初期データの転送に失敗しました。")

    try:
        forward_data(sock_in, sock_out)
    finally:
        sock_in.close()
        sock_out.close()
        logging.info("main: 接続をクローズしました。")

    # 接続終了後に systemctl show により接続数をチェックする
    count = get_socket_connected_count()
    if count is not None:
        logging.info("現在の socket 接続数: %d", count)
        # 接続数が 1 なら、自分以外の接続はないと判断してサーバーを停止する
        if count <= 1:
            shutdown_minecraft_server()
        else:
            logging.info("接続が残っているため、サーバー停止はスキップします。")
    else:
        logging.error("socket 接続数の取得に失敗したため、サーバー停止処理は実行されません。")

if __name__ == "__main__":
    main()
