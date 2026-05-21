import matplotlib

matplotlib.use("Agg")  # Headless mode: do not open GUI windows
import matplotlib.pyplot as plt
import numpy as np
import logging

logger = logging.getLogger(__name__)


def plot_raw_vs_filtered(
    raw_signal: list,
    filtered_signal: list,
    save_path: str,
    title: str = "Gemma 4 E4B Assisted CSI Noise Filtering",
):
    """
    Plots the raw signal versus the filtered signal and saves it as a PNG file.
    """
    if not raw_signal:
        logger.warning("Empty raw signal. Cannot generate plot.")
        return

    raw_arr = np.array(raw_signal, dtype=float)
    filtered_arr = np.array(filtered_signal, dtype=float)

    plt.figure(figsize=(12, 6))

    # Grid lines and style
    plt.grid(True, which="both", linestyle="--", alpha=0.5)

    # Plotting signals
    plt.plot(
        raw_arr,
        label="Raw CSI Signal (Mean Subcarrier)",
        color="#E76F51",
        alpha=0.6,
        linewidth=1.5,
    )
    plt.plot(filtered_arr, label="Filtered CSI Signal", color="#264653", linewidth=2.0)

    plt.title(title, fontsize=14, fontweight="bold", pad=15)
    plt.xlabel("Sample Index", fontsize=12)
    plt.ylabel("CSI Subcarrier Amplitude (Mean)", fontsize=12)

    plt.legend(loc="upper right", framealpha=0.9, facecolor="#fdfdfd")
    plt.tight_layout()

    try:
        plt.savefig(save_path, dpi=150)
        logger.info(f"Plot successfully saved to {save_path}")
    except Exception as e:
        logger.error(f"Failed to save plot to {save_path}: {e}")
    finally:
        plt.close()
