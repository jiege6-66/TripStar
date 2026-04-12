"""多智能体旅行规划系统"""

import json
import asyncio
import os
from typing import Dict, Any, List, Callable, Awaitable, Optional
from hello_agents import SimpleAgent
from hello_agents.tools import MCPTool
from ..services.llm_service import get_llm
from ..models.schemas import TripRequest, TripPlan, DayPlan, Attraction, Meal, WeatherInfo, Location, Hotel
from ..config import get_settings

# ============ Agent提示词 ============

ATTRACTION_AGENT_PROMPT = """你是景点搜索专家。你的任务是根据城市和用户偏好搜索合适的景点。

**重要提示:**
1. 你必须使用工具来搜索景点!不要自己编造景点信息!
2. 系统为你绑定的真实工具名称叫做 `amap_maps_text_search`，你**只能而且必须**原样输出这个名字。绝对不要输出 `amap` 或者 `action=...` 这样的自定义格式！

**工具调用格式:**
使用maps_text_search工具时,必须严格按照以下单行格式输出，**不要带任何多余的字符或JSON block**:
`[TOOL_CALL:amap_maps_text_search:keywords=景点关键词,city=城市名]`

**示例:**
用户: "搜索北京的历史文化景点"
你的回复: [TOOL_CALL:amap_maps_text_search:keywords=历史文化,city=北京]

用户: "搜索上海的公园"
你的回复: [TOOL_CALL:amap_maps_text_search:keywords=公园,city=上海]

**注意:**
1. 必须使用工具,不要直接回答
2. 格式必须完全正确,包括方括号和冒号
3. 必须输出 `amap_maps_text_search` 作为工具名。
"""

WEATHER_AGENT_PROMPT = """你是天气查询专家。你的任务是查询指定城市的天气信息。

**重要提示:**
1. 你必须使用工具来查询天气!不要自己编造天气信息!
2. 系统为你绑定的真实工具名称叫做 `amap_maps_weather`，你**只能而且必须**原样输出这个名字。

**工具调用格式:**
使用maps_weather工具时,必须严格按照以下单行格式输出，**不要带任何多余的字符或JSON block**:
`[TOOL_CALL:amap_maps_weather:city=城市名]`

**示例:**
用户: "查询北京天气"
你的回复: [TOOL_CALL:amap_maps_weather:city=北京]

用户: "上海的天气怎么样"
你的回复: [TOOL_CALL:amap_maps_weather:city=上海]

**注意:**
1. 必须使用工具,不要直接回答
2. 格式必须完全正确,包括方括号和冒号
3. 必须输出 `amap_maps_weather` 作为工具名。
"""

HOTEL_AGENT_PROMPT = """你是酒店推荐专家。你的任务是根据城市和景点位置推荐合适的酒店。

**重要提示:**
1. 你必须使用工具来搜索酒店!不要自己编造酒店信息!
2. 系统为你绑定的真实工具名称叫做 `amap_maps_text_search`，你**只能而且必须**原样输出这个名字。

**工具调用格式:**
使用maps_text_search工具搜索酒店时,必须严格按照以下单行格式输出，**不要带任何多余的字符或JSON block**:
`[TOOL_CALL:amap_maps_text_search:keywords=酒店,city=城市名]`

**示例:**
用户: "搜索北京的酒店"
你的回复: [TOOL_CALL:amap_maps_text_search:keywords=酒店,city=北京]

**注意:**
1. 必须使用工具,不要直接回答
2. 格式必须完全正确,包括方括号和冒号
3. 关键词使用"酒店"或"宾馆"
4. 必须输出 `amap_maps_text_search` 作为工具名。
"""

