from backend.csi_demo_simulator import build_demo_snapshot
from backend.csi_spectrogram import build_demo_spectrogram, build_spectrogram


def test_build_spectrogram_downsamples_frames_to_heatmap():
    frames = [
        [1, 2, 3, 4, 10, 12, 14, 16],
        [2, 3, 4, 5, 11, 13, 15, 17],
        [3, 4, 5, 6, 12, 14, 16, 18],
    ]

    spectrogram = build_spectrogram(frames, time_bins=3, subcarrier_bins=4)

    assert spectrogram["time_bins"] == 3
    assert spectrogram["subcarrier_bins"] == 4
    assert len(spectrogram["rows"]) == 3
    assert all(len(row) == 4 for row in spectrogram["rows"])
    assert spectrogram["rows"][0][0] == 0
    assert spectrogram["rows"][-1][-1] == 100
    assert spectrogram["ascii"].isascii()


def test_demo_spectrogram_uses_snapshot_fingerprint_shape():
    snapshot = build_demo_snapshot("walking")

    spectrogram = build_demo_spectrogram(snapshot, time_bins=8, subcarrier_bins=8)

    assert spectrogram["source"] == "demo_fingerprint"
    assert spectrogram["time_bins"] == 8
    assert spectrogram["subcarrier_bins"] == 8
    assert len(spectrogram["rows"]) == 8
