import asyncio
import sys
import json
import pytest
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from log import get_logger

from models.names_prefixes import ReleaseType

logger = get_logger(__name__)

SERVER_PATH = "./main.py"
EXPECTED_TOOLS = [
    "fetch_release_by_name",
    "prepare_release_for_musicbrainz",
    "list_all_releases",
    "get_new_catalog_id",
]


@pytest.mark.asyncio
async def test_mcp_server_connection():
    async with AsyncExitStack() as stack:
        server_params = StdioServerParameters(
            command=sys.executable, args=[SERVER_PATH], env=None
        )
        read, write = await stack.enter_async_context(stdio_client(server_params))
        client = ClientSession(read, write)
        async with client:
            await client.initialize()
            result = await client.list_tools()
            tool_names = [tool.name for tool in result.tools]


@pytest.mark.asyncio
async def test_fetch_release_by_name():
    async with AsyncExitStack() as stack:
        server_params = StdioServerParameters(
            command=sys.executable, args=[SERVER_PATH], env=None
        )
        read, write = await stack.enter_async_context(stdio_client(server_params))
        client = ClientSession(read, write)
        async with client:
            await client.initialize()
            result = await client.call_tool(
                name="fetch_release_by_name",
                arguments={
                    "artist_name": "Christian Schwöbel",
                    "release_title": "Dystopian Pulse",
                },
            )
            assert hasattr(result, "content")
            assert len(result.content) > 0

            print(f"DEBUG: result.content[0].text = {result.content[0].text!r}")
            # Parse the JSON string from the first content item to verify fields
            content_data = json.loads(result.content[0].text)
            assert "artist_name" in content_data
            assert "release_title" in content_data
            assert "label" in content_data
            assert "mc_catalog_id" in content_data
            assert "cd_catalog_id" in content_data
            assert "lp_catalog_id" in content_data
            assert "digital_catalog_id" in content_data
            assert "archive_catalog_id" in content_data
            assert "tracks" in content_data
            assert "release_date" in content_data
            assert len(content_data["tracks"]) > 0


@pytest.mark.asyncio
async def test_get_new_digital_catalog_id():
    async with AsyncExitStack() as stack:
        server_params = StdioServerParameters(
            command=sys.executable, args=[SERVER_PATH], env=None
        )
        read, write = await stack.enter_async_context(stdio_client(server_params))
        client = ClientSession(read, write)
        async with client:
            await client.initialize()
            result = await client.call_tool(
                name="get_new_catalog_id",
                arguments={"release_type": ReleaseType.DIGITAL},
            )
            assert hasattr(result, "content")
            assert len(result.content) > 0
            assert result.isError is False
            assert result.content[0].text.startswith(ReleaseType.DIGITAL.value)
            logger.debug(
                f"get_new_catalog_id result.content[0].text = {result.content[0].text!r}"
            )


@pytest.mark.asyncio
async def test_get_new_cassette_catalog_id():
    async with AsyncExitStack() as stack:
        server_params = StdioServerParameters(
            command=sys.executable, args=[SERVER_PATH], env=None
        )
        read, write = await stack.enter_async_context(stdio_client(server_params))
        client = ClientSession(read, write)
        async with client:
            await client.initialize()
            result = await client.call_tool(
                name="get_new_catalog_id",
                arguments={"release_type": ReleaseType.CASSETTE},
            )
            assert hasattr(result, "content")
            assert len(result.content) > 0
            assert result.isError is False
            assert result.content[0].text.startswith(ReleaseType.CASSETTE.value)
            logger.debug(
                f"get_new_catalog_id result.content[0].text = {result.content[0].text!r}"
            )


@pytest.mark.asyncio
async def test_get_new_cd_catalog_id():
    async with AsyncExitStack() as stack:
        server_params = StdioServerParameters(
            command=sys.executable, args=[SERVER_PATH], env=None
        )
        read, write = await stack.enter_async_context(stdio_client(server_params))
        client = ClientSession(read, write)
        async with client:
            await client.initialize()
            result = await client.call_tool(
                name="get_new_catalog_id",
                arguments={"release_type": ReleaseType.CD},
            )
            assert hasattr(result, "content")
            assert len(result.content) > 0
            assert result.isError is False
            assert result.content[0].text.startswith(ReleaseType.CD.value)
            logger.debug(
                f"get_new_catalog_id result.content[0].text = {result.content[0].text!r}"
            )


@pytest.mark.asyncio
async def test_get_new_archive_catalog_id():
    async with AsyncExitStack() as stack:
        server_params = StdioServerParameters(
            command=sys.executable, args=[SERVER_PATH], env=None
        )
        read, write = await stack.enter_async_context(stdio_client(server_params))
        client = ClientSession(read, write)
        async with client:
            await client.initialize()
            result = await client.call_tool(
                name="get_new_catalog_id",
                arguments={"release_type": ReleaseType.ARCHIVE},
            )
            assert hasattr(result, "content")
            assert len(result.content) > 0
            assert result.isError is False
            assert result.content[0].text.startswith(ReleaseType.ARCHIVE.value)
            logger.debug(
                f"get_new_catalog_id result.content[0].text = {result.content[0].text!r}"
            )
