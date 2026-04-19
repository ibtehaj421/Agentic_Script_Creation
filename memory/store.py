from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from contextlib import asynccontextmanager
import sys, os

def _server_params(filename: str) -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=[os.path.join(os.path.dirname(os.path.dirname(__file__)), "mcp-servers", filename)]
    )

@asynccontextmanager
async def script_session():
    async with stdio_client(_server_params("script_tools_server.py")) as (r, w):
        async with ClientSession(r, w) as session:
            await session.initialize()
            yield session

@asynccontextmanager
async def character_session():
    async with stdio_client(_server_params("character_tools_server.py")) as (r, w):
        async with ClientSession(r, w) as session:
            await session.initialize()
            yield session