"""内网 AS 传输的占位模块；内网部署时替换为真实实现。"""

from app.logger import logger
from config.config import Settings
from custom.model_transport import ModelTransportError
from models.generation import ModelRequestContext


class AsOpenAiWsTransport:
    """保留运行时依赖的接口，允许未使用 AS 通道的环境正常初始化。"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def generate(
        self,
        messages: list[dict[str, str]],
        request_context: ModelRequestContext | None = None,
    ) -> str:
        reason = "AS 通道仅包含占位实现，请在内网部署真实传输与鉴权模块后使用。"
        logger.error(f"[AS Transport] implementation_unavailable reason={reason}")
        raise ModelTransportError(reason)
