"""음성 백엔드 에이전트. 모두 Harness.runner 로 돌고, 실패하면 템플릿으로 물러난다."""

from pathlib import Path

PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_prompt(name: str, store: dict) -> str:
    """voice/agents/prompts/<name> 을 읽어 {가게이름}, {업종} 을 채운다. 매번 읽으므로 고치면 바로 반영된다."""
    text = (PROMPTS_DIR / name).read_text(encoding="utf-8")
    return text.replace("{가게이름}", store.get("name", "")).replace("{업종}", store.get("category", ""))
