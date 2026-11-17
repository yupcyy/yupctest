
from openai import AsyncOpenAI


class DeepSeekProvider:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        *,
        usage_service=None,
    ):
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=90,
            max_retries=1,
        )
        self.model = model
        self.usage_service = usage_service

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        conversation_id: str | None = None,
        max_tokens: int = 500,
    ) -> str:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            stream=False,
        )

        if self.usage_service is not None and conversation_id:
            await self.usage_service.record(
                response,
                model=self.model,
                conversation_id=conversation_id,
                operation="chat",
            )

        return (
            response.choices[0].message.content
            or "（模型未返回文本）"
        )

    async def close(self) -> None:
        await self.client.close()
