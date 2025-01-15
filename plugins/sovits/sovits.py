import json
import re
import plugins
from bridge.reply import Reply, ReplyType
from bridge.context import ContextType
from channel.chat_message import ChatMessage
from plugins import *
from common.log import logger
from common.expired_dict import ExpiredDict
import os
from .ttsapi import _ttsApi
import random
from voice.azure.azure_voice import AzureVoice
from .huoshan import synthesize_speech  # 新增导入
from common.tmp_dir import TmpDir  # 确保导入 TmpDir
import time  # 新增导入
import hashlib  # 新增导入
from pathlib import Path  # 新增导入

@plugins.register(
    name="sovits",
    desire_priority=2,
    desc="A plugin to convert voice with gpt-sovits and azure tts",
    version="0.0.2",
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
            
            self.tts = _ttsApi(self.config)
            # 设置事件处理函数
            self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
            # 从配置中提取所需的设置
            self.api_url = self.config.get("api_url","")
            self.tts_prefix = self.config.get("tts_prefix","变声")
            self.azure_tts_prefix = self.config.get("azure_tts_prefix","语音合成")
            self.tts_model = self.config.get("tts_model","default")
            self.model_list = self.config.get("model_list", "[]")
            self.model_mappings = self.config.get("model_mappings", "[]")
            self.params_cache = ExpiredDict(500)
            # 初始化成功日志
            logger.info("[sovits] inited.")
        except Exception as e:
            # 初始化失败日志
            logger.warn(f"sovits init failed: {e}")

            
    def on_handle_context(self, e_context: EventContext):
        context = e_context["context"]
        if context.type not in [ContextType.TEXT, ContextType.SHARING, ContextType.FILE, ContextType.IMAGE]:
            return
        content = context.content

        if e_context['context'].type == ContextType.TEXT:
            if content.startswith(self.azure_tts_prefix):
                pattern = self.azure_tts_prefix + r"\s*((?:女[12])|(?:男[12]))?\s*([\d.]+x)?\s*(.+)?"
                match = re.match(pattern, content)
                voice_mappings = {
                    "女1": "zh-CN-XiaochenMultilingualNeural",
                    "女2": "zh-CN-XiaoyuMultilingualNeural",
                    "男1": "zh-CN-YunfanMultilingualNeural",
                    "男2": "zh-CN-YunyiMultilingualNeural"
                }
                tip = f"💡欢迎使用语音合成服务(可商用)，语音合成指令格式为:\n\n{self.azure_tts_prefix} [音色] [速度] 文字\n\n可选音色：女1、女2、男1、男2\n速度范围：0.5x-2.0x，例如1.5x\n例如：语音合成 男2 1.5x 你好\n不指定音色和速度则使用默认设置"
                
                if match:
                    voice_type = match.group(1)
                    speed = match.group(2)
                    text = match.group(3)
                    
                    if text:
                        azure_voice_service = AzureVoice()
                        if voice_type:
                            azure_voice_service.speech_config.speech_synthesis_voice_name = voice_mappings[voice_type]
                        
                        # 处理速度并构建SSML
                        speed_value = float(speed.rstrip('x')) if speed else 1.0
                        if 0.5 <= speed_value <= 2.0:
                            ssml_text = f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="zh-CN"><prosody rate="{int((speed_value-1)*100):+d}%">{text.strip()}</prosody></speak>'
                            reply = azure_voice_service.textToVoice(ssml_text)
                        else:
                            reply = Reply(type=ReplyType.TEXT, content="速度范围应在0.5x-2.0x之间")
                    else:
                        reply = Reply(type=ReplyType.TEXT, content=tip)

                    e_context["reply"] = reply
                    e_context.action = EventAction.BREAK_PASS

    def call_service(self, content, user_id, e_context):
        self.handle_sovits(content, user_id, e_context)

    def handle_sovits(self, content, user_id, e_context):
        logger.info(f"handle_sovits, content =  {content}")
        tts_model = self.params_cache[user_id]['tts_model']
        logger.info('using tts_model=' + tts_model)
        
        status, msg, id = self.tts.convert(tts_model, content)
        return self._reply(status, msg, id, tts_model, content,e_context)
    
    def _reply(self, status, msg, id, tts_model, content, e_context: EventContext):
        if status:
            logger.info('querying task id =' + id)
            rc, rt = self.get_result(id, tts_model, content)
            reply = Reply(rt, rc)
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS
        else:
            rc= "服务暂不可用"
            rt = ReplyType.TEXT
            reply = Reply(rt, rc)
            logger.error("[sovits] service exception")
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS
        
    def get_result(self, id, tts_model, content):
        status, msg, filepath = self.tts.get_tts_result(id)
        rt = ReplyType.TEXT
        rc = msg
        if not status:
            rt = ReplyType.ERROR
            rc = msg

        if status and filepath:
            logger.info('getting result, status = ' + str(status) + ', file path =' + filepath)
            newfilepath = self.rename_file(filepath, tts_model, content)
            rt = ReplyType.VOICE
            rc = newfilepath

        if not rc:
            rt = ReplyType.ERROR
            rc = "语音转换失败"
        return rc, rt
    
    def rename_file(self, filepath, model, content):
        # 提取目录路径和扩展名
        dir_path, filename = os.path.split(filepath)
        file_ext = os.path.splitext(filename)[1]

        # 移除content中的标点符号和空格
        cleaned_content = re.sub(r'[^\w]', '', content)
        # 截取content的前10个字符
        content_prefix = cleaned_content[:10]
        
        random_number = f"{random.randint(0, 999):03}"
        
        # 组装新的文件名，包括模型、内容和4位随机数
        new_filename = f"({model}){content_prefix}{random_number}"

        # 拼接回完整的新文件路径
        new_filepath = os.path.join(dir_path, new_filename + file_ext)

        # 重命名原文件
        try:
            os.rename(filepath, new_filepath)
        except OSError as e:
            print(f"Error: {e.strerror}")
            return filepath

        return new_filepath