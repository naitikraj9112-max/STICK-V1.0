"""Abstract provider interfaces for multimedia generation."""

from abc import ABC, abstractmethod
from pathlib import Path


class ImageProvider(ABC):
    @property
    @abstractmethod
    def available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def generate(self, prompt: str, output_path: Path, correlation_id: str = "-") -> dict:
        raise NotImplementedError


class TextProvider(ABC):
    @property
    @abstractmethod
    def available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def generate(self, prompt: str, correlation_id: str = "-") -> str:
        raise NotImplementedError


class TTSProvider(ABC):
    @property
    @abstractmethod
    def available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def synthesize(self, text: str, output_path: Path, correlation_id: str = "-") -> dict:
        raise NotImplementedError
