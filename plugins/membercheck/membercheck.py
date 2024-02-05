import json
import plugins
from bridge.reply import Reply, ReplyType
from bridge.context import ContextType
from channel.chat_message import ChatMessage
from plugins import *
from common.log import logger
from common.expired_dict import ExpiredDict
import os

@plugins.register(
    name="membercheck",
    desire_priority=99,
    desc="A plugin to check member credit in group",
    version="0.0.1",
    author="davexxx",
)

class membercheck(Plugin):
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
            self.exclude_commands = self.config.get("exclude_commands","[]")

            self.params_cache = ExpiredDict(500)
            # 初始化成功日志
            logger.info("[membercheck] inited.")
        except Exception as e:
            # 初始化失败日志
            logger.warn(f"membercheck init failed: {e}")

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
            self.params_cache[user_id]['credit'] = 5
            logger.info('Added new user to params_cache. user id = ' + user_id)

        if e_context['context'].type == ContextType.TEXT:
            if user_id in self.params_cache and isgroup:
                match_command = False
                for command in self.exclude_commands:
                    if content.startswith(command):
                        logger.info("检测到特定指令, 不计算credit")
                        match_command = True                            

                if self.params_cache[user_id]['credit'] > 0:
                    if not match_command:
                        self.params_cache[user_id]['credit'] -= 1
                        logger.info(f"当前用户id: {user_id} \n当前credit: {self.params_cache[user_id]['credit']}")
                    e_context.action = EventAction.CONTINUE  # 事件继续，交付给下个插件或默认逻辑
                else:
                    error_tip = f"尊敬的用户，您当前的试用次数已达上限。为了不中断您的体验，您可以选择成为会员享受无限制的服务。或者您也可以稍后再试。感谢您的理解与支持！"
                    reply = Reply(type=ReplyType.TEXT, content= error_tip)
                    e_context["reply"] = reply
                    e_context.action = EventAction.BREAK_PASS
            