PLANNER_AGENT_PROMPT = """你是行程规划专家。你的任务是根据景点信息和天气信息,生成详细的旅行计划。

请严格按照以下JSON格式返回旅行计划:
```json
{
  "city": "城市名称",
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD",
  "days": [
    {
      "date": "YYYY-MM-DD",
      "day_index": 0,
      "description": "第1天行程概述",
      "transportation": "交通方式",
      "accommodation": "住宿类型",
      "hotel": {
        "name": "酒店名称",
        "address": "酒店地址",
        "location": {"longitude": 116.397128, "latitude": 39.916527},
        "price_range": "300-500元",
        "rating": "4.5",
        "distance": "距离景点2公里",
        "type": "经济型酒店",
        "estimated_cost": 400
      },
      "attractions": [
        {
          "name": "景点名称",
          "address": "详细地址",
          "location": {"longitude": 116.397128, "latitude": 39.916527},
          "visit_duration": 120,
          "description": "景点详细描述",
          "category": "景点类别",
          "ticket_price": 60,
          "reservation_required": false,
          "reservation_tips": ""
        }
      ],
      "meals": [
        {"type": "breakfast", "name": "早餐推荐", "description": "早餐描述", "estimated_cost": 30},
        {"type": "lunch", "name": "午餐推荐", "description": "午餐描述", "estimated_cost": 50},
        {"type": "dinner", "name": "晚餐推荐", "description": "晚餐描述", "estimated_cost": 80}
      ]
    }
  ],
  "weather_info": [
    {
      "date": "YYYY-MM-DD",
      "day_weather": "晴",
      "night_weather": "多云",
      "day_temp": 25,
      "night_temp": 15,
      "wind_direction": "南风",
      "wind_power": "1-3级"
    }
  ],
  "overall_suggestions": "总体建议",
  "budget": {
    "total_attractions": 180,
    "total_hotels": 1200,
    "total_meals": 480,
    "total_transportation": 200,
    "total": 2060
  }
}
```

**⚠️ JSON 格式关键约束（违反将导致系统崩溃）：**
- budget 中所有费用字段（total_attractions、total_hotels、total_meals、total_transportation、total）必须是**纯数字**，绝对禁止出现算术表达式！
  - ✅ 正确: "total_attractions": 324
  - ❌ 错误: "total_attractions": 30+54+120+120=324
  - ❌ 错误: "total_attractions": "324元"
- ticket_price、estimated_cost 等所有价格字段也必须是纯数字，不带单位

**重要提示:**
1. weather_info数组必须包含每一天的天气信息
2. 温度必须是纯数字(不要带°C等单位)
3. 每天安排2-3个景点
4. 考虑景点之间的距离和游览时间
5. 每天必须包含早中晚三餐
6. 提供实用的旅行建议
7. **必须包含预算信息**:
   - 景点门票价格(ticket_price)
   - 餐饮预估费用(estimated_cost)
   - 酒店预估费用(estimated_cost)
   - 预算汇总(budget)包含各项总费用
9. **预约信息透传**: 如果景点搜索数据中包含 reservation_required 和 reservation_tips 字段，请务必将它们完整保留在对应景点的JSON中。需要预约的景点请在 description 中也提醒游客提前预约
8. **景点图片**: 不需要在JSON中填写 image_url 字段，图片由前端根据景点名称自动从小红书获取。
"""


