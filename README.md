# minecraft-socket-autoboot

## 概要

このプロジェクトは、Minecraft のオンデマンドサーバーを構築・運用するための仕組みを提供します。主な仕組みとしては、systemd の socket ユニットと連携し、クライアントからの接続要求があったときに Python スクリプト（main.py）が起動し、必要であれば Docker Compose を用いて Minecraft コンテナを起動するという流れになっています。さらに、Ansible を使ってターゲット環境への自動デプロイも可能です。

---

## README.md の内容

README.md には、以下のファイル配置と各種初期設定、サービスの有効化方法が記載されています。

### ファイル配置

- **systemd ユニットファイル**
  - `/etc/systemd/system/minecraft-on-demand.socket`
  - `/etc/systemd/system/minecraft-on-demand@.service`
- **プロジェクトファイル**
  - `/opt/minecraft-on-demand/main.py`
  - `/opt/minecraft-on-demand/compose.yaml`
  - `/opt/minecraft-on-demand/requirements.txt`

### セットアップ手順

1. **手動でのセットアップ**

    1.1. **Python 仮想環境の作成と依存パッケージのインストール**

      - 仮想環境の作成:

        ```bash
        python3 -m venv /opt/minecraft-on-demand/venv
        ```

      - 仮想環境の有効化:

        ```bash
        source /opt/minecraft-on-demand/venv/bin/activate
        ```

      - pip による必要パッケージのインストール:

        ```bash
        pip install -r /opt/minecraft-on-demand/requirements.txt
        ```

    1.2. **systemd ユニットファイルの配置とサービス管理**

      - ユニットファイルのコピー:

        ```bash
        sudo cp /opt/minecraft-on-demand/minecraft-on-demand.socket /etc/systemd/system/
        sudo cp /opt/minecraft-on-demand/minecraft-on-demand@.service /etc/systemd/system/
        ```

      - systemd デーモンのリロード:

        ```bash
        sudo systemctl daemon-reload
        ```

      - socket サービスの有効化および起動:

        ```bash
        sudo systemctl enable minecraft-on-demand.socket
        sudo systemctl start minecraft-on-demand.socket
        ```

      - サービスの状態確認:

        ```bash
        sudo systemctl status minecraft-on-demand.socket
        ```

2. **Ansible によるデプロイ**
   最後に、Ansible のプレイブックを使用してデプロイする方法も記載されています。

   ```bash
   ansible-playbook -i host minecraft-on-demand.yml
   ```

---

## 補足情報：システム全体の流れ

- **systemd の socket 起動**
  `minecraft-on-demand.socket` はポート 25565 で接続を待ち受け、接続が入ると自動的に `minecraft-on-demand@.service` を起動します。

- **Python スクリプト (main.py) の役割**
  - クライアントから systemd によって渡されるソケットを利用し、接続元の情報をログに記録します。
  - Docker Compose を用いて、Minecraft サーバー（Docker コンテナ）の状態を確認し、必要に応じて起動します。
  - TCP 接続が確立するまで待機し、さらに `mcstatus` ライブラリを使用してサーバーがプロトコルレベルで正常稼働しているかチェックします。
  - クライアントからの初期通信データをバッファリングし、接続先のサーバーに転送します。
  - サーバー側との双方向データ転送を処理し、接続終了後には systemd の socket 接続数に応じてサーバーの停止処理を行います。

- **Docker Compose 構成 (compose.yaml)**
  Minecraft サーバーの Docker コンテナは、外部からの接続ポート（25564 ← 25565）や、環境変数 `EULA: "TRUE"` を設定した上で起動します。ボリュームでデータ永続化も実現しています。

- **Ansible プレイブック (minecraft-on-demand.yml)**
  Ansible のプレイブックは、依存パッケージのインストール、Docker のセットアップ、プロジェクトファイルの配置、Python 仮想環境の作成、systemd ユニットファイルの配置、サービスの起動といった全プロセスを自動化します。

---

## まとめ

README.md は、手動でシステムをセットアップする場合と Ansible で自動デプロイする場合の両方について、必要な手順を簡潔にまとめています。
このリポジトリにより、接続要求に応じてオンデマンドで Minecraft サーバーが起動する仕組みを、Docker、systemd、Python、そして Ansible によって効率的に管理・運用できるようになっています。

## おまけ

```bash
/etc/systemd/system/minecraft-on-demand.socket
/etc/systemd/system/minecraft-on-demand@.service
/opt/minecraft-on-demand/main.py
/opt/minecraft-on-demand/compose.yaml
/opt/minecraft-on-demand/requirements.txt

python3 -m venv /opt/minecraft-on-demand/venv
source /opt/minecraft-on-demand/venv/bin/activate
pip install -r /opt/minecraft-on-demand/requirements.txt
sudo cp /opt/minecraft-on-demand/minecraft-on-demand.socket /etc/systemd/system/
sudo cp /opt/minecraft-on-demand/minecraft-on-demand@.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable minecraft-on-demand.socket
sudo systemctl start minecraft-on-demand.socket
sudo systemctl status minecraft-on-demand.socket
```

```bash
ansible-playbook -i host minecraft-on-demand.yml
```
