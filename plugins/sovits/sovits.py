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
            
            self.tts = _ttsApi(self.config)
            # 设置事件处理函数
            self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
            # 从配置中提取所需的设置
            self.api_url = self.config.get("api_url","")
            self.tts_prefix = self.config.get("tts_prefix","变声")
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
        if context.type not in [ContextType.TEXT, ContextType.SHARING,ContextType.FILE,ContextType.IMAGE]:
            return
        msg: ChatMessage = e_context["context"]["msg"]
        user_id = msg.from_user_id
        content = context.content
        isgroup = e_context["context"].get("isgroup", False)

        # 将用户信息存储在params_cache中
        if user_id not in self.params_cache:
            self.params_cache[user_id] = {}
            self.params_cache[user_id]['tts_quota'] = 0
            logger.debug('Added new user to params_cache. user id = ' + user_id)

        if user_id in self.params_cache and self.params_cache[user_id]['tts_quota'] > 0:
            logger.info('符合转换条件，开始转换')
            if len(content) > 200:
                error_tip = f"❌转换文本不能超过200个字"
                reply = Reply(type=ReplyType.TEXT, content= error_tip)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
            else:
                self.params_cache[user_id]['tts_quota'] = 0
                self.call_service(content, user_id, e_context)
                return

        if e_context['context'].type == ContextType.TEXT:
            if content.startswith(self.tts_prefix):
                # Call new function to handle search operation
                pattern = self.tts_prefix + r"\s(.+)"
                match = re.match(pattern, content)
                model_str = "\n".join(self.model_list)
                tip = f"💡欢迎使用变声服务，变声指令格式为:\n\n{self.tts_prefix}+空格+模型名称\n\n💬当前可用模型为：\n{model_str}"
                if match:
                    tts_model = content[len(self.tts_prefix):].strip()
                    if tts_model in self.model_list:
                        real_model = self.model_mappings.get(tts_model)
                        self.params_cache[user_id]['tts_model'] = real_model
                        self.params_cache[user_id]['tts_quota'] = 1
                        tip = f"💡{tts_model}已就位（语音素材来源网络,仅供学习研究,严禁用于商业及违法途径）"
                    else:
                        tip = f"❌错误的模型名称:{tts_model}，\n\n💡变声指令格式为：{self.tts_prefix}+空格+模型名称\n\n💬当前可用模型为：{model_str}"
                    
                else:
                    self.params_cache[user_id]['tts_model'] = self.tts_model

                
                reply = Reply(type=ReplyType.TEXT, content= tip)
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