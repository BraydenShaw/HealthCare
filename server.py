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
import base64

from mcp.server.fastmcp import FastMCP

PAPER_DIR = "papers"

# Initialize FastMCP server
#mcp = FastMCP("research", host = "localhost", port=50001)
mcp = FastMCP("research", host="0.0.0.0", port=50001)

ak = ""
sk = ""

API_KEY = "YEGmYARHwdWHuH7LPtX6amtV"
SECRET_KEY = "JFF2Yu53AHgbWEz4blpaWY4bPqdeEfh0"

def getmd5(data):
    return hashlib.md5(data.encode('utf-8')).hexdigest()

def hmacsha256(secret, message):
    data = message.encode('utf-8')
    return hmac.new(secret.encode('utf-8'), data, digestmod=hashlib.sha256).hexdigest()

def get_access_token():
    url = "https://aip.baidubce.com/oauth/2.0/token"
    params = {
        "grant_type": "client_credentials",
        "client_id": API_KEY,
        "client_secret": SECRET_KEY,
    }
    return str(requests.post(url, params=params).json().get("access_token"))

@mcp.tool()
def recognize_text(
    url: str,
    detect_direction: bool = False,
    paragraph: bool = False,
    probability: bool = False,
) -> Dict[str, Any]:
    """
    调用百度OCR API识别图片中的文字, 可用于药品包装的识别。

    :param url: str, 网络图片路径（如 "http://images/test.jpg"）。
    :param detect_direction: bool, 是否检测文字方向（默认False）。
    :param paragraph: bool, 是否返回段落信息（默认False）。
    :param probability: bool, 是否返回置信度（默认False）。
    
    :return: Dict[str, Any], 返回识别结果，包含以下字段：
             - 'text' (str): 识别出的文字内容。
             - 'error' (str): 如果出错，返回错误信息。
    """
    try:
        # 1. 获取 access_token
        url_access = "https://aip.baidubce.com/rest/2.0/ocr/v1/accurate_basic?access_token=" + get_access_token()
        

        # 2. 读取图片并转换为 Base64
        # with open(image_path, "rb") as f:
        #     image_base64 = base64.b64encode(f.read()).decode("utf-8")

        # 3. 构造请求 payload
        payload = {
            "url": url,
            "detect_direction": "true" if detect_direction else "false",
            "paragraph": "true" if paragraph else "false",
            "probability": "true" if probability else "false",
        }

        # 4. 发送请求
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }
        response = requests.post(url_access, headers=headers, data=payload)
        result = response.json()
        result_num = result.get("words_result_num", 0)

        # 5. 解析结果
        if result_num == 0:
            return {
                "text": "",
                "error": f"OCR识别失败: {result['error_msg']}",
            }

        # 提取识别文本
        text = "\n".join([item["words"] for item in result.get("words_result", [])])

        return {
            "text": text,
            "error": "",
        }

    except Exception as e:
        return {
            "text": "",
            "error": f"OCR识别异常: {str(e)}",
        }


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
def apartment_query(user_input: str, session_id: Optional[str] = None) -> Dict[str, Any]: 
    """
    调用多轮在线问诊AI模型,用于为用户推荐适合就诊的科室。
    通过多轮对话收集患者主诉，精准推荐适合就诊的科室.
    该工具模拟患者与AI医生进行对话。它会处理会话ID，并根据模型的响应判断对话是否结束。

    :param user_input: str, 患者的输入，例如“头痛挂什么科室”或对医生问题的回答。
    :param session_id: Optional[str], 对话的会话ID。如果是首轮对话，请保持为None；
                       如果是多轮对话，请传入上一轮返回的session_id。
    :return: Dict[str, Any], 一个包含以下键的字典:
             - 'scene' (int): 对话场景状态码。0表示对话继续，501表示对话结束。
             - 'model_response' (list): AI医生返回的内容。
             - 'session_id' (str): 当前对话的会话ID，用于下一轮调用。
             - 'error' (str): 如果发生错误，则包含错误信息。
    
    **重要使用说明**:
    如果返回结果中 'scene' 的值为 0，意味着对话尚未结束，Agent必须根据'model_response'的内容再次调用此工具以继续问诊。
    如果 'scene' 的值为 501，意味着问诊结束，Agent可以向用户展示最终诊断报告。
    """
    stream = False
    
    # 如果 session_id 是 None (首次对话)，API需要一个空字符串
    current_session_id = session_id or ""

    message = {
        "model": "third-common-v3-department",
        "stream": stream,
        "session_id": current_session_id, # 应用型API生效，首轮对话时为空，后续对话时可传入首轮对话返回的session_id，保留上下文信息
        "messages": [
            {
                "role": "user",
                "content": [  # 消息内容
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
def skin_disease_query(
    url: str, 
    query: str, 
    model = "third-skin-v1-diagnose",
    session_id: Optional[str] = None) -> str:
    """
    调用皮肤病诊断 API 进行图片和文本的问诊。

    Args:
        url: str, 图片的路径（如 "http://images/test.jpg"）。
        query: str, 用户提出的关于皮肤病的具体问题。
        model: str, 使用的模型名称。默认为 'third-skin-v1-diagnose'。
                可选值: 'third-skin-v1-diagnose', 'third-skin-v2-diagnose'。
        session_id: Optional[str], 对话 session_id。首轮对话可为空，后续对话传入可保留上下文。

    Returns:
        返回 API 的 JSON 字符串格式的应答。如果请求失败，则返回包含错误信息的字符串。
    """

    stream = False
    message = {
        "model": model, # third-skin-v1-diagnose, third-skin-v2-diagnose
        "stream": stream,
        "session_id": session_id or "", # 应用型API生效，首轮对话时为空，后续对话时可传入首轮对话返回的session_id，保留上下文信息
        "messages": [
            {
                "role": "user",            # 角色
                "content": [               # 消息内容
                    {
                        "type": "image",
                        "url": url,
                    },
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
                return(line.decode('utf-8'))
        else:
            response = requests.post(reqUrl, data=json.dumps(message), headers=headers)
            return(response.text)

    except requests.exceptions.RequestException as e:
        return json.dumps({"error": f"API request failed: {str(e)}"}, indent=2)
    except Exception as e:
        return json.dumps({"error": f"An unexpected error occurred: {str(e)}"}, indent=2)

@mcp.tool()
def tongue_query(
    url: str, 
    query: str, 
    model = "third-skin-v1-diagnose",
    session_id: Optional[str] = None) -> str:
    """
    调用舌头患处诊断 API 进行图片和文本的问诊。

    Args:
        url: str, 图片的路径（如 "http://images/test.jpg"）。
        query: str, 用户提出的关于舌头患处的具体问题。
        model: str, 使用的模型名称。默认为 'third-tongue-v1-diagnose'。
        session_id: Optional[str], 对话 session_id。首轮对话可为空，后续对话传入可保留上下文。

    Returns:
        返回 API 的 JSON 字符串格式的应答。如果请求失败，则返回包含错误信息的字符串。
    """


    stream = False
    message = {
        "model": "third-tongue-v1-diagnose", # third-tongue-v1-diagnose
        "stream": stream,
        "messages": [
            {
                "role": "user",            # 角色
                "content": [               # 消息内容
                    {
                        "type": "image",
                        "url": url,
                    },
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
                return(line.decode('utf-8'))
        else:
            response = requests.post(reqUrl, data=json.dumps(message), headers=headers)
            return(response.text)
    
    except requests.exceptions.RequestException as e:
        return json.dumps({"error": f"API request failed: {str(e)}"}, indent=2)
    except Exception as e:
        return json.dumps({"error": f"An unexpected error occurred: {str(e)}"}, indent=2)

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


if __name__ == "__main__":
    # Initialize and run the server
    #mcp.run(transport='streamable-http')
    mcp.run(transport='sse')
