import requests
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
import uuid
from .ttsapi import _ttsApi

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
            logger.info('Added new user to params_cache. user id = ' + user_id)

        if user_id in self.params_cache and self.params_cache[user_id]['tts_quota'] > 0:
            logger.info('符合转换条件，开始转换')
            self.params_cache[user_id]['tts_quota'] = 0
            self.call_service(content, user_id, e_context)
            return

        if e_context['context'].type == ContextType.TEXT:
            if content.startswith(self.tts_prefix):
                # Call new function to handle search operation
                pattern = self.tts_prefix + r"\s(.+)"
                match = re.match(pattern, content)
                model_str = ",".join(self.model_list)
                tip = f"\n未检测到模型名称，将使用系统默认模型。\n\n💬自定义提示词的格式为：{self.tts_prefix}+空格+模型名称\n\n当前可用模型为：{model_str}"
                if match:
                    tts_model = content[len(self.tts_prefix):].strip()
                    if tts_model in self.model_list:
                        self.params_cache[user_id]['tts_model'] = tts_model
                        tip = f"\n\n💬使用的模型为:{tts_model}"
                    else:
                        self.params_cache[user_id]['tts_model'] = self.tts_model
                        tip = f"\n\n💬错误的模型名称:{tts_model}，将使用默认语音模型"
                    
                else:
                    self.params_cache[user_id]['tts_model'] = self.tts_model

                self.params_cache[user_id]['tts_quota'] = 1
                reply = Reply(type=ReplyType.TEXT, content="💡已开启变声模式。请输入想要转换的文字，为保证转换效果，请不要超过30个字。"+ tip)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS

    def call_service(self, content, user_id, e_context):
        self.handle_sovits(content, user_id, e_context)

    def handle_sovits(self, content, user_id, e_context):
        logger.info(f"handle_sovits, content =  {content}")
        tts_model = self.params_cache[user_id]['tts_model']
        logger.info('using tts_model=' + tts_model)
        
        status, msg, id = self.tts.convert(tts_model, content)
        return self._reply(status, msg, id, e_context)
    
    def _reply(self, status, msg, id, e_context: EventContext):
        if status:
            logger.info('querying task id =' + id)
            rc, rt = self.get_result(id)
            logger.info('_reply, rc =' + rc)
            logger.info('_reply, rt =' + str(rt))
            return self.send(rc, e_context, rt)
        else:
            return self.Error(msg, e_context)
        
    def get_result(self, id):
        status, msg, filepath = self.tts.get_tts_result(id)
        rt = ReplyType.TEXT
        rc = msg
        if not status:
            rt = ReplyType.ERROR
            rc = msg

        if status and filepath:
            logger.info('getting result, status = ' + str(status) + ', file path =' + filepath)
            rt = ReplyType.VOICE
            rc = filepath

        if not rc:
            rt = ReplyType.ERROR
            rc = "语音转换失败"
        return rc, rt

    def send_reply(reply, e_context: EventContext, reply_type=ReplyType.TEXT):
        if isinstance(reply, Reply):
            if not reply.type and reply_type:
                reply.type = reply_type
        else:
            reply = Reply(reply_type, reply)
        channel = e_context['channel']
        context = e_context['context']
        # reply的包装步骤
        rd = channel._decorate_reply(context, reply)
        # reply的发送步骤
        return channel._send_reply(context, rd)

    def send(rc, e_context: EventContext, rt=ReplyType.TEXT, action=EventAction.BREAK_PASS):
        reply = Reply(rt, rc)
        e_context["reply"] = reply
        e_context.action = action
        return
    
    def Error(self, msg, e_context: EventContext):
        return self.send(msg, e_context, ReplyType.ERROR)
