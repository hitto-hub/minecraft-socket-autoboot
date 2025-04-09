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
