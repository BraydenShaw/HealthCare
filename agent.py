import os
import logging
from typing import AsyncGenerator, Dict, Any
from typing_extensions import override
from dotenv import load_dotenv

from google.adk.agents import Agent, LlmAgent, BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
from google.adk.tools.mcp_tool.mcp_session_manager import SseServerParams
from google.adk.sessions import InMemorySessionService
from google.adk.events import Event

# =============================
# 日志
# =============================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============================
# 环境变量配置
# =============================
# Load environment variables from .env file
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

# Use model from environment or default to deepseek
model_type = os.getenv('MODEL', 'deepseek/deepseek-chat')

# =============================
# MCP 工具配置
# =============================
toolset = MCPToolset(
    connection_params=SseServerParams(
        url="http://localhost:50001/sse",  # 替换为你的 SSE server 地址
    ),
)

# =============================
# 模型选择
# =============================
use_model = "deepseek"
if use_model == "deepseek":
    base_model = LiteLlm(model="deepseek/deepseek-chat")
elif use_model == "gpt-4o":
    base_model = LiteLlm(model="azure/gpt-4o")
else:
    raise ValueError("Unknown model option")

# =============================
# 定义四个子 agent
# =============================

# 问诊 agent —— 输出 JSON，包含 finished + summary
inquiry_agent = Agent(
    name="inquiry_agent",
    model=base_model,
    instruction=(
        "你是一个问诊 agent，需要与用户进行多轮问诊。"
        "在用户明确表示结束问诊前，不要输出总结。"
        "当用户说结束问诊时，你必须输出‘您已结束问诊’并附带一个详细的症状总结"
    ),
    tools=[toolset],
    output_key="inquiry_result",  # 存 JSON 对象
    description="问诊 agent: 持续和用户进行问诊，最终输出 JSON 格式的问诊结果。",
)

# 生成病情报告 agent
report_agent = LlmAgent(
    name="report_agent",
    description="根据症状总结，生成病情报告，包括病情描述、症状、可能的疾病等，输出 HTML 格式。",
    model=base_model,
    output_key="report",
)

# 推荐药物 agent
medicine_agent = LlmAgent(
    name="medicine_agent",
    description="根据病情报告推荐药物（适用于轻症）。",
    model=base_model,
    output_key="medicine",
)

# 推荐医院 agent
hospital_agent = LlmAgent(
    name="hospital_agent",
    description="根据病情报告推荐医院（适用于重症）。",
    model=base_model,
    output_key="hospital",
)

# =============================
# Orchestrator 逻辑
# =============================

class OrchestratorAgent(BaseAgent):
    """
    自定义 Orchestrator：问诊 → 生成报告 → 推荐药物/医院
    """

    inquiry_agent: Agent
    report_agent: LlmAgent
    medicine_agent: LlmAgent
    hospital_agent: LlmAgent

    model_config = {"arbitrary_types_allowed": True}

    def __init__(self, name: str, inquiry_agent, report_agent, medicine_agent, hospital_agent):
        super().__init__(
            name=name,
            inquiry_agent=inquiry_agent,
            report_agent=report_agent,
            medicine_agent=medicine_agent,
            hospital_agent=hospital_agent,
            sub_agents=[inquiry_agent, report_agent, medicine_agent, hospital_agent],
        )

    @override
    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        logger.info(f"[{self.name}] 开始 Orchestrator 流程")

        # Step 1: 问诊
        async for event in self.inquiry_agent.run_async(ctx):
            yield event

        inquiry_result = ctx.session.state.get("inquiry_result", {})
        if "结束" not in inquiry_result:
            return

        logger.info(f"[{self.name}] 生成病情报告")
        # Step 2: 生成病情报告
        async for event in self.report_agent.run_async(ctx):
            yield event

        report_text = ctx.session.state.get("report", "")

        # Step 3: 分流（轻症 → 药物；重症 → 医院）
        if "轻度" in report_text or "轻症" in report_text:
            async for event in self.medicine_agent.run_async(ctx):
                yield event
        else:
            async for event in self.hospital_agent.run_async(ctx):
                yield event

        logger.info(f"[{self.name}] Orchestrator 流程结束")

# =============================
# 暴露 root_agent 给 adk-web
# =============================

session_service = InMemorySessionService()
root_agent = OrchestratorAgent(
    name="root_agent",
    inquiry_agent=inquiry_agent,
    report_agent=report_agent,
    medicine_agent=medicine_agent,
    hospital_agent=hospital_agent,
)
