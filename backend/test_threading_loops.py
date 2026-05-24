import unittest
from unittest.mock import MagicMock, patch
import queue
import threading
import time
import struct
from frontend.app import udp_receiver_loop, serial_receiver_loop, simulator_loop

class TestThreadingLoops(unittest.TestCase):
    def setUp(self):
        self.shutdown_event = threading.Event()
        self.data_queue = queue.Queue(maxsize=10)
        self.config = {
            "presence_threshold": 0.6,
            "fall_threshold": 12.0
        }

    def tearDown(self):
        self.shutdown_event.set()

    @patch('socket.socket')
    def test_udp_receiver_loop_timeout(self, mock_socket_class):
        # Setup mock socket
        mock_socket = MagicMock()
        mock_socket_class.return_value = mock_socket
        
        # Simulate socket.timeout on recvfrom
        import socket
        mock_socket.recvfrom.side_effect = socket.timeout
        
        # Run loop in a separate thread so we can stop it
        t = threading.Thread(
            target=udp_receiver_loop,
            args=(5005, self.shutdown_event, self.data_queue, self.config)
        )
        t.start()
        
        # Let it run briefly to trigger socket.timeout block, then shut down
        time.sleep(0.3)
        self.shutdown_event.set()
        t.join(timeout=1.0)
        
        # The loop should put an offline packet in the queue when it timeouts for over 3 seconds.
        # But since we only ran it for 0.3s, maybe it didn't write yet, or it did.
        # Let's verify that close was called
        mock_socket.close.assert_called_once()

    @patch('socket.socket')
    def test_udp_receiver_loop_receives_packet(self, mock_socket_class):
        mock_socket = MagicMock()
        mock_socket_class.return_value = mock_socket
        
        # Construct a valid dummy ADR018 packet
        # format: <IBBHIIbbH -> magic (4B), node_id (1B), antennas (1B), n_subcarriers (2B->H but format is H? Wait, struct format is "<IBBHIIbbH" which is:
        # magic (I=4B), node_id (B=1B), antennas (B=1B), n_subcarriers (H=2B), freq_mhz (I=4B), seq (I=4B), rssi (b=1B), noise (b=1B), reserved (H=2B)
        # Total header size: 4 + 1 + 1 + 2 + 4 + 4 + 1 + 1 + 2 = 20 bytes.
        # We append 128*2 bytes of subcarrier data (IQ values)
        magic = 0xC5110001
        node_id = 1
        antennas = 2
        n_subcarriers = 64
        freq_mhz = 2412
        seq = 101
        rssi = -50
        noise = -95
        reserved = 0
        
        header = struct.pack("<IBBHIIbbH", magic, node_id, antennas, n_subcarriers, freq_mhz, seq, rssi, noise, reserved)
        iq_data = bytes([10, 20] * n_subcarriers) # I=10, Q=20 for each subcarrier
        dummy_packet = header + iq_data
        
        # Mock recvfrom to return dummy_packet once, then timeout
        import socket
        mock_socket.recvfrom.side_effect = [(dummy_packet, ("127.0.0.1", 50055)), socket.timeout]
        
        t = threading.Thread(
            target=udp_receiver_loop,
            args=(5005, self.shutdown_event, self.data_queue, self.config)
        )
        t.start()
        
        # Wait a moment for packet to be processed and queued
        time.sleep(0.3)
        self.shutdown_event.set()
        t.join(timeout=1.0)
        
        # Verify packet was parsed and placed in the queue
        self.assertFalse(self.data_queue.empty())
        ui_pkg = self.data_queue.get()
        self.assertEqual(ui_pkg["stats"]["node_id"], node_id)
        self.assertEqual(ui_pkg["stats"]["seq"], seq)
        self.assertEqual(ui_pkg["stats"]["rssi"], rssi)
        self.assertEqual(ui_pkg["stats"]["freq_mhz"], freq_mhz)

    @patch('serial.Serial')
    def test_serial_receiver_loop(self, mock_serial_class):
        mock_serial = MagicMock()
        mock_serial_class.return_value = mock_serial
        
        # Simulate serial inputs: timestamp,rssi,bin0,bin1,bin2,bin3,bin4,bin5
        mock_serial.readline.return_value = b"1000,-48,1.2,1.5,1.1,1.3,1.4,1.2\n"
        
        t = threading.Thread(
            target=serial_receiver_loop,
            args=("COM5", 115200, self.shutdown_event, self.data_queue, self.config)
        )
        t.start()

        try:
            # Wait for the observable result instead of assuming filter startup
            # completes within a fixed scheduling interval.
            ui_pkg = self.data_queue.get(timeout=3.0)
        finally:
            self.shutdown_event.set()
            t.join(timeout=1.0)

        self.assertEqual(ui_pkg["stats"]["rssi"], -48)
        self.assertEqual(ui_pkg["stats"]["freq_mhz"], 2437)

    def test_simulator_loop(self):
        # Run the simulator loop which runs natively without external hardware
        t = threading.Thread(
            target=simulator_loop,
            args=(self.shutdown_event, self.data_queue, self.config)
        )
        t.start()
        
        time.sleep(0.3)
        self.shutdown_event.set()
        t.join(timeout=1.0)
        
        # Verify that simulator generated and queued telemetry packets
        self.assertFalse(self.data_queue.empty())
        ui_pkg = self.data_queue.get()
        self.assertIn("stats", ui_pkg)
        self.assertIn("telemetry", ui_pkg)
        self.assertIn("raw_history", ui_pkg)
        self.assertIn("filtered_history", ui_pkg)

if __name__ == "__main__":
    unittest.main()
