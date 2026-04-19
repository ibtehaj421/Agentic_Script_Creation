# test_llm.py
import asyncio
from config import llm_call

async def main():
    result = await llm_call(
        prompt="Say hello in one sentence.",
        system="You are a helpful assistant."
    )
    print(f"result: '{result}'")
    print(f"length: {len(result)}")

asyncio.run(main())