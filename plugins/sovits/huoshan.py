import json
import requests
from pathlib import Path
import base64
from .token_service import get_token
import uuid
from common.tmp_dir import TmpDir  # 新增导入
import hashlib  # 新增导入

def synthesize_speech(speaker: str, text: str, output_path: str = None):
    # 获取token
    token = get_token()

    domain = "https://sami.bytedance.com"
    version = "v4"
    namespace = "TTS"

    # 读取配置文件以获取appkey
    config_path = Path(__file__).parent / 'config.json'
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    appkey = config.get('huoshan_app_key')

    if not appkey:
        raise ValueError("配置文件中缺少 huoshan_app_key。")

    url = f"{domain}/api/v1/invoke?version={version}&token={token}&appkey={appkey}&namespace={namespace}"

    payload = {
        "speaker": speaker,
        "text": text,
        "audio_config": {
            "format": "wav"
        }
    }

    body = {
        "payload": json.dumps(payload)
    }

    headers = {
        'Content-Type': 'application/json'
    }

    try:
        response = requests.post(url, headers=headers, json=body)
        response.raise_for_status()
        sami_resp = response.json()

        task_id = sami_resp.get('task_id')
        payload_str = sami_resp.get('payload', '')
        data = sami_resp.get('data', '')

        print(f"response task_id={task_id}, payload={payload_str}, data={len(data)} bytes")

        # 保存输出
        with open('output.json', 'w', encoding='utf-8') as f:
            f.write(payload_str)

        # 检查 data 是否为空
        if not data:
            raise Exception("API 返回的数据为空。")

        # 确认 data 是字符串并进行解码
        if isinstance(data, str):
            try:
                data = base64.b64decode(data)
            except Exception as decode_err:
                raise Exception(f"数据解码失败: {decode_err}")

        # 如果未提供 output_path，生成唯一文件名并保存到 tmp 目录
        if not output_path:
            timestamp = int(time.time())
            text_hash = hashlib.md5(text.encode('utf-8')).hexdigest()[:8]
            output_filename = f"reply-{timestamp}-{text_hash}.wav"
            output_dir = TmpDir().path()
            output_path = Path(output_dir) / output_filename

        with open(output_path, 'wb') as f:
            f.write(data)

    except Exception as e:
        raise Exception(f"调用语音合成服务失败: {e}")

if __name__ == "__main__":
    import time
    speaker = "zh_male_sunwukong_clone2"  # 修改后的 speaker
    text = "欢迎使用文本转语音服务啊。"
    synthesize_speech(speaker, text)