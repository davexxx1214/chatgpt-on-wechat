# encoding:utf-8

import time

import openai
import openai.error
from bot.bot import Bot
from bot.zhipuai.zhipu_ai_session import ZhipuAISession
from bot.zhipuai.zhipu_ai_image import ZhipuAIImage
from bot.session_manager import SessionManager
from bridge.context import ContextType
from bridge.reply import Reply, ReplyType
from common.log import logger
from config import conf, load_config
from zhipuai import ZhipuAI
from datetime import datetime
from zoneinfo import ZoneInfo


# ZhipuAI对话模型API
class ZHIPUAIBot(Bot, ZhipuAIImage):
    def __init__(self):
        super().__init__()
        self.sessions = SessionManager(ZhipuAISession, model=conf().get("model") or "ZHIPU_AI")
        self.args = {
            "model": conf().get("model") or "glm-4",  # 对话模型的名称
            "temperature": conf().get("temperature", 0.9),  # 值在(0,1)之间(智谱AI 的温度不能取 0 或者 1)
            "top_p": conf().get("top_p", 0.7),  # 值在(0,1)之间(智谱AI 的 top_p 不能取 0 或者 1)
        }
        self.tools = {
            "knowledge_id": conf().get("zhipu_ai_knowledge_id")
        }
        self.client = ZhipuAI(api_key=conf().get("zhipu_ai_api_key"))

    def reply(self, query, context=None):
        # acquire reply content
        if context.type == ContextType.TEXT:
            tz = ZoneInfo('Asia/Shanghai')

            # 获取当前UTC+8时区的时间
            now = datetime.now(tz)

            formatted_time = now.strftime("(现在时间是%H点%M分)")
            if "路线" in query:    
                query = f"{query}{formatted_time}"
                
            logger.info("[ZHIPU_AI] query={}".format(query))

            session_id = context["session_id"]
            reply = None
            clear_memory_commands = conf().get("clear_memory_commands", ["#清除记忆"])
            if query in clear_memory_commands:
                self.sessions.clear_session(session_id)
                reply = Reply(ReplyType.INFO, "记忆已清除")
            elif query == "#清除所有":
                self.sessions.clear_all_session()
                reply = Reply(ReplyType.INFO, "所有人记忆已清除")
            elif query == "#更新配置":
                load_config()
                reply = Reply(ReplyType.INFO, "配置已更新")
            if reply:
                return reply
            session = self.sessions.session_query(query, session_id)
            logger.debug("[ZHIPU_AI] session query={}".format(session.messages))

            api_key = context.get("openai_api_key") or openai.api_key
            model = context.get("gpt_model")
            new_args = None
            

            # 构造prompt_template的初始模板
            prompt_template = (
                "你的名字叫小石头,你是中国云南大理石门关景区的智能客服，旨在回答并解决人们关于石门关景区相关的问题,请优先从景区知识库里\n"
                "'''\n"
                "{{knowledge}}\n"
                "'''\n"
                "中找问题\n"
                "'''\n"
                "{{question}}\n"
                "'''\n"
                "的答案，找到答案就参考文档中的答案回答，找不到答案就用自身知识回答并不要告诉用户该信息不是来自知识库.你只能回答跟景区旅游相关的问题，不要回答其他方面的问题。\n"
                "\n"
                "不要复述问题，直接开始回答。"
            )

            # 将formatted_time添加到prompt_template的末尾
            prompt_template_with_time = f"{prompt_template}\n{formatted_time}"
            if model:
                new_args = self.args.copy()
                new_args["model"] = model
            # if context.get('stream'):
            #     # reply in stream
            #     return self.reply_text_stream(query, new_query, session_id)
            if self.tools["knowledge_id"]:
                logger.info("[ZHIPU_AI] tools knowledge_id={}".format(self.tools["knowledge_id"]))
                new_args = self.args.copy()
                new_args["tools"] = [
                    {
                        "type": "retrieval",
                        "retrieval": {
                            "knowledge_id": self.tools["knowledge_id"],
                            "prompt_template": prompt_template_with_time
                        }
                    }
                ]
            reply_content = self.reply_text(session, api_key, args=new_args)
            logger.debug(
                "[ZHIPU_AI] new_query={}, session_id={}, reply_cont={}, completion_tokens={}".format(
                    session.messages,
                    session_id,
                    reply_content["content"],
                    reply_content["completion_tokens"],
                )
            )
            if reply_content["completion_tokens"] == 0 and len(reply_content["content"]) > 0:
                reply = Reply(ReplyType.ERROR, reply_content["content"])
            elif reply_content["completion_tokens"] > 0:
                self.sessions.session_reply(reply_content["content"], session_id, reply_content["total_tokens"])
                reply = Reply(ReplyType.TEXT, reply_content["content"])
            else:
                reply = Reply(ReplyType.ERROR, reply_content["content"])
                logger.debug("[ZHIPU_AI] reply {} used 0 tokens.".format(reply_content))
            return reply
        elif context.type == ContextType.IMAGE_CREATE:
            ok, retstring = self.create_img(query, 0)
            reply = None
            if ok:
                reply = Reply(ReplyType.IMAGE_URL, retstring)
            else:
                reply = Reply(ReplyType.ERROR, retstring)
            return reply

        else:
            reply = Reply(ReplyType.ERROR, "Bot不支持处理{}类型的消息".format(context.type))
            return reply

    def reply_text(self, session: ZhipuAISession, api_key=None, args=None, retry_count=0) -> dict:
        """
        call openai's ChatCompletion to get the answer
        :param session: a conversation session
        :param session_id: session id
        :param retry_count: retry count
        :return: {}
        """
        try:
            # if conf().get("rate_limit_chatgpt") and not self.tb4chatgpt.get_token():
            #     raise openai.error.RateLimitError("RateLimitError: rate limit exceeded")
            # if api_key == None, the default openai.api_key will be used
            if args is None:
                args = self.args
            # response = openai.ChatCompletion.create(api_key=api_key, messages=session.messages, **args)
            response = self.client.chat.completions.create(messages=session.messages, **args)
            # logger.debug("[ZHIPU_AI] response={}".format(response))
            # logger.info("[ZHIPU_AI] reply={}, total_tokens={}".format(response.choices[0]['message']['content'], response["usage"]["total_tokens"]))

            return {
                "total_tokens": response.usage.total_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "content": response.choices[0].message.content,
            }
        except Exception as e:
            need_retry = retry_count < 2
            result = {"completion_tokens": 0, "content": "对不起，这个问题我无法回答。如果您有任何其他关于石门关景区的问题或者需要帮助，请告诉我。"}
            if isinstance(e, openai.error.RateLimitError):
                logger.warn("[ZHIPU_AI] RateLimitError: {}".format(e))
                result["content"] = "提问太快啦，请休息一下再问我吧"
                if need_retry:
                    time.sleep(20)
            elif isinstance(e, openai.error.Timeout):
                logger.warn("[ZHIPU_AI] Timeout: {}".format(e))
                result["content"] = "我没有收到你的消息"
                if need_retry:
                    time.sleep(5)
            elif isinstance(e, openai.error.APIError):
                logger.warn("[ZHIPU_AI] Bad Gateway: {}".format(e))
                result["content"] = "请再问我一次"
                if need_retry:
                    time.sleep(10)
            elif isinstance(e, openai.error.APIConnectionError):
                logger.warn("[ZHIPU_AI] APIConnectionError: {}".format(e))
                result["content"] = "我连接不到你的网络"
                if need_retry:
                    time.sleep(5)
            else:
                logger.exception("[ZHIPU_AI] Exception: {}".format(e), e)
                need_retry = False
                self.sessions.clear_session(session.session_id)

            if need_retry:
                logger.warn("[ZHIPU_AI] 第{}次重试".format(retry_count + 1))
                return self.reply_text(session, api_key, args, retry_count + 1)
            else:
                return result
