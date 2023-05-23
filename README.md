Example usage:
boneio run -dd -c config.yaml

# Installation instructions

```
sudo apt-get install libopenjp2-7-dev libatlas-base-dev python3-venv libjpeg-dev zlib1g-dev
mkdir ~/boneio
python3 -m venv ~/boneio/venv
source ~/boneio/venv/bin/activate
pip3 install --upgrade boneio
cp ~/venv/lib/python3.7/site-packages/boneio/example_config/*.yaml ~/boneio/
```

Edit config.yaml

# Start app

```
source ~/boneio/venv/bin/activate
boneio run -c ~/boneio/config.yaml -dd
```
