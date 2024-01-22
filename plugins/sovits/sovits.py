import requests
import json
import re
import plugins
from bridge.reply import Reply, ReplyType
from bridge.context import ContextType
from channel.chat_message import ChatMessage
from plugins import *
from common.log import logger
import os
import uuid

@plugins.register(
    name="sovits",
    desire_priority=2,
    desc="A plugin to convert voice with gpt-sovits",
    version="0.0.1",
    author="davexxx",
)

class sovits(Plugin):
    def __init__(self):
        super().__init__()
        try:
            curdir = os.path.dirname(__file__)
            config_path = os.path.join(curdir, "config.json")
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    self.config = json.load(f)
            else:
                # 使用父类的方法来加载配置
                self.config = super().load_config()

                if not self.config:
                    raise Exception("config.json not found")
            # 设置事件处理函数
            self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
            # 从配置中提取所需的设置
            self.api_url = self.config.get("api_url","")
            
            # 初始化成功日志
            logger.info("[sovits] inited.")
        except Exception as e:
            # 初始化失败日志
            logger.warn(f"sovits init failed: {e}")
    def on_handle_context(self, e_context: EventContext):
        context = e_context["context"]
        if context.type not in [ContextType.TEXT, ContextType.SHARING,ContextType.FILE,ContextType.IMAGE]:
            return
        msg: ChatMessage = e_context["context"]["msg"]
        user_id = msg.from_user_id
        content = context.content
        isgroup = e_context["context"].get("isgroup", False)

        # if content.startswith(self.tts_prefix):
        #     # Call new function to handle search operation
        #     self.call_service(content, e_context)
        #     return
        if self.params_cache[user_id]['tts_quota'] > 0:
            self.params_cache[user_id]['tts_quota'] = 0
            self.call_service(content, e_context)
            return
        
        # 将用户信息存储在params_cache中
        if user_id not in self.params_cache:
            self.params_cache[user_id] = {}
            self.params_cache[user_id]['tts_quota'] = 0
            logger.info('Added new user to params_cache.')

        if e_context['context'].type == ContextType.TEXT:
            if content.startswith(self.tts_prefix):
                # Call new function to handle search operation
                pattern = self.tts_prefix + r"\s(.+)"
                match = re.match(pattern, content)
                tip = f"\n未检测到模型名称，将使用系统默认模型。\n\n💬自定义提示词的格式为：{self.tts_prefix}+空格+模型名称"
                if match:
                    self.params_cache[user_id]['tts_model'] = content[len(self.tts_prefix):]
                    tip = f"\n\n💬使用的提示词为:{self.params_cache[user_id]['tts_model'] }"
                else:
                    self.params_cache[user_id]['tts_model'] = self.tts_model

                self.params_cache[user_id]['tts_quota'] = 1
                reply = Reply(type=ReplyType.TEXT, content="💡已开启变声模式。请输入想要转换的文字，为保证转换效果，请不要超过30个字。"+ tip)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS

    def call_service(self, content, e_context):
        self.handle_sovits(content, e_context)

    def handle_sovits(self, content, e_context):
        data = {
            "refer_wav_path": "E:\\Dave\\GPT-SoVITS-beta\\GPT-SoVITS\\output\\slicer_opt\\leijun.wav_132160_296960.wav",
            "prompt_text": "你们都是做数据分析的高手，欢迎来我们小米",
            "prompt_language":"zh",
            "text":content,
            "text_language":"zh"
        }
        
        if not os.path.exists('./tmp'):
            os.makedirs('./tmp')

        filename = f"./tmp/{str(uuid.uuid4())}.wav"
        try:
            api_url = self.api_url
            # response = requests.post(api_url, json=data)
            response = requests.post(api_url, json=data, stream=True)
            response.raise_for_status()
            # 处理响应数据
            with open(filename, 'wb') as f:
                f.write(response.content)

        except Exception as e:
            reply.type = ReplyType.ERROR
            reply.content = "服务暂不可用"+str(e)
            logger.error("[sovits] exception: %s" % e)
            e_context.action = EventAction.CONTINUE  # 事件继续，交付给下个插件或默认逻辑

        reply = Reply(ReplyType.VOICE, filename)
        reply.content = f"转换结束"
        e_context["reply"] = reply
        e_context.action = EventAction.BREAK_PASS
