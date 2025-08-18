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
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_response import LlmResponse

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
        url="http://dxgq1371138.bohrium.tech:50001/sse",  # 替换为你的 SSE server 地址
    ),
)

toolset2 = MCPToolset(
    connection_params=SseServerParams(
        url="https://mcp.amap.com/sse?key=2089a5b76f6b77a5a896a61203f040f9",  # 替换为你的 SSE server 地址
    ),
)

# =============================
# 模型选择
# =============================
use_model = "gpt-4o"
if use_model == "deepseek":
    base_model = LiteLlm(model="deepseek/deepseek-chat")
elif use_model == "gpt-4o":
    base_model = LiteLlm(model="gpt-4o", temperature=0.1)
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
        "当ask_doctor返回最终诊断报告时，你必须输出‘本轮问诊结束’为开头的内容，并判断病情严重程度是否需要去医院就诊，如需去医院就诊，必须输出‘前往医院就诊’"
        "必须完整的给出诊断报告"
    ),
    tools=[toolset, toolset2],
    output_key="inquiry_result",  # 存 JSON 对象
    description="问诊 agent: 持续和用户进行问诊，最终输出 JSON 格式的问诊结果。",
)

from google.genai import types
async def save_generated_report_html(callback_context: CallbackContext, llm_response: LlmResponse):
    """Saves generated PDF report bytes as an artifact."""
    report_artifact = types.Part.from_bytes(
        data=llm_response.content.parts[0].text.replace("```html", "").replace("```", "").encode('utf-8'),
        mime_type="text/html"
    )
    filename = "generated_report.html"

    try:
        version = await callback_context.save_artifact(filename=filename, artifact=report_artifact)
        print(f"Successfully saved Python artifact '{filename}' as version {version}.")        
        # The event generated after this callback will contain:
        # event.actions.artifact_delta == {"generated_report.pdf": version}
    except ValueError as e:
        print(f"Error saving Python artifact: {e}. Is ArtifactService configured in Runner?")
    except Exception as e:
        # Handle potential storage errors (e.g., GCS permissions)
        print(f"An unexpected error occurred during Python artifact save: {e}")



UNIFIED_CSS = r"""
:root{
  --ink:#0f172a; --muted:#475569; --border:#e2e8f0; --card:#ffffff; --bg:#f8fafc; --accent:#0ea5e9;
}
*{box-sizing:border-box}
html,body{margin:0;padding:0;background:var(--bg);color:var(--ink);
  font:14px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Noto Sans CJK SC","Noto Sans CJK",
        Helvetica,Arial,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;}
.container{max-width:900px;margin:32px auto;padding:0 16px}
.card{background:var(--card);border:1px solid var(--border);border-radius:16px;box-shadow:0 6px 24px rgba(15,23,42,.06);overflow:hidden}
header{padding:24px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;gap:16px}
.hospital{font-size:18px;font-weight:700;letter-spacing:.5px}
.subtitle{font-size:12px;color:var(--muted)}
.title{font-size:22px;font-weight:800;letter-spacing:1px;margin:4px 0 0}
.badge{border:1px solid var(--accent);color:var(--accent);padding:2px 8px;border-radius:999px;font-size:12px;white-space:nowrap}
.toolbar{display:flex;gap:8px;align-items:center}
button{border:1px solid var(--border);background:#fff;cursor:pointer;padding:8px 12px;border-radius:10px;font-weight:600}
button:hover{border-color:var(--accent)}
main{padding:16px 24px 24px}
section{border:1px solid var(--border);border-radius:12px;padding:16px;margin:14px 0;background:#fff}
section h3{margin:0 0 10px;font-size:16px;letter-spacing:.5px;display:flex;align-items:center;gap:8px}
section h3::before{content:"";width:6px;height:6px;border-radius:999px;background:var(--accent);display:inline-block}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.grid-3{grid-template-columns:repeat(3,1fr)}
.grid-2{grid-template-columns:repeat(2,1fr)}
.field{border:1px dashed var(--border);border-radius:10px;padding:8px 10px;min-height:38px;background:#fff}
.label{font-size:12px;color:var(--muted);margin-bottom:4px}
.value{font-size:14px}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,"Liberation Mono","Courier New",monospace}
table{width:100%;border-collapse:collapse;border:1px solid var(--border);border-radius:10px;overflow:hidden}
th,td{border-bottom:1px solid var(--border);padding:8px 10px;text-align:left;vertical-align:top}
thead th{background:#f1f5f9;font-weight:700;font-size:13px}
.muted{color:var(--muted)}
footer{padding:20px 24px;border-top:1px solid var(--border);background:#fff;display:grid;gap:10px}
.hint{font-size:12px;color:var(--muted)}
.signature{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
.signature .line{padding:10px;border:1px dashed var(--border);border-radius:10px;min-height:50px}
@media print{
  :root{--bg:#fff}
  .container{max-width:100%;margin:0;padding:0}
  .toolbar{display:none!important}
  .card{border:none;box-shadow:none;border-radius:0}
  body{font-size:12px}
  section{page-break-inside:avoid}
  @page{size:A4;margin:14mm}
}
"""

# 生成病情报告 agent
report_agent = LlmAgent(
    name="report_agent",
    description=(
        "请依据给定的诊断报告，生成**完整且可打印的 HTML5 病情报告**。"
        "必须只输出一个自包含的 HTML 文档（含 <html><head><body>），不得输出 Markdown、解释或额外文本。"
        "统一样式：将下列 CSS 原样内联至 <head><style>...</style>（禁止更名/修改选择器）：\n"
        f"{UNIFIED_CSS}\n"
    ),
    model=base_model,
    output_key="report",
    after_model_callback=save_generated_report_html
)


# 推荐药物 agent
medicine_agent = LlmAgent(
    name="medicine_agent",
    description="必须使用工具，根据病情报告推荐药物",
    model=base_model,
    output_key="medicine",
    tools=[toolset],
)

# 推荐医院 agent
hospital_agent = LlmAgent(
    name="hospital_agent",
    description="推荐附近的医院。",
    instruction="获取用户位置，然后推荐医院需要调用地图工具推荐。当要给出确切医院地点时，回答必须以‘我将为您提供以下医院’开头。",
    model=base_model,
    output_key="hospital",
    tools=[toolset2],
)

# =============================
# Orchestrator 逻辑
# =============================
hospital_flag = 0

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
        
        global hospital_flag

        inquiry_result = ctx.session.state.get("inquiry_result", {})

        if hospital_flag == 0:
            # Step 1: 问诊
            async for event in self.inquiry_agent.run_async(ctx):
                yield event

            inquiry_result = ctx.session.state.get("inquiry_result", {})
            if "本轮问诊结束" not in inquiry_result:
                return

            logger.info(f"[{self.name}] 生成病情报告")
            # Step 2: 生成病情报告
            async for event in self.report_agent.run_async(ctx):
                yield event

            report_text = ctx.session.state.get("report", "")

            logger.info(f"[{self.name}] 推荐药物")
            # Step 3: 推荐药物
            async for event in self.medicine_agent.run_async(ctx):
                yield event

        if "前往医院就诊" in inquiry_result or hospital_flag:
            logger.info(f"[{self.name}] 推荐医院")
            # Step 3: 推荐医院
            async for event in self.hospital_agent.run_async(ctx):
                yield event

            hospital_flag = 1
            hospital_result = ctx.session.state.get("hospital", {})

            if "我将为您提供以下医院" in hospital_result:
                hospital_flag = 0

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
