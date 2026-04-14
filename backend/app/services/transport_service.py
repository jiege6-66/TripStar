"""城际交通查询服务 - 直接通过 mcp Python SDK 调用 12306 / 航班 MCP Server"""

import asyncio
import json
import logging

logger = logging.getLogger(__name__)


async def _call_mcp_tool(server_cmd: list[str], tool_name: str, args: dict) -> str:
    """通用：启动 MCP 子进程，调用一次工具，返回文本结果，然后关闭。"""
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        server_params = StdioServerParameters(command=server_cmd[0], args=server_cmd[1:])
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, args)
                if result.content:
                    return result.content[0].text if hasattr(result.content[0], "text") else str(result.content[0])
                return ""
    except Exception as e:
        logger.warning(f"MCP 工具调用失败 ({tool_name}): {e}")
        return ""


def _format_train_result(raw: str, from_city: str, to_city: str) -> str:
    """把 12306 JSON 结果格式化为一句话摘要。"""
    if not raw:
        return ""
    try:
        trains = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(trains, list) or not trains:
            return ""
        lines = []
        for t in trains[:3]:
            code = t.get("start_train_code", "")
            dep = t.get("start_time", "")
            arr = t.get("arrive_time", "")
            dur = t.get("lishi", "")
            prices = t.get("prices", [])
            price_2 = next((p["price"] for p in prices if p.get("short") == "ze"), None)
            price_1 = next((p["price"] for p in prices if p.get("short") == "zy"), None)
            price_str = ""
            if price_2:
                price_str += f"二等座¥{price_2}"
            if price_1:
                price_str += f" / 一等座¥{price_1}"
            from_st = t.get("from_station", from_city)
            to_st = t.get("to_station", to_city)
            lines.append(f"{code} {from_st}→{to_st} {dep}-{arr}（{dur}）{price_str}")
        return "【火车】" + "；".join(lines)
    except Exception:
        return f"【火车】{raw[:200]}" if raw else ""


def _format_flight_result(raw: str, from_city: str, to_city: str) -> str:
    """把 FlightTicketMCP 结果格式化为摘要。"""
    if not raw:
        return ""
    try:
        if raw.startswith("{") or raw.startswith("["):
            data = json.loads(raw)
            if isinstance(data, dict):
                flights = data.get("flights", data.get("data", []))
            else:
                flights = data
            if not flights:
                return ""
            lines = []
            for f in flights[:2]:
                fn = f.get("flight_number", f.get("flightNo", ""))
                dep = f.get("dep_time", f.get("departureTime", ""))
                arr = f.get("arr_time", f.get("arrivalTime", ""))
                dur = f.get("duration", "")
                price = f.get("price", f.get("lowestPrice", ""))
                price_str = f"约¥{price}" if price else ""
                lines.append(f"{fn} {dep}-{arr}（{dur}）{price_str}")
            return "【航班】" + "；".join(lines)
        return f"【航班】{raw[:200]}"
    except Exception:
        return f"【航班】{raw[:200]}" if raw else ""


async def query_transport(from_city: str, to_city: str, date: str) -> str:
    """
    查询 from_city → to_city 在 date 的城际交通方案。
    并发查询火车+航班，合并返回文字摘要。失败时返回空字符串。

    Args:
        from_city: 出发城市（中文）
        to_city: 到达城市（中文）
        date: 日期 YYYY-MM-DD

    Returns:
        格式化的交通方案摘要字符串
    """
    train_task = asyncio.create_task(_call_mcp_tool(
        ["uvx", "12306-mcp"],
        "get-tickets",
        {
            "fromStation": from_city,
            "toStation": to_city,
            "date": date,
            "trainFilterFlags": "GD",
            "sortFlag": "duration",
            "limitedNum": 3,
            "format": "json",
        }
    ))

    flight_task = asyncio.create_task(_call_mcp_tool(
        ["uvx", "flight-ticket-mcp-server@latest"],
        "searchFlightRoutes",
        {
            "departure_city": from_city,
            "destination_city": to_city,
            "departure_date": date,
        }
    ))

    train_raw, flight_raw = await asyncio.gather(train_task, flight_task, return_exceptions=True)

    parts = []

    train_str = _format_train_result(
        "" if isinstance(train_raw, Exception) else train_raw,
        from_city, to_city
    )
    if train_str:
        parts.append(train_str)

    flight_str = _format_flight_result(
        "" if isinstance(flight_raw, Exception) else flight_raw,
        from_city, to_city
    )
    if flight_str:
        parts.append(flight_str)

    return "\n".join(parts)
