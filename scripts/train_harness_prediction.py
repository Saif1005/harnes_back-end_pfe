from __future__ import annotations

from harness_backend.training.prediction_trainer import prediction_report_to_dict, train_prediction_model


def main() -> None:
    report = train_prediction_model()
    print(prediction_report_to_dict(report))


if __name__ == "__main__":
    main()

