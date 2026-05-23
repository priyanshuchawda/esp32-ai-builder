import argparse
from pathlib import Path

from backend.live_label_evaluator import evaluate_live_labels


def main():
    parser = argparse.ArgumentParser(description="Evaluate local live CSI labels.")
    parser.add_argument("--labels-dir", default="backend/data/live_labels")
    args = parser.parse_args()

    report = evaluate_live_labels(Path(args.labels_dir))
    readiness = report["readiness"]
    model = report["model"]
    evaluation = report["evaluation"]
    confusion = report["confusion"]

    status = "PASS" if readiness["ready"] and evaluation["accuracy"] >= 0.8 else "FAIL"
    print(f"{status} | live label evaluator")
    print(f"READY {str(readiness['ready']).lower()}")
    print(f"SESSIONS {evaluation['sessions']}")
    print(f"EMPTY_SESSIONS {readiness['empty_sessions']}")
    print(f"OCCUPIED_SESSIONS {readiness['occupied_sessions']}")
    print(f"FEATURE {model['feature']}")
    print(f"THRESHOLD {model['threshold']}")
    print(f"EMPTY_MAX {model['empty_max']}")
    print(f"OCCUPIED_MIN {model['occupied_min']}")
    print(f"ACCURACY {evaluation['accuracy']:.4f}")
    print(f"CONFUSION {confusion}")
    for prediction in report["predictions"]:
        print(
            "PREDICTION "
            f"{prediction['file']} "
            f"label={prediction['label']} "
            f"actual={prediction['actual']} "
            f"predicted={prediction['predicted']} "
            f"value={prediction['feature_value']}"
        )
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
