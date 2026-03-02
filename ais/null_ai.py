"""AI that does nothing — useful for testing."""
from systems.ai.base import BaseAI


class NullAI(BaseAI):
    ai_id = "null"
    ai_name = "Null AI"

    def on_start(self) -> None:
        pass

    def on_step(self, iteration: int) -> None:
        pass
