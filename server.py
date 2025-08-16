import arxiv
import json
import os
from typing import List
import hashlib
import hmac
import json
import time
import requests
from typing import Optional, Dict, Any

from mcp.server.fastmcp import FastMCP

PAPER_DIR = "papers"

# Initialize FastMCP server
#mcp = FastMCP("research", host = "localhost", port=50001)
mcp = FastMCP("research", host="0.0.0.0", port=50001)

ak = "11279aea94d9ca063450f5109b3d6490340cf0b6f5a605552088b1081be420a2e6d0160372e57652cd7e1053e5c44efe"
sk = "e42c1f8503a8a4f4c99271e64884142c7784662c"

def getmd5(data):
    return hashlib.md5(data.encode('utf-8')).hexdigest()

def hmacsha256(secret, message):
    data = message.encode('utf-8')
    return hmac.new(secret.encode('utf-8'), data, digestmod=hashlib.sha256).hexdigest()

@mcp.tool()
def ask_doctor(user_input: str, session_id: Optional[str] = None) -> Dict[str, Any]:
    """
    调用多轮在线问诊AI模型。
    该工具模拟患者与AI医生进行对话。它会处理会话ID，并根据模型的响应判断对话是否结束。

    :param user_input: str, 患者的输入，例如“我头晕”或对医生问题的回答。
    :param session_id: Optional[str], 对话的会话ID。如果是首轮对话，请保持为None；
                       如果是多轮对话，请传入上一轮返回的session_id。
    :return: Dict[str, Any], 一个包含以下键的字典:
             - 'scene' (int): 对话场景状态码。0表示对话继续，202表示对话结束。
             - 'model_response' (list): AI医生返回的内容。
             - 'session_id' (str): 当前对话的会话ID，用于下一轮调用。
             - 'error' (str): 如果发生错误，则包含错误信息。
    
    **重要使用说明**:
    如果返回结果中 'scene' 的值为 0，意味着对话尚未结束，Agent必须根据'model_response'的内容再次调用此工具以继续问诊。
    如果 'scene' 的值为 202，意味着问诊结束，Agent可以向用户展示最终诊断报告。
    """
    stream = False
    
    # 如果 session_id 是 None (首次对话)，API需要一个空字符串
    current_session_id = session_id or ""

    message = {
        "model": "third-common-v3-consultationAssistant",
        "stream": False,  # Tool中通常使用非流式以获得完整响应
        "session_id": current_session_id,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "body": user_input
                    }
                ]
            }
        ]
    }

    md5 = getmd5(json.dumps(message))
    timestr = time.strftime("%d %b %Y %H:%M:%S GMT", time.localtime())
    authStringPrefix = "ihcloud/" + ak + "/" + timestr + "/300"
    signingKey = hmacsha256(sk, authStringPrefix)
    host = 'https://01bot.baidu.com'
    router = '/api/01bot/sse-gateway/stream'
    reqUrl = host + router
    canonicalRequest = '\n'.join(["POST", router, "content-md5:" + md5])
    signature = hmacsha256(signingKey, canonicalRequest)
    headers = {
        "Content-Type": "application/json",
        "X-IHU-Authorization-V2": authStringPrefix + "/" + signature
    }
    
    if stream:
        response = requests.post(reqUrl, data=json.dumps(message), headers=headers, stream=True)
        
        for line in response.iter_lines():
            return line.decode('utf-8')
    else:
        response = requests.post(reqUrl, data=json.dumps(message), headers=headers)
        data = json.loads(response.text)

        return {
            "scene": data['result'][0]['messages'][0]['scene'],
            "model_response": data['result'][0]['messages'][0]['content'],
            "session_id": data['result'][0]['session_id']
        }

