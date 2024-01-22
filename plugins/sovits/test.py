import requests
import logging
import uuid
import os

data = {
        "refer_wav_path": "",
        "prompt_text": "",
        "prompt_language":"zh",
        "text":"",
        "text_language":"zh"
}
        
if not os.path.exists('./tmp'):
    os.makedirs('./tmp')

filename = f"./tmp/{str(uuid.uuid4())}.wav"

try:
    api_url = ""
    # response = requests.post(api_url, json=data)
    response = requests.post(api_url, json=data, stream=True)
    response.raise_for_status()
    # 处理响应数据
    with open(filename, 'wb') as f:
        f.write(response.content)

except requests.exceptions.RequestException as e:
    # 处理可能出现的错误
    logging.error("发生错误: %s", e)