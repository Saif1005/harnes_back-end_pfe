from __future__ import annotations

from harness_backend.training.classification_trainer import report_to_dict, train_classification_model


def main() -> None:
    for model_name in ("camembert-classifier", "xlm-roberta-large-classifier"):
        report = train_classification_model(model_name=model_name)
        print(report_to_dict(report))


if __name__ == "__main__":
    main()