@mcp.tool()
def consult_drug(
    query: str,
    model: str = "third-common-v1-DrugQA",
    session_id: Optional[str] = None
) -> str:
    """
    针对具体的药物相关问题，调用基于药品说明书的问答 API 进行咨询。
    适用于查询药品的适应症、禁忌症、注意事项、用法用量、特殊人群使用、多药联用等科普性质的问题。

    Args:
        query: 用户提出的关于药物的具体问题。例如："感康里面含有对乙酰氨基酚吗？"
        model: 使用的模型名称。默认为 'third-common-v1-DrugQA'。
               可选值: 'third-common-v1-DrugQA', 'third-common-v2-DrugQA'。
        session_id: 对话 session_id。首轮对话可为空，后续对话传入可保留上下文。

    Returns:
        返回 API 的 JSON 字符串格式的应答。如果请求失败，则返回包含错误信息的字符串。
    """
    host = 'https://01bot.baidu.com'
    router = '/api/01bot/sse-gateway/stream'
    reqUrl = host + router

    message: Dict[str, Any] = {
        "model": model,
        "stream": False,  # MCP 工具通常适用于一次性返回结果，因此设置为 False
        "session_id": session_id or "",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "body": query,
                    }
                ]
            }
        ]
    }

    try:
        md5 = getmd5(json.dumps(message))
        timestr = time.strftime("%d %b %Y %H:%M:%S GMT", time.localtime())
        stream = False
        authStringPrefix = "ihcloud/" + ak + "/" + timestr + "/300"
        signingKey = hmacsha256(sk, authStringPrefix)
        host = 'https://01bot.baidu.com'
        router = '/api/01bot/sse-gateway/stream'
        reqUrl = host + router
        canonicalRequest = '\n'.join(["POST", router, "content-md5:" + md5])
        signature = hmacsha256(signingKey, canonicalRequest)
        headers = {
            "Content-Type": "application/json",
            "X-IHU-Authorization-V2": authStringPrefix + "/" + signature
        }
        if stream:
            response = requests.post(reqUrl, data=json.dumps(message), headers=headers, stream=True)
            for line in response.iter_lines():
                return line.decode('utf-8')
        else:
            response = requests.post(reqUrl, data=json.dumps(message), headers=headers)
            return response.text

    except requests.exceptions.RequestException as e:
        return json.dumps({"error": f"API request failed: {str(e)}"}, indent=2)
    except Exception as e:
        return json.dumps({"error": f"An unexpected error occurred: {str(e)}"}, indent=2)


@mcp.tool()
def search_papers(topic: str, max_results: int = 5) -> List[str]:
    """
    Search for papers on arXiv based on a topic and store their information.

    Args:
        topic: The topic to search for
        max_results: Maximum number of results to retrieve (default: 5)

    Returns:
        List of paper IDs found in the search
    """

    # Use arxiv to find the papers
    client = arxiv.Client()

    # Search for the most relevant articles matching the queried topic
    search = arxiv.Search(
        query=topic,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.Relevance
    )

    papers = client.results(search)

    # Create directory for this topic
    path = os.path.join(PAPER_DIR, topic.lower().replace(" ", "_"))
    os.makedirs(path, exist_ok=True)

    file_path = os.path.join(path, "papers_info.json")

    # Try to load existing papers info
    try:
        with open(file_path, "r") as json_file:
            papers_info = json.load(json_file)
    except (FileNotFoundError, json.JSONDecodeError):
        papers_info = {}

    # Process each paper and add to papers_info  
    paper_ids = []
    for paper in papers:
        paper_ids.append(paper.get_short_id())
        paper_info = {
            'title': paper.title,
            'authors': [author.name for author in paper.authors],
            'summary': paper.summary,
            'pdf_url': paper.pdf_url,
            'published': str(paper.published.date())
        }
        papers_info[paper.get_short_id()] = paper_info

    # Save updated papers_info to json file
    with open(file_path, "w") as json_file:
        json.dump(papers_info, json_file, indent=2)

    print(f"Results are saved in: {file_path}")

    return paper_ids

@mcp.tool()
def extract_info(paper_id: str) -> str:
    """
    Search for information about a specific paper across all topic directories.

    Args:
        paper_id: The ID of the paper to look for

    Returns:
        JSON string with paper information if found, error message if not found
    """

    for item in os.listdir(PAPER_DIR):
        item_path = os.path.join(PAPER_DIR, item)
        if os.path.isdir(item_path):
            file_path = os.path.join(item_path, "papers_info.json")
            if os.path.isfile(file_path):
                try:
                    with open(file_path, "r") as json_file:
                        papers_info = json.load(json_file)
                        if paper_id in papers_info:
                            return json.dumps(papers_info[paper_id], indent=2)
                except (FileNotFoundError, json.JSONDecodeError) as e:
                    print(f"Error reading {file_path}: {str(e)}")
                    continue

    return f"There's no saved information related to paper {paper_id}."

if __name__ == "__main__":
    # Initialize and run the server
    #mcp.run(transport='streamable-http')
    mcp.run(transport='sse')
