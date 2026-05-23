import unittest
import struct
from frontend.app import parse_adr018_packet

class TestPacketParser(unittest.TestCase):
    def test_parse_valid_packet(self):
        # Construct a valid packet
        magic = 0xC5110001
        node_id = 42
        antennas = 2
        n_subcarriers = 4
        freq_mhz = 2412
        seq = 101
        rssi = -50
        noise = -95
        reserved = 0

        header = struct.pack("<IBBHIIbbH", magic, node_id, antennas, n_subcarriers, freq_mhz, seq, rssi, noise, reserved)
        
        # 4 subcarriers -> 8 bytes of IQ data. 
        # I, Q pairs:
        # 1. I=10, Q=20
        # 2. I=128 (signed -128), Q=128 (signed -128)
        # 3. I=255 (signed -1), Q=0
        # 4. I=0, Q=50
        iq_data = bytes([10, 20, 128, 128, 255, 0, 0, 50])
        packet = header + iq_data
        
        result = parse_adr018_packet(packet)
        self.assertIsNotNone(result)
        self.assertEqual(result["node_id"], node_id)
        self.assertEqual(result["seq"], seq)
        self.assertEqual(result["rssi"], rssi)
        self.assertEqual(result["noise"], noise)
        self.assertEqual(result["freq_mhz"], freq_mhz)
        self.assertEqual(result["n_subcarriers"], n_subcarriers)
        
        # Calculate expected amplitudes manually:
        # Subcarrier 1: (10**2 + 20**2)**0.5 = 500**0.5 = 22.360679774997898
        # Subcarrier 2: ((-128)**2 + (-128)**2)**0.5 = 32768**0.5 = 181.01933598375618
        # Subcarrier 3: ((-1)**2 + 0**2)**0.5 = 1.0
        # Subcarrier 4: (0**2 + 50**2)**0.5 = 50.0
        # Average: (22.360679774997898 + 181.01933598375618 + 1.0 + 50.0) / 4 = 254.38001575875408 / 4 = 63.59500393968852
        expected_signal = ( (10**2 + 20**2)**0.5 + ((-128)**2 + (-128)**2)**0.5 + ((-1)**2 + 0**2)**0.5 + 50.0 ) / 4
        expected_amplitudes = [
            (10**2 + 20**2)**0.5,
            ((-128)**2 + (-128)**2)**0.5,
            1.0,
            50.0,
        ]
        self.assertEqual(result["amplitudes"], expected_amplitudes)
        self.assertAlmostEqual(result["raw_signal"], expected_signal, places=4)

    def test_parse_invalid_magic(self):
        # Header with wrong magic
        header = struct.pack("<IBBHIIbbH", 0xDEADC0DE, 1, 1, 4, 2412, 1, -50, -95, 0)
        iq_data = bytes([10, 20, 30, 40, 50, 60, 70, 80])
        packet = header + iq_data
        self.assertIsNone(parse_adr018_packet(packet))

    def test_parse_too_short(self):
        # Packet length < 20 bytes
        packet = bytes([1, 2, 3, 4, 5])
        self.assertIsNone(parse_adr018_packet(packet))

    def test_parse_truncated_iq(self):
        # Valid header but not enough IQ bytes for specified n_subcarriers
        magic = 0xC5110001
        n_subcarriers = 10 # Requires 20 IQ bytes
        header = struct.pack("<IBBHIIbbH", magic, 1, 1, n_subcarriers, 2412, 1, -50, -95, 0)
        iq_data = bytes([10, 20]) # Only 2 IQ bytes
        packet = header + iq_data
        
        # It should handle truncated IQ data safely up to the available bytes in min(...)
        result = parse_adr018_packet(packet)
        self.assertIsNotNone(result)
        # min(2, 20) - 1 = 1 iteration -> parses 1 subcarrier
        expected_amp = (10**2 + 20**2)**0.5
        self.assertAlmostEqual(result["raw_signal"], expected_amp, places=4)

    def test_parse_corrupt_struct(self):
        # Struct unpack exception (e.g. data length between 5 and 19 bytes)
        packet = bytes([0xC5, 0x11, 0x00, 0x01, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11])
        self.assertIsNone(parse_adr018_packet(packet))

if __name__ == "__main__":
    unittest.main()
