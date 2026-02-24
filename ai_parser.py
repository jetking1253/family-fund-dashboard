import os
import re
import base64
from openai import OpenAI
from io import BytesIO
from PIL import Image

# 全局配置，可在 app.py 中动态覆盖
API_KEY = os.environ.get("OPENAI_API_KEY", "")
BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
MODEL_NAME = os.environ.get("OPENAI_MODEL_NAME", "gpt-4o")

def init_client():
    if not API_KEY:
        return None
    try:
        # 兼容第三方代理地址或自定义模型地址
        client = OpenAI(
            api_key=API_KEY,
            base_url=BASE_URL if BASE_URL else None
        )
        return client
    except Exception as e:
        print(f"OpenAI Client 初始化失败: {e}")
        return None

def extract_number_from_text(text):
    """从大模型返回的文本中提取并清洗出第一组有效的浮点数"""
    # 匹配可能包含逗号的数字串，例如 12,345.67 或 12345
    matches = re.findall(r'[\d,]+(?:\.\d+)?', text)
    if matches:
        # 去掉逗号后转换为浮点数
        clean_num_str = matches[0].replace(',', '')
        try:
             return float(clean_num_str)
        except ValueError:
             pass
    return 0.0

def _encode_image_to_base64(image_stream):
    """将 Streamlit 传入的图片流转换为 base64 字符串"""
    try:
        # 读取流
        img = Image.open(image_stream)
        # 转换为 RGB 以防止由于 Alpha 通道导致某些 API 处理报错
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        buffered = BytesIO()
        # 统一存为 JPEG
        img.save(buffered, format="JPEG")
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        return f"data:image/jpeg;base64,{img_str}"
    except Exception as e:
        print(f"图片二次编码失败: {e}")
        return None

def _call_vision_api(prompt, image_stream):
    """统一的底层 Vision 识别调用闭包"""
    client = init_client()
    if not client:
         return False, "系统未配置 API_KEY，无法使用 OCR 智能识别功能。"
         
    base64_image = _encode_image_to_base64(image_stream)
    if not base64_image:
         return False, "图片预处理失败，无法解析。"

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME if MODEL_NAME else "gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": base64_image,
                            },
                        },
                    ],
                }
            ],
            max_tokens=300,
        )
        # 解析返回的所有文本并抽取数字
        amount = extract_number_from_text(response.choices[0].message.content)
        return True, amount
    except Exception as e:
         return False, f"大模型视觉识别请求失败: {e}"

def parse_investment_amount(image_stream):
    """
    分析定投截图，提取定投金额
    """
    prompt = "这是一张金融转账或定投流水截图。请你仔细寻找截图中体现的『交易金额』或『发生金额』，直接返回这个总金额的数字，不要带任何单位和人民币符号，只需返回纯数字即可。如果没有找到，返回 0。"
    return _call_vision_api(prompt, image_stream)

def parse_asset_snapshot(image_stream):
    """
    分析券商/银行持仓截图，提取总市值
    """
    prompt = "这是一张证券账户或理财账户的持仓截图。请你寻找截图中体现的『总资产』、『总市值』或『持仓金额』，直接返回这个总金额的数字，不要带任何单位和人民币符号，只需返回纯数字即可。如果没有找到，返回 0。"
    return _call_vision_api(prompt, image_stream)
