Example usage:
boneio run -dd -c config.yaml

# Installation instructions

```
sudo apt install -y libopenjp2-7-dev python3-venv libjpeg-dev docker-compose docker.io fonts-dejavu-core fonts-dejavu-extra libffi-dev libfreetype-dev libtiff6 libxcb1 mosquitto
mkdir ~/boneio
python3 -m venv ~/boneio/venv
source ~/boneio/venv/bin/activate
pip3 install --upgrade boneio
cp ~/venv/lib/python3.13/site-packages/boneio/example_config/*.yaml ~/boneio/
```

Edit config.yaml

# Start app

```
source ~/boneio/venv/bin/activate
boneio run -c ~/boneio/config.yaml -dd
```

```bash
sed -i 's/^- id:/- name:/' *.yaml
```