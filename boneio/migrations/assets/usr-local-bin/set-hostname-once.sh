#!/bin/bash
MAC=$(cat /sys/class/net/eth0/address 2>/dev/null || cat /sys/class/net/end0/address 2>/dev/null)
if [ -n "$MAC" ] && [ "$MAC" != "none" ]; then
    MAC_CLEAN=$(echo $MAC | tr -d ':')
    ID=${MAC_CLEAN: -6}
    NEW_HOSTNAME="blk$ID"
    hostnamectl set-hostname "$NEW_HOSTNAME"
    sed -i "s/127.0.1.1.*/127.0.1.1\t$NEW_HOSTNAME/g" /etc/hosts
    # Only disable once the hostname has actually been set from a real MAC;
    # otherwise keep the service enabled so it retries on the next boot
    # (e.g. the NIC not being renamed/up yet at this point in boot order).
    systemctl disable set-hostname-once.service
else
    echo "set-hostname-once: no MAC found on eth0/end0, will retry next boot" >&2
fi
