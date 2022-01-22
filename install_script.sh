#!/bin/bash

function askQuestion(){
    Q=$(whiptail --inputbox "$1" 8 39 "$2" --title "$3" 3>&1 1>&2 2>&3)
    exitstatus=$?
    if [ $exitstatus == 0 ]; then
        echo $Q;
    else
        echo "Wrong selection."
        exit 1;
    fi
}

sudo true

INSTALL_PATH=$(askQuestion "Where would you like to install package? Last part of directory will be created for you" "$HOME/boneio" "Installation PATH")
echo Preparing $INSTALL_PATH
mkdir -p $INSTALL_PATH
sudo apt-get install libopenjp2-7-dev libatlas-base-dev python3-venv
echo Creating Python3 Venv
python3 -m venv $INSTALL_PATH/venv
echo Installing PyYaml
$INSTALL_PATH/venv/bin/pip3 install --upgrade pyyaml
echo Fetching script to install boneIO.
$INSTALL_PATH/venv/bin/python3 <(wget https://github.com/boneIO-eu/app_bbb/raw/main/install_script.py -q -O-) $INSTALL_PATH
