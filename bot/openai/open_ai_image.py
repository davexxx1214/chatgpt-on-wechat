import time
import requests
import json
import base64
import io

from common.log import logger
from common.token_bucket import TokenBucket
from config import conf


# OPENAI提供的画图接口
class OpenAIImage(object):
    def __init__(self):
        self.api_key = conf().get("open_ai_image_api_key")
        self.api_base = conf().get("open_ai_image_base", "https://api.openai.com/v1")
        if conf().get("rate_limit_dalle"):
            self.tb4dalle = TokenBucket(conf().get("rate_limit_dalle", 50))

    def create_img(self, query, retry_count=0, api_key=None, api_base=None):
        try:
            if conf().get("rate_limit_dalle") and not self.tb4dalle.get_token():
                return False, "请求太快了，请休息一下再问我吧"
            
            logger.info("[OPEN_AI] image_query={}".format(query))
            
            # 使用传入的参数或默认配置
            use_api_key = api_key or self.api_key
            use_api_base = api_base or self.api_base
            
            if not use_api_key:
                return False, "未配置画图API密钥"
            
            # 准备API请求
            headers = {
                "Authorization": f"Bearer {use_api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": "gpt-image-1",
                "moderation":"low",
                "prompt": query,
                "n": 1,
                "output_format": "png",
                "background": "auto",
                "size": "auto"
            }
            
            # 确保API base URL格式正确
            api_base_url = use_api_base.rstrip('/')
            if not api_base_url.endswith('/v1'):
                if '/v1' not in api_base_url:
                    api_base_url = f"{api_base_url}/v1"
            
            api_url = f"{api_base_url}/images/generations"
            
            # 发送请求
            response = requests.post(
                api_url, 
                headers=headers, 
                json=payload, 
                timeout=300
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("data") and len(data["data"]) > 0:
                    # 检查是否有base64格式的图片
                    if data["data"][0].get("b64_json"):
                        image_b64 = data["data"][0]["b64_json"]
                        # 将base64转换为字节流，然后可以进一步处理
                        image_bytes = base64.b64decode(image_b64)
                        
                        # 这里我们需要返回一个可以被现有代码处理的格式
                        # 可以创建一个临时的数据URL或者返回base64字符串
                        data_url = f"data:image/png;base64,{image_b64}"
                        logger.info("[OPEN_AI] image generated successfully with gpt-image-1")
                        return True, data_url
                    elif data["data"][0].get("url"):
                        # 兼容URL格式返回
                        image_url = data["data"][0]["url"]
                        logger.info("[OPEN_AI] image_url={}".format(image_url))
                        return True, image_url
                    else:
                        return False, "API响应格式不正确"
                else:
                    return False, "API响应中没有图片数据"
            else:
                error_msg = f"API请求失败，状态码: {response.status_code}"
                try:
                    error_data = response.json()
                    if "error" in error_data:
                        error_msg += f", 错误: {error_data['error'].get('message', '未知错误')}"
                except:
                    pass
                logger.error(f"[OPEN_AI] {error_msg}")
                return False, error_msg
                
        except requests.exceptions.Timeout:
            logger.warn("[OPEN_AI] 请求超时")
            if retry_count < 1:
                time.sleep(5)
                logger.warn("[OPEN_AI] ImgCreate Timeout, 第{}次重试".format(retry_count + 1))
                return self.create_img(query, retry_count + 1, api_key, api_base)
            else:
                return False, "画图请求超时，请稍后再试"
        except requests.exceptions.RequestException as e:
            logger.warn(f"[OPEN_AI] 网络请求错误: {e}")
            if retry_count < 1:
                time.sleep(5)
                logger.warn("[OPEN_AI] ImgCreate RequestException, 第{}次重试".format(retry_count + 1))
                return self.create_img(query, retry_count + 1, api_key, api_base)
            else:
                return False, "画图出现网络问题，请稍后再试"
        except Exception as e:
            logger.exception(e)
            return False, "画图出现问题，可能是某些关键词或句子未通过安全审查"
