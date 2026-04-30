from __future__ import annotations

from abc import ABC, abstractmethod

from harness_backend.core.state import HarnessState


class CheckpointStore(ABC):
    @abstractmethod
    def save(self, state: HarnessState, node_name: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def load_latest(self, run_id: str) -> HarnessState | None:
        raise NotImplementedError

