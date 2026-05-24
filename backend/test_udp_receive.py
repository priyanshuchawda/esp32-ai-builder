import socket
import struct
import time

def main():
    print("Listening for incoming ESP32 CSI packets on 0.0.0.0:5005...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", 5005))
    sock.settimeout(10.0) # 10 seconds timeout

    packet_count = 0
    start_time = time.time()

    try:
        while packet_count < 10:
            try:
                data, addr = sock.recvfrom(4096)
                if len(data) >= 20:
                    magic, node_id, antennas, n_subcarriers, freq_mhz, seq, rssi, noise, reserved = struct.unpack("<IBBHIIbbH", data[:20])
                    if magic == 0xC5110001:
                        packet_count += 1
                        print(f"Packet {packet_count} from {addr}:")
                        print(f"  Node ID: {node_id}")
                        print(f"  Sequence: {seq}")
                        print(f"  RSSI: {rssi} dBm")
                        print(f"  Frequency: {freq_mhz} MHz")
                        print(f"  Subcarriers: {n_subcarriers}")
                        print(f"  Total Bytes: {len(data)}")
                        
                        # Let's print out the first few amplitude values
                        iq_data = data[20:]
                        amplitudes = []
                        for i in range(0, min(len(iq_data), n_subcarriers * 2) - 1, 2):
                            in_phase = iq_data[i]
                            if in_phase >= 128:
                                in_phase -= 256
                            Q = iq_data[i+1]
                            if Q >= 128:
                                Q -= 256
                            amplitudes.append((in_phase*in_phase + Q*Q)**0.5)
                        if amplitudes:
                            avg_amp = sum(amplitudes) / len(amplitudes)
                            print(f"  Avg Amplitude: {avg_amp:.2f}")
                    else:
                        print(f"Received non-CSI UDP packet of length {len(data)} from {addr}")
            except socket.timeout:
                print("Timeout waiting for UDP packet. ESP32 might be offline or using a different IP.")
                break
    except KeyboardInterrupt:
        print("Stopped by user")
    finally:
        sock.close()
        print(f"Done. Received {packet_count} packets in {time.time() - start_time:.2f} seconds.")

if __name__ == "__main__":
    main()
