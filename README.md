/etc/systemd/system/minecraft-on-demand.socket
/etc/systemd/system/minecraft-on-demand@.service
/home/hitto/mc/main.py
/home/hitto/mc/compose.yaml
/home/hitto/mc/requirements.txt

python3 -m venv /home/hitto/mc/venv
source /home/hitto/mc/venv/bin/activate
pip install -r /home/hitto/mc/requirements.txt
sudo cp /home/hitto/mc/minecraft-on-demand.socket /etc/systemd/system/
sudo cp /home/hitto/mc/minecraft-on-demand@.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable minecraft-on-demand.socket
sudo systemctl start minecraft-on-demand.socket
sudo systemctl status minecraft-on-demand.socket
