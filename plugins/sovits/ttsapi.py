import requests
import time
import os
import uuid
from common.log import logger

class _ttsApi:
    def __init__(self, config):
        self.config = config  # 请注意这里需要添加 self.config 的赋值
        self.headers = {
            "Content-Type": "application/json",
        }
        self.api_url = config.get("api_url", "")
        self.api_key = config.get("api_key", "")
        self.total_timeout = config.get("total_timeout", 10)


    def subTip(self, res):
        if res.status_code == 200 or res.status_code == 201:
            rj = res.json()
            if not rj:
                return False, "❌ 无法解析服务器的回复", ""
            
            status = rj["status"]
            id = rj['task_id']
            if status == "SUBMITTED":
                msg = "✅ 您的任务已提交\n"
                msg += f"🚀 正在快速处理中，请稍后\n"
                msg += f"📨 ID: {id}\n"
                return True, msg, id

        elif res.status_code == 400:  # 错误请求
            detail = res.json().get('detail', 'No detail provided')
            return False, detail, ""
        elif res.status_code == 422:
            return False, "key授权错误", ""
        else:
            return False, "❌ 变声服务异常",""

    def convert(self, model, content):
        try:
            url = self.api_url + "/task"
            headers = {
                'Content-Type': 'application/json',
                'auth-key': f'Bearer {self.api_key}'
            }
            data = {
                "model": model,
                "content": content,
            }
            res = requests.post(url, json=data, headers=headers)
            return self.subTip(res)
        except Exception as e:
            logger.exception(e)
            return False, "❌ 任务提交失败", None
        
    # 轮询获取任务结果
    def get_tts_result(self, task_id):
        start_time = time.time()  # 记录开始时间
        total_timeout = 60 * self.total_timeout  # 总超时时间

        try:
            headers = {
                'Content-Type': 'application/json',
                'auth-key': f'Bearer {self.api_key}'
            }
            url = self.api_url + f"/task/{task_id}"
            content_type = ""

            while content_type != "audio/wav":
                # 检查是否已经超过总超时时间
                if (time.time() - start_time) > total_timeout:
                    logger.debug("❌ 超过最大等待时间")
                    return False, "❌ 请求失败：超过最大等待时间", ""
                
                time.sleep(1)
                res = requests.get(url, headers=headers, timeout=60) # 注意单次请求也设了超时时间
                content_type = res.headers.get('content-type')

                if content_type != "audio/wav":
                    rj = res.json()
                    status = rj.get("status")
                    if status is not None:
                        logger.debug(f"status: {status}")

            if content_type == "audio/wav":
                if not os.path.exists('./tmp'):
                    os.makedirs('./tmp')

                filename = f"./tmp/{str(uuid.uuid4())}.wav"
                with open(filename, 'wb') as audio_file:
                    for chunk in res.iter_content(chunk_size=8192):
                        audio_file.write(chunk)
                msg = "变声成功,本音频素材由人工智能合成,仅供学习研究,严禁用于商业及违法途径。"
                return True, msg, filename
            else:
                return False, "❌ 请求失败：服务异常", ""
        
        except Exception as e:
            logger.exception(e)
            return False, "❌ 请求失败", ""

# def main():
#     # 你的 TTS Api 配置信息
#     config = {
#         "api_url": "http://localhost:9880",
#         "api_key": ""
#     }
    
#     tts_api = _ttsApi(config)
#     model = 'liudehua'
#     content = '你想要转换的文本内容'

#     success, message, task_id = tts_api.convert(model, content)
#     print(f"Success: {success}")
#     print(f"Message: {message}")
#     if task_id:
#         success, message, filename = tts_api.get_tts_result(task_id)
#         print(f"Success: {success}")
#         print(f"Message: {message}")
#         print(f"FileName: {filename}")

# if __name__ == '__main__':
#     main()