#!/usr/bin/env python3
"""Simple CAN bus test script for boneIO Black.

This script tests basic CAN communication by sending and receiving frames.
Run this on a boneIO Black device after configuring the CAN overlay.

Prerequisites:
1. Enable CAN overlay in /boot/uEnv.txt:
   uboot_overlay_addr4=/lib/firmware/BB-CAN1-00A0.dtbo

2. Reboot and configure interface:
   sudo ip link set can0 type can bitrate 125000
   sudo ip link set up can0

3. Run this script:
   python3 scripts/test_can.py

For loopback test (single device):
   sudo ip link set can0 type can bitrate 125000 loopback on
   sudo ip link set up can0
"""

import argparse
import asyncio
import sys
import time

try:
    import can
    CAN_AVAILABLE = True
except ImportError:
    CAN_AVAILABLE = False
    print("ERROR: python-can not installed. Run: pip install python-can")
    sys.exit(1)


async def test_send(channel: str, count: int = 5) -> None:
    """Send test CAN frames.
    
    Args:
        channel: CAN interface (e.g., 'can0', 'vcan0')
        count: Number of frames to send
    """
    print(f"\n=== Sending {count} test frames on {channel} ===\n")
    
    try:
        bus = can.Bus(interface='socketcan', channel=channel)
        
        for i in range(count):
            # Heartbeat frame (COB-ID: 0x701 = node 1)
            heartbeat = can.Message(
                arbitration_id=0x701,
                data=[0x05],  # OPERATIONAL state
                is_extended_id=False,
            )
            bus.send(heartbeat)
            print(f"[{i+1}] Sent heartbeat: ID=0x701, data=0x05 (OPERATIONAL)")
            
            # Output state frame (TPDO1: 0x181 = node 1)
            output_state = can.Message(
                arbitration_id=0x181,
                data=[i, 1, 128, 0, 0, 0, 0, 0],  # output_index, state, brightness
                is_extended_id=False,
            )
            bus.send(output_state)
            print(f"[{i+1}] Sent TPDO1: ID=0x181, output={i}, state=ON, brightness=128")
            
            await asyncio.sleep(0.5)
        
        bus.shutdown()
        print("\n✅ Send test completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Send test failed: {e}")
        raise


async def test_receive(channel: str, timeout: float = 10.0) -> None:
    """Receive and display CAN frames.
    
    Args:
        channel: CAN interface (e.g., 'can0', 'vcan0')
        timeout: How long to listen (seconds)
    """
    print(f"\n=== Listening for frames on {channel} (timeout: {timeout}s) ===\n")
    print("Waiting for CAN frames... (press Ctrl+C to stop)\n")
    
    try:
        bus = can.Bus(interface='socketcan', channel=channel)
        start_time = time.time()
        frame_count = 0
        
        while (time.time() - start_time) < timeout:
            msg = bus.recv(timeout=0.5)
            if msg:
                frame_count += 1
                
                # Decode frame type
                cob_id = msg.arbitration_id
                if 0x700 <= cob_id <= 0x77F:
                    node_id = cob_id - 0x700
                    state = msg.data[0] if msg.data else 0
                    state_name = {0x00: "BOOT-UP", 0x04: "STOPPED", 0x05: "OPERATIONAL", 0x7F: "PRE-OP"}.get(state, f"0x{state:02X}")
                    print(f"[{frame_count}] HEARTBEAT: node={node_id}, state={state_name}")
                    
                elif 0x180 <= cob_id <= 0x1FF:
                    node_id = cob_id - 0x180
                    if len(msg.data) >= 3:
                        output_idx = msg.data[0]
                        state = "ON" if msg.data[1] else "OFF"
                        brightness = msg.data[2]
                        print(f"[{frame_count}] TPDO1: node={node_id}, output={output_idx}, state={state}, brightness={brightness}")
                    else:
                        print(f"[{frame_count}] TPDO1: node={node_id}, data={msg.data.hex()}")
                        
                else:
                    print(f"[{frame_count}] FRAME: ID=0x{cob_id:03X}, data={msg.data.hex()}")
        
        bus.shutdown()
        print(f"\n✅ Received {frame_count} frames in {timeout}s")
        
    except KeyboardInterrupt:
        print(f"\n\nStopped. Received {frame_count} frames.")
    except Exception as e:
        print(f"\n❌ Receive test failed: {e}")
        raise


