#!/bin/bash
MAC=$(cat /sys/class/net/eth0/address 2>/dev/null)
if [ -n "$MAC" ] && [ "$MAC" != "none" ]; then
    MAC_CLEAN=$(echo $MAC | tr -d ':')
    ID=${MAC_CLEAN: -6}
    NEW_HOSTNAME="blk$ID"
    hostnamectl set-hostname "$NEW_HOSTNAME"
    sed -i "s/127.0.1.1.*/127.0.1.1\t$NEW_HOSTNAME/g" /etc/hosts
fi
systemctl disable set-hostname-once.service
