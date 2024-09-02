import time

import openai
import openai.error

from common.log import logger
from common.token_bucket import TokenBucket
from config import conf


# OPENAI提供的画图接口
class OpenAIImage(object):
    def __init__(self):
        openai.api_key = conf().get("open_ai_image_api_key")
        if conf().get("rate_limit_dalle"):
            self.tb4dalle = TokenBucket(conf().get("rate_limit_dalle", 50))

    def create_img(self, query, retry_count=0, api_key=None, api_base=None):
        try:
            if conf().get("rate_limit_dalle") and not self.tb4dalle.get_token():
                return False, "请求太快了，请休息一下再问我吧"
            logger.info("[OPEN_AI] image_query={}".format(query))
            if conf().get("open_ai_image_base"):
                openai.api_base = conf().get("open_ai_image_base")

            if conf().get("open_ai_image_api_key"):
                openai.api_key =conf().get("open_ai_image_api_key")
                
            # Determine the size based on the query
            if "16:9" in query:
                size = "1792x1024"
            elif "9:16" in query:
                size = "1024x1792"
            else:
                size = "1024x1024"
            
            response = openai.Image.create(
                api_key=api_key,
                prompt=query,  # 图片描述
                n=1,  # 每次生成图片的数量
                model=conf().get("text_to_image") or "dall-e-3",
                size=size,  # 图片大小
            )
            image_url = response["data"][0]["url"]
            logger.info("[OPEN_AI] image_url={}".format(image_url))
            return True, image_url
        except openai.error.RateLimitError as e:
            logger.warn(e)
            if retry_count < 1:
                time.sleep(5)
                logger.warn("[OPEN_AI] ImgCreate RateLimit exceed, 第{}次重试".format(retry_count + 1))
                return self.create_img(query, retry_count + 1)
            else:
                return False, "画图出现问题，可能是画图配额不足(当前画图配额为每分钟5张)"
        except Exception as e:
            logger.exception(e)
            return False, "画图出现问题，可能是某些关键词或句子未通过安全审查"
