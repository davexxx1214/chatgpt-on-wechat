import json
import re
import plugins
from bridge.reply import Reply, ReplyType
from bridge.context import ContextType
from channel.chat_message import ChatMessage
from plugins import *
from common.log import logger
from common.expired_dict import ExpiredDict
from common.tmp_dir import TmpDir

import os
import requests
import uuid

@plugins.register(
    name="stability",
    desire_priority=2,
    desc="A plugin to call stabilityai API",
    version="0.0.1",
    author="davexxx",
)

class stability(Plugin):
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
            self.inpaint_url = self.config.get("inpaint_url","")
            self.inpaint_prefix = self.config.get("inpaint_prefix","修图")
            self.api_key = self.config.get("api_key", "")

            self.params_cache = ExpiredDict(500)
            # 初始化成功日志
            logger.info("[stability] inited.")
        except Exception as e:
            # 初始化失败日志
            logger.warn(f"stability init failed: {e}")
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
            self.params_cache[user_id]['inpaint_quota'] = 0
            self.params_cache[user_id]['search_prompt'] = None
            self.params_cache[user_id]['prompt'] = None
            logger.info('Added new user to params_cache. user id = ' + user_id)

        if e_context['context'].type == ContextType.TEXT:
            if content.startswith(self.inpaint_prefix):
                # Call new function to handle search operation
                pattern = self.inpaint_prefix + r"\s(.+)"
                match = re.match(pattern, content)
                tip = f"💡欢迎使用修图服务，修图指令格式为:\n\n{self.inpaint_prefix}+空格+把xxx替换成yyy\n例如:修图 把狗替换成猫"
                if match:
                    query = content[len(self.inpaint_prefix):].strip()
                    pattern = r"把(.*?)替换成([^，。,.!?;:\s]*).*"
                    match = re.search(pattern, query)
                    if match:
                        search_prompt = match[1].strip()
                        prompt = match[2].strip()
                        self.params_cache[user_id]['search_prompt'] = search_prompt
                        self.params_cache[user_id]['prompt'] = prompt
                        logger.info("search_prompt  =  {search_prompt}")
                        logger.info("prompt =  {prompt}" )
                        self.params_cache[user_id]['inpaint_quota'] = 1

                    else:
                        tip = f"❌错误的命令\n\n💡修图指令格式为:\n\n{self.inpaint_prefix}+空格+把xxx替换成yyy\n例如:修图 把狗替换成猫"
                
                reply = Reply(type=ReplyType.TEXT, content= tip)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS

        elif context.type == ContextType.IMAGE:
            if self.params_cache[user_id]['image_sum_quota'] < 1:
                logger.info("on_handle_context: 当前用户识图配额不够，不进行识别")
                return

            logger.info("on_handle_context: 开始处理图片")
            context.get("msg").prepare()
            image_path = context.content
            logger.info(f"on_handle_context: 获取到图片路径 {image_path}")

            self.params_cache[user_id]['inpaint_quota'] = 0
            self.call_service(image_path, user_id, e_context)

            # 删除文件
            os.remove(image_path)
            logger.info(f"文件 {image_path} 已删除")

    def call_service(self, image_path, user_id, e_context):
        self.handle_stability(image_path, user_id, e_context)

    def handle_stability(self, image_path, user_id, e_context):
        logger.info(f"handle_stability")

        search_prompt = self.params_cache[user_id]['search_prompt']
        prompt = self.params_cache[user_id]['prompt']
        response = requests.post(
            f"{self.inpaint_url}",
            headers={"authorization": f"Bearer {self.api_key}"},
            files={"image": open(image_path, "rb")},
            data={
                "prompt": prompt,
                "mode": "search",
                "search_prompt": search_prompt,
                "output_format": "jpeg",
            },
        )

        if response.status_code == 200:
            imgpath = TmpDir().path() + "stability" + str(uuid.uuid4()) + ".jpg" 
            with open(imgpath, 'wb') as file:
                file.write(response.content)
            
            rt = ReplyType.IMAGE
            rc = imgpath
            reply = Reply(rt, rc)
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS
        else:
            rc= "服务暂不可用"
            rt = ReplyType.TEXT
            reply = Reply(rt, rc)
            logger.error("[stability] service exception")
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS
   