async def test_loopback(channel: str) -> None:
    """Test loopback mode (send and receive on same device).
    
    Args:
        channel: CAN interface (e.g., 'can0')
    """
    print(f"\n=== Loopback test on {channel} ===\n")
    print("Make sure loopback is enabled:")
    print(f"  sudo ip link set {channel} type can bitrate 125000 loopback on")
    print(f"  sudo ip link set up {channel}\n")
    
    try:
        bus = can.Bus(interface='socketcan', channel=channel, receive_own_messages=True)
        
        # Send test frame
        test_msg = can.Message(
            arbitration_id=0x123,
            data=[0xDE, 0xAD, 0xBE, 0xEF],
            is_extended_id=False,
        )
        
        print(f"Sending: ID=0x123, data=DEADBEEF")
        bus.send(test_msg)
        
        # Try to receive it back
        received = bus.recv(timeout=1.0)
        
        if received:
            print(f"Received: ID=0x{received.arbitration_id:03X}, data={received.data.hex().upper()}")
            if received.data == test_msg.data:
                print("\n✅ Loopback test PASSED! CAN interface is working.")
            else:
                print("\n⚠️ Received different data than sent.")
        else:
            print("\n❌ No frame received. Check loopback configuration.")
        
        bus.shutdown()
        
    except Exception as e:
        print(f"\n❌ Loopback test failed: {e}")
        print("\nPossible issues:")
        print("  - CAN interface not configured")
        print("  - Loopback mode not enabled")
        print("  - Missing kernel modules (can, can-raw)")
        raise


def check_interface(channel: str) -> bool:
    """Check if CAN interface exists and is up.
    
    Args:
        channel: CAN interface name
        
    Returns:
        True if interface is ready
    """
    import subprocess
    
    try:
        result = subprocess.run(
            ['ip', 'link', 'show', channel],
            capture_output=True,
            text=True,
        )
        
        if result.returncode != 0:
            print(f"❌ Interface {channel} not found!")
            print("\nTo create the interface:")
            print("  1. Add to /boot/uEnv.txt:")
            print("     uboot_overlay_addr4=/lib/firmware/BB-CAN1-00A0.dtbo")
            print("  2. Reboot")
            print("  3. Configure interface:")
            print(f"     sudo ip link set {channel} type can bitrate 125000")
            print(f"     sudo ip link set up {channel}")
            return False
        
        if 'UP' not in result.stdout:
            print(f"⚠️ Interface {channel} exists but is DOWN")
            print(f"\nTo bring it up:")
            print(f"  sudo ip link set {channel} type can bitrate 125000")
            print(f"  sudo ip link set up {channel}")
            return False
        
        print(f"✅ Interface {channel} is UP")
        return True
        
    except Exception as e:
        print(f"❌ Error checking interface: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Test CAN bus communication on boneIO Black",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        'mode',
        choices=['send', 'receive', 'loopback', 'check'],
        help="Test mode: send, receive, loopback, or check interface",
    )
    parser.add_argument(
        '-c', '--channel',
        default='can0',
        help="CAN interface (default: can0)",
    )
    parser.add_argument(
        '-n', '--count',
        type=int,
        default=5,
        help="Number of frames to send (default: 5)",
    )
    parser.add_argument(
        '-t', '--timeout',
        type=float,
        default=10.0,
        help="Receive timeout in seconds (default: 10)",
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("  boneIO Black CAN Bus Test")
    print("=" * 60)
    
    if args.mode == 'check':
        check_interface(args.channel)
        return
    
    if not check_interface(args.channel):
        sys.exit(1)
    
    if args.mode == 'send':
        asyncio.run(test_send(args.channel, args.count))
    elif args.mode == 'receive':
        asyncio.run(test_receive(args.channel, args.timeout))
    elif args.mode == 'loopback':
        asyncio.run(test_loopback(args.channel))


if __name__ == '__main__':
    main()