class MultiAgentTripPlanner:
    """多智能体旅行规划系统"""

    def __init__(self):
        """初始化多智能体系统"""
        print("🔄 开始初始化多智能体旅行规划系统...")

        try:
            settings = get_settings()
            self.llm = get_llm()

            # 创建共享的MCP工具(只创建一次)
            print("  - 创建共享MCP工具...")
            self.amap_tool = MCPTool(
                name="amap",
                description="高德地图服务",
                server_command=["uvx", "amap-mcp-server"],
                env={"AMAP_MAPS_API_KEY": settings.vite_amap_web_key},
                auto_expand=True
            )
            # 当前 hello_agents 版本不会自动把 MCPTool 标记为 expandable，
            # 手动开启后才能把 `amap_maps_*` 子工具注册到 Agent。
            self.amap_tool.expandable = True

            # 取消高德景点 Agent,改用原生小红书服务
            # print("  - 创建景点搜索Agent...")
            # self.attraction_agent = SimpleAgent(
            #     name="景点搜索专家",
            #     llm=self.llm,
            #     system_prompt=ATTRACTION_AGENT_PROMPT
            # )
            # self.attraction_agent.add_tool(self.amap_tool)

            # 创建天气查询Agent
            print("  - 创建天气查询Agent...")
            self.weather_agent = SimpleAgent(
                name="天气查询专家",
                llm=self.llm,
                system_prompt=WEATHER_AGENT_PROMPT
            )
            self.weather_agent.add_tool(self.amap_tool)

            # 创建酒店推荐Agent
            print("  - 创建酒店推荐Agent...")
            self.hotel_agent = SimpleAgent(
                name="酒店推荐专家",
                llm=self.llm,
                system_prompt=HOTEL_AGENT_PROMPT
            )
            self.hotel_agent.add_tool(self.amap_tool)

            # 创建行程规划Agent(不需要工具)
            print("  - 创建行程规划Agent...")
            self.planner_agent = SimpleAgent(
                name="行程规划专家",
                llm=self.llm,
                system_prompt=PLANNER_AGENT_PROMPT
            )

            print(f"✅ 多智能体系统初始化成功")
            # print(f"   景点搜索Agent: {len(self.attraction_agent.list_tools())} 个工具")
            print(f"   天气查询Agent: {len(self.weather_agent.list_tools())} 个工具")
            print(f"   酒店推荐Agent: {len(self.hotel_agent.list_tools())} 个工具")

        except Exception as e:
            print(f"❌ 多智能体系统初始化失败: {str(e)}")
            import traceback
            traceback.print_exc()
            raise

    async def _emit_progress(
        self,
        progress_callback: Optional[Callable[[str, str, int], Awaitable[None] | None]],
        stage: str,
        message: str,
        progress: int,
    ) -> None:
        """向上层回调任务进度（支持同步/异步回调）。"""
        if progress_callback is None:
            return
        result = progress_callback(stage, message, progress)
        if asyncio.iscoroutine(result):
            await result
    
    async def plan_trip(
        self,
        request: TripRequest,
        progress_callback: Optional[Callable[[str, str, int], Awaitable[None] | None]] = None
    ) -> TripPlan:
        """
        使用多智能体协作生成旅行计划（并发优化版）

        步骤1-3（景点/天气/酒店）通过 asyncio.gather 并发执行，
        将耗时从 T1+T2+T3 缩短为 max(T1, T2, T3)。
        步骤4（行程规划）依赖前三步结果，保持串行。

        Args:
            request: 旅行请求

        Returns:
            旅行计划
        """
        try:
            print(f"\n{'='*60}")
            print(f"🚀 开始多智能体协作规划旅行（并发优化模式）...")
            print(f"目的地: {request.city}")
            print(f"日期: {request.start_date} 至 {request.end_date}")
            print(f"天数: {request.travel_days}天")
            print(f"偏好: {', '.join(request.preferences) if request.preferences else '无'}")
            print(f"{'='*60}\n")

            # ========== 串行阶段: 步骤1-3 依次执行 ==========
            print("⏳ 依次执行步骤1-3: 搜索景点 -> 查询天气 -> 搜索酒店...")

            # 构建各Agent的查询
            weather_query = f"请查询{request.city}的天气信息"
            hotel_query = f"请搜索{request.city}的{request.accommodation}酒店"

            # 依次执行,避免多个线程同时启动 uvx 子进程导致资源竞争和超时
            print("  [1/3] 正在使用小红书服务搜索景点...")
            await self._emit_progress(progress_callback, "attraction_search", "正在使用小红书搜索景点...", 30)
            from ..services.xhs_service import search_xhs_attractions
            keywords = request.preferences[0] if request.preferences else "景点"
            attraction_response = await asyncio.to_thread(search_xhs_attractions, request.city, keywords)
            print(f"📍 景点搜索结果: {attraction_response[:200]}...")

            print("  [2/3] 正在查询天气...")
            await self._emit_progress(progress_callback, "weather_search", "正在查询天气信息...", 50)
            weather_response = await asyncio.to_thread(self.weather_agent.run, weather_query)
            print(f"🌤️  天气查询结果: {weather_response[:200]}...")

            print("  [3/3] 正在搜索酒店...")
            await self._emit_progress(progress_callback, "hotel_search", "正在搜索酒店推荐...", 70)
            hotel_response = await asyncio.to_thread(self.hotel_agent.run, hotel_query)
            print(f"🏨 酒店搜索结果: {hotel_response[:200]}...")

            print(f"\n✅ 基础信息搜集完成\n")

            # ========== 串行阶段: 步骤4 整合生成 ==========
            print("📋 步骤4: 生成行程计划...")
            await self._emit_progress(progress_callback, "planning", "正在生成旅行计划...", 85)
            print(
                f"🧾 规划上下文长度: 景点={len(attraction_response)} 天气={len(weather_response)} 酒店={len(hotel_response)}"
            )
            planner_response = await self._run_planner_with_retry(
                request,
                attraction_response,
                weather_response,
                hotel_response,
            )
            print(f"行程规划结果: {planner_response[:300]}...\n")

            # 解析最终计划
            trip_plan = self._parse_response(planner_response, request)

            print(f"{'='*60}")
            print(f"✅ 旅行计划生成完成!")
            print(f"{'='*60}\n")

            return trip_plan

        except Exception as e:
            print(f"❌ 生成旅行计划失败: {str(e)}")
            import traceback
            traceback.print_exc()
            raise RuntimeError(f"旅行计划生成失败: {str(e)}") from e
    
    def _build_attraction_query(self, request: TripRequest) -> str:
        """构建景点搜索查询 - 直接包含工具调用"""
        keywords = []
        if request.preferences:
            # 只取第一个偏好作为关键词
            keywords = request.preferences[0]
        else:
            keywords = "景点"

        # 直接返回工具调用格式，使用正确的工具名和严格的格式
        query = f"请使用amap_maps_text_search工具搜索{request.city}的{keywords}相关的景点。\n非常重要：你必须直接输出 `[TOOL_CALL:amap_maps_text_search:keywords={keywords},city={request.city}]`，不要附带任何多余的 JSON 或文字说明！"
        return query


    async def _run_planner_with_retry(
        self,
        request: TripRequest,
        attractions: str,
        weather: str,
        hotels: str,
    ) -> str:
        """规划阶段使用更长超时，并在超时后重试一次。"""
        timeout = int(os.getenv("TRIP_PLANNER_TIMEOUT", "180"))
        planner_query = self._build_planner_query(request, attractions, weather, hotels)

        try:
            return await asyncio.to_thread(
                self.planner_agent.run,
                planner_query,
                timeout=timeout,
                temperature=0.2,
            )
        except Exception as exc:
            err_text = str(exc).lower()
            if "timeout" not in err_text and "timed out" not in err_text:
                raise

            print("⚠️  首次行程规划超时，正在重试一次...")
            planner_query += (
                "\n\n**补充要求:** 如果部分辅助信息不足，请使用保守、常见、可执行的建议补齐，"
                "但必须输出完整合法的 JSON，不要输出解释性文字。"
            )
            return await asyncio.to_thread(
                self.planner_agent.run,
                planner_query,
                timeout=timeout,
                temperature=0.2,
            )

    def _build_planner_query(self, request: TripRequest, attractions: str, weather: str, hotels: str = "") -> str:
        """构建行程规划查询"""
        query = f"""请根据以下信息生成{request.city}的{request.travel_days}天旅行计划:

**基本信息:**
- 城市: {request.city}
- 日期: {request.start_date} 至 {request.end_date}
- 天数: {request.travel_days}天
- 交通方式: {request.transportation}
- 住宿: {request.accommodation}
- 偏好: {', '.join(request.preferences) if request.preferences else '无'}

**景点信息:**
{attractions}

**天气信息:**
{weather}

**酒店信息:**
{hotels}

**要求:**
1. 每天安排2-3个景点
2. 每天必须包含早中晚三餐
3. 每天推荐一个具体的酒店(从酒店信息中选择)
3. 考虑景点之间的距离和交通方式
4. 返回完整的JSON格式数据
5. 景点的经纬度坐标要真实准确
6. 如果天气或酒店信息不足，请基于保守、通用的旅行建议补齐，但不要输出“无法查询”之类的解释文字
"""
        if request.free_text_input:
            query += f"\n**额外要求:** {request.free_text_input}"

        return query
    
    def _sanitize_json_str(self, json_str: str) -> str:
        """清理大模型输出中常见的 JSON 格式污染"""
        import re as _re
        # 1. 移除可能包裹在外面的 ```json ... ``` 标记
        json_str = _re.sub(r'^```(?:json)?\s*', '', json_str.strip())
        json_str = _re.sub(r'```\s*$', '', json_str.strip())
        # 2. 移除 JS 风格注释 // ... 和 /* ... */
        json_str = _re.sub(r'//[^\n]*', '', json_str)
        json_str = _re.sub(r'/\*.*?\*/', '', json_str, flags=_re.DOTALL)
        # 3. 移除 JSON 值中的控制字符
        json_str = _re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', json_str)
        # 4. 修复尾部逗号: },] 或 },}
        json_str = _re.sub(r',\s*([\]\}])', r'\1', json_str)
        # 5. 修复中文引号和全角标点
        #    注意: 中文双引号""必须替换为单引号，因为它们通常出现在 JSON 字符串值内部
        #    如果替换为标准双引号会破坏 JSON 结构！
        json_str = json_str.replace('\u201c', "'").replace('\u201d', "'")
        json_str = json_str.replace('\u2018', "'").replace('\u2019', "'")
        json_str = json_str.replace('\uff1a', ':')
        json_str = json_str.replace('\uff0c', ',')
        # 6. 修复 LLM 在 budget 等数值字段中输出算术表达式的问题
        #    例如: "total_attractions": 30+54+120+120=324 → "total_attractions": 324
        #    模式: 冒号后面跟着 数字[+-*/]数字...=最终结果
        def _fix_arithmetic_expr(m):
            """将算术表达式替换为等号后的最终结果，若无等号则尝试 eval"""
            expr = m.group(1).strip()
            if '=' in expr:
                # 取等号后面的最终结果
                return m.group(0).replace(m.group(1), expr.split('=')[-1].strip())
            else:
                # 没有等号，尝试安全计算
                try:
                    result = eval(expr, {"__builtins__": {}}, {})
                    return m.group(0).replace(m.group(1), str(result))
                except Exception:
                    return m.group(0)
        # 匹配 JSON 键值对中冒号后的算术表达式（含 +、-、*、= 且以数字开头）
        json_str = _re.sub(
            r':\s*(\d+(?:\s*[+\-*/]\s*\d+)+(?:\s*=\s*\d+)?)',
            _fix_arithmetic_expr,
            json_str
        )
        return json_str
    
    def _fix_unescaped_quotes(self, json_str: str) -> str:
        """修复 JSON 字符串值内部未转义的双引号
        
        例如: "description": "这是"好的"景点" 
        修复为: "description": "这是'好的'景点"
        """
        import re as _re
        result = []
        i = 0
        in_string = False
        escape_next = False
        
        while i < len(json_str):
            ch = json_str[i]
            
            if escape_next:
                result.append(ch)
                escape_next = False
                i += 1
                continue
            
            if ch == '\\' and in_string:
                escape_next = True
                result.append(ch)
                i += 1
                continue
            
            if ch == '"':
                if not in_string:
                    in_string = True
                    result.append(ch)
                else:
                    # 看下一个非空白字符是否是 JSON 结构字符
                    rest = json_str[i+1:].lstrip()
                    if rest and rest[0] in (',', '}', ']', ':'):
                        # 这是真正的字符串结尾引号
                        in_string = False
                        result.append(ch)
                    elif not rest:
                        # 到末尾了，也是结尾引号
                        in_string = False
                        result.append(ch)
                    else:
                        # 内嵌的未转义引号，替换为单引号
                        result.append("'")
            else:
                result.append(ch)
            
            i += 1
        
        return ''.join(result)

    def _repair_truncated_json(self, json_str: str) -> str:
        """修复被 max_tokens 截断的不完整 JSON。

        策略：
        1. 如果最后一个字符在字符串值内部，先关闭该字符串。
        2. 移除最后一个不完整的键值对（trailing comma 之后的碎片）。
        3. 根据打开/关闭的括号差额，补齐缺失的 ] 和 }。
        """
        import re as _re

        s = json_str.rstrip()
        if not s:
            return s

        # --- Step 1: 关闭未终止的字符串 ---
        in_str = False
        escape = False
        for ch in s:
            if escape:
                escape = False
                continue
            if ch == '\\':
                escape = True
                continue
            if ch == '"':
                in_str = not in_str
        if in_str:
            # 去掉尾部可能的碎片转义符
            s = s.rstrip('\\')
            s += '"'

        # --- Step 2: 移除尾部不完整的键值对碎片 ---
        # 常见模式: 值字符串闭合后紧跟着换行但后面没有逗号/括号
        # 或者尾部是 "key": 但缺少值
        # 尝试反复去除尾部碎片直到以合法的 JSON 结构字符结尾
        for _ in range(10):
            stripped = s.rstrip()
            if not stripped:
                break
            last = stripped[-1]
            if last in ('}', ']', '"', '0', '1', '2', '3', '4', '5', '6', '7', '8', '9',
                        'e', 'l', 's'):
                # 'e' for true/false, 'l' for null, 's' unlikely but safe
                break
            # 当前尾部是非法字符(如冒号、逗号、空键名开头等)，回退一个 token
            s = stripped[:-1]

        # 移除尾部悬挂的逗号
        s = _re.sub(r',\s*$', '', s)

        # --- Step 3: 补齐缺失的闭合括号 ---
        open_braces = s.count('{') - s.count('}')
        open_brackets = s.count('[') - s.count(']')

        # 更精确: 扫描非字符串中的括号
        stack = []
        in_str2 = False
        esc2 = False
        for ch in s:
            if esc2:
                esc2 = False
                continue
            if ch == '\\' and in_str2:
                esc2 = True
                continue
            if ch == '"':
                in_str2 = not in_str2
                continue
            if in_str2:
                continue
            if ch in ('{', '['):
                stack.append(ch)
            elif ch == '}' and stack and stack[-1] == '{':
                stack.pop()
            elif ch == ']' and stack and stack[-1] == '[':
                stack.pop()

        # 用精确的 stack 逆序关闭
        closing = [']' if c == '[' else '}' for c in reversed(stack)]
        if closing:
            s += '\n' + ''.join(closing)

        return s

    def _llm_repair_json(self, broken_json: str) -> str:
        """使用 LLM 修复无法自动修复的 JSON（最后手段）"""
        llm = get_llm()
        # 只发送尾部 2000 字符以节省 token
        tail = broken_json[-2000:] if len(broken_json) > 2000 else broken_json
        head = broken_json[:500] if len(broken_json) > 500 else broken_json

        repair_prompt = f"""以下是一段被截断的旅行计划 JSON，请你补全它使其成为合法的 JSON。
只输出修复后的完整 JSON，不要输出任何解释文字。

开头部分:
{head}

...(中间省略)...

尾部被截断部分:
{tail}
"""
        try:
            response = llm._client.chat.completions.create(
                model=llm.model,
                messages=[{"role": "user", "content": repair_prompt}],
                temperature=0.0,
                max_tokens=1500,
            )
            content = response.choices[0].message.content or ""
            # 从修复结果中提取 JSON
            import re as _re
            if "```json" in content:
                start = content.find("```json") + 7
                end = content.find("```", start)
                if end > start:
                    return content[start:end].strip()
            if "```" in content:
                start = content.find("```") + 3
                end = content.find("```", start)
                if end > start:
                    return content[start:end].strip()
            match = _re.search(r'\{[\s\S]*\}', content)
            if match:
                return match.group()
            return content
        except Exception as e:
            print(f"⚠️  LLM 修复 JSON 失败: {e}")
            return broken_json

    def _parse_response(self, response: str, request: TripRequest) -> TripPlan:
        """
        解析Agent响应，带有多层容错清理
        
        Args:
            response: Agent响应文本
            request: 原始请求
            
        Returns:
            旅行计划
        """
        import re as _re
        try:
            # 尝试从响应中提取JSON
            if "```json" in response:
                json_start = response.find("```json") + 7
                json_end = response.find("```", json_start)
                # 如果没有找到闭合的 ```，说明输出被截断，取到末尾
                if json_end == -1 or json_end <= json_start:
                    json_str = response[json_start:].strip()
                else:
                    json_str = response[json_start:json_end].strip()
            elif "```" in response:
                json_start = response.find("```") + 3
                json_end = response.find("```", json_start)
                if json_end == -1 or json_end <= json_start:
                    json_str = response[json_start:].strip()
                else:
                    json_str = response[json_start:json_end].strip()
            elif "{" in response:
                json_start = response.find("{")
                json_end = response.rfind("}")
                if json_end > json_start:
                    json_str = response[json_start:json_end + 1]
                else:
                    # 没有闭合的 }，取到末尾（截断场景）
                    json_str = response[json_start:]
            else:
                raise ValueError("响应中未找到JSON数据")
            
            # ====== 第1轮：基础清理 + 解析 ======
            json_str = self._sanitize_json_str(json_str)
            
            parse_attempts = [
                ("基础清理", json_str),
            ]

            # 预生成各轮修复候选
            fixed_quotes = self._fix_unescaped_quotes(json_str)
            parse_attempts.append(("修复未转义引号", fixed_quotes))

            # 截断修复
            repaired = self._repair_truncated_json(json_str)
            if repaired != json_str:
                parse_attempts.append(("截断修复", repaired))
                # 截断修复 + 引号修复
                repaired_fixed = self._fix_unescaped_quotes(repaired)
                if repaired_fixed != repaired:
                    parse_attempts.append(("截断+引号修复", repaired_fixed))

            # 暴力正则提取
            match = _re.search(r'\{[\s\S]*\}', json_str)
            if match:
                brutal = self._sanitize_json_str(match.group())
                brutal = self._fix_unescaped_quotes(brutal)
                parse_attempts.append(("正则提取", brutal))
                # 对正则提取的结果也做截断修复
                brutal_repaired = self._repair_truncated_json(brutal)
                if brutal_repaired != brutal:
                    parse_attempts.append(("正则+截断修复", brutal_repaired))

            # 依次尝试每种修复
            last_error = None
            for attempt_name, candidate in parse_attempts:
                try:
                    data = json.loads(candidate)
                    if attempt_name != "基础清理":
                        print(f"✅ JSON 通过「{attempt_name}」成功解析")
                    # 转换为TripPlan对象
                    return TripPlan(**data)
                except (json.JSONDecodeError, Exception) as e:
                    last_error = e
                    if attempt_name == "基础清理":
                        pos = e.pos if hasattr(e, 'pos') else 0
                        context_start = max(0, pos - 60)
                        context_end = min(len(candidate), pos + 60)
                        print(f"⚠️  首次 JSON 解析失败: {e}")
                        print(f"   出错位置附近内容: ...{candidate[context_start:context_end]}...")
                    else:
                        print(f"⚠️  「{attempt_name}」仍失败: {e}")

            # ====== 最终手段：LLM 修复 ======
            print("🔧 所有本地修复均失败，尝试使用 LLM 修复 JSON...")
            llm_fixed = self._llm_repair_json(json_str)
            llm_fixed = self._sanitize_json_str(llm_fixed)
            try:
                data = json.loads(llm_fixed)
                print("✅ JSON 通过 LLM 修复成功解析")
                return TripPlan(**data)
            except Exception as e_llm:
                print(f"⚠️  LLM 修复后仍然解析失败: {e_llm}")
                # 最终 raise 最初的错误
                raise ValueError(f"行程 JSON 解析失败: {str(last_error)}") from last_error
            
        except ValueError:
            raise
        except Exception as e:
            print(f"⚠️  解析响应失败: {str(e)}")
            raise ValueError(f"行程 JSON 解析失败: {str(e)}") from e
    
    def _create_fallback_plan(self, request: TripRequest) -> TripPlan:
        """创建备用计划(当Agent失败时)"""
        from datetime import datetime, timedelta
        
        # 解析日期
        start_date = datetime.strptime(request.start_date, "%Y-%m-%d")
        
        # 创建每日行程
        days = []
        for i in range(request.travel_days):
            current_date = start_date + timedelta(days=i)
            
            day_plan = DayPlan(
                date=current_date.strftime("%Y-%m-%d"),
                day_index=i,
                description=f"第{i+1}天行程",
                transportation=request.transportation,
                accommodation=request.accommodation,
                attractions=[
                    Attraction(
                        name=f"{request.city}景点{j+1}",
                        address=f"{request.city}市",
                        location=Location(longitude=116.4 + i*0.01 + j*0.005, latitude=39.9 + i*0.01 + j*0.005),
                        visit_duration=120,
                        description=f"这是{request.city}的著名景点",
                        category="景点"
                    )
                    for j in range(2)
                ],
                meals=[
                    Meal(type="breakfast", name=f"第{i+1}天早餐", description="当地特色早餐"),
                    Meal(type="lunch", name=f"第{i+1}天午餐", description="午餐推荐"),
                    Meal(type="dinner", name=f"第{i+1}天晚餐", description="晚餐推荐")
                ]
            )
            days.append(day_plan)
        
        return TripPlan(
            city=request.city,
            start_date=request.start_date,
            end_date=request.end_date,
            days=days,
            weather_info=[],
            overall_suggestions=f"这是为您规划的{request.city}{request.travel_days}日游行程,建议提前查看各景点的开放时间。"
        )


# 全局多智能体系统实例
_multi_agent_planner = None


def get_trip_planner_agent() -> MultiAgentTripPlanner:
    """获取多智能体旅行规划系统实例(单例模式)"""
    global _multi_agent_planner

    if _multi_agent_planner is None:
        _multi_agent_planner = MultiAgentTripPlanner()

    return _multi_agent_planner


def reset_trip_planner_agent() -> None:
    """重置旅行规划多智能体实例（用于运行时配置更新后热生效）。"""
    global _multi_agent_planner
    _multi_agent_planner = None

