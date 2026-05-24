import unittest
import plotly.graph_objects as go
from frontend.app import get_skeleton_coords, generate_3d_observatory


CONFIRMED = {
    "score": 95,
    "level": "HIGH",
    "alert_allowed": True,
    "label": "CONFIRMED HUMAN",
    "reasons": [],
}

class TestObservatoryGeometry(unittest.TestCase):
    def test_get_skeleton_coords_fall(self):
        # When a fall is detected, all joints should collapse to floor level Z = 0.15
        telemetry = {
            "fall_alert": True,
            "presence": True,
            "presence_confidence": CONFIRMED,
            "resp_bpm": 12.0,
            "variance": 15.0,
            "apnea_status": {"is_apnea": False, "is_hypopnea": False}
        }
        joints, draw_bed = get_skeleton_coords(telemetry)
        self.assertFalse(draw_bed)
        self.assertEqual(len(joints), 15)  # 14 joints + hip_center
        for joint, coord in joints.items():
            self.assertAlmostEqual(coord[2], 0.15, places=5, msg=f"Joint {joint} Z-coordinate is not 0.15 during fall")

    def test_get_skeleton_coords_sleeping(self):
        # Sleeping when presence is active and either apnea/hypopnea or low variance
        telemetry = {
            "fall_alert": False,
            "presence": True,
            "presence_confidence": CONFIRMED,
            "resp_bpm": 15.0,
            "variance": 0.5,
            "apnea_status": {"is_apnea": True, "is_hypopnea": False}
        }
        joints, draw_bed = get_skeleton_coords(telemetry)
        self.assertTrue(draw_bed)
        self.assertIn("head", joints)
        self.assertIn("hip_center", joints)
        
        # Z-coordinates should reflect sleeping state (around bed_z = 0.4 plus body thickness)
        self.assertGreater(joints["head"][2], 0.3)
        self.assertLess(joints["head"][2], 0.6)

    def test_get_skeleton_coords_fitness(self):
        # Fitness when presence is active and variance >= 1.0
        telemetry = {
            "fall_alert": False,
            "presence": True,
            "presence_confidence": CONFIRMED,
            "resp_bpm": 24.0,
            "variance": 2.5,
            "apnea_status": {"is_apnea": False, "is_hypopnea": False}
        }
        joints, draw_bed = get_skeleton_coords(telemetry)
        self.assertFalse(draw_bed)
        self.assertIn("head", joints)
        self.assertIn("ankle_l", joints)
        # Left ankle should be on the floor (Z = 0.0)
        self.assertAlmostEqual(joints["ankle_l"][2], 0.0, places=5)
        # Head Z should fluctuate between standing/squatting range
        self.assertTrue(1.0 <= joints["head"][2] <= 1.8)

    def test_get_skeleton_coords_idle(self):
        # Idle state (upright standing) when presence is inactive
        telemetry = {
            "fall_alert": False,
            "presence": False,
            "resp_bpm": 16.0,
            "variance": 0.3,
            "apnea_status": {"is_apnea": False, "is_hypopnea": False}
        }
        joints, draw_bed = get_skeleton_coords(telemetry)
        self.assertFalse(draw_bed)
        # Head should be high in idle state (~1.7 plus small breathing jitter)
        self.assertGreater(joints["head"][2], 1.6)
        self.assertLess(joints["head"][2], 1.8)

    def test_generate_3d_observatory(self):
        # Check that generate_3d_observatory returns a valid Plotly Figure
        telemetry = {
            "presence": True,
            "presence_confidence": CONFIRMED,
            "resp_bpm": 14.0,
            "variance": 0.8,
            "fall_alert": False,
            "apnea_status": {
                "is_apnea": False,
                "is_hypopnea": False
            }
        }
        stats = {
            "rssi": -50,
            "noise": -96
        }
        fig = generate_3d_observatory(telemetry, stats)
        self.assertIsInstance(fig, go.Figure)
        
        # Verify it has traces (grid, wifi waves, sensor node, skeleton, etc.)
        self.assertGreater(len(fig.data), 0)
        
        # Grid trace should be markers
        self.assertEqual(fig.data[0].mode, 'markers')
        
        # Wi-Fi waves should be lines
        self.assertEqual(fig.data[1].mode, 'lines')

if __name__ == "__main__":
    unittest.main()
