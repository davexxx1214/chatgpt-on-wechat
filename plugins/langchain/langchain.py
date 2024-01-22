# encoding:utf-8

import json
import os

import plugins
from bridge.context import ContextType
from common.log import logger
from plugins import *

import pinecone
from langchain.embeddings.openai import OpenAIEmbeddings
from langchain.vectorstores import Pinecone

@plugins.register(
    name="Langchain",
    desire_priority=0,
    hidden=True,
    desc="用来构建本地知识库",
    version="1.0",
    author="davexxx",
)
class Langchain(Plugin):
    def __init__(self):
        super().__init__()

        try:
            curdir = os.path.dirname(__file__)
            config_path = os.path.join(curdir, "config.json")
            conf = None
            if not os.path.exists(config_path):
                raise Exception("config.json not found")
            else:
                with open(config_path, "r") as f:
                    conf = json.load(f)

            self.pinecone_api_key = conf["pinecone_api_key"]
            self.pinecone_environment = conf["pinecone_environment"]
            self.pinecone_index_name = conf["pinecone_index_name"]
            self.pinecone_name_space = conf["pinecone_name_space"]

            self.openai_api_key = conf["openai_api_key"]
            self.openai_model_name = conf["openai_model_name"]
            self.openai_api_base = conf["openai_api_base"]
            self.openai_api_version = conf["openai_api_version"]
            self.openai_api_type = conf["openai_api_type"]

            self.llm_threshold = conf.get("llm_threshold", 0.8)
            self.plugin_trigger_prefix = conf.get("plugin_trigger_prefix", "$")

            self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
            logger.info("[Langchain] inited")
        except Exception as e:
            logger.warn("[Langchain] init failed.")
            raise e

    def on_handle_context(self, e_context: EventContext):
        if e_context["context"].type not in [
            ContextType.TEXT
        ]:
            return

        content = e_context["context"].content
        logger.debug("[Langchain] on_handle_context. content: %s" % content)

        clists = e_context["context"].content.split(maxsplit=1)
        if clists[0].startswith(self.plugin_trigger_prefix) | clists[0].startswith('/'):
            logger.info("[Langchain] : found plugin trigger prefix. escape.")
            return
        
        
        
        try:
            pinecone.init(
                api_key=self.pinecone_api_key,
                environment=self.pinecone_environment  # find next to API key in console
            )
            index = pinecone.Index(index_name=self.pinecone_index_name)
            embed = OpenAIEmbeddings(
                model=self.openai_model_name,
                deployment=self.openai_model_name,
                openai_api_key=self.openai_api_key,
                openai_api_base=self.openai_api_base,
                openai_api_version=self.openai_api_version,
                openai_api_type=self.openai_api_type
            )
            vectorstore = Pinecone(
                index, embed.embed_query, 'text',namespace=self.pinecone_name_space
            )
            docs = vectorstore.similarity_search_with_score(
                content,  # our search query
                k=1  # return 3 most relevant docs
            )
        except Exception as e:
            logger.warn("[pinecone] init failed.")
            raise e
    
        score = docs[0][1]
        logger.info("search docs with score : %s " % score );
        logger.info("LLM  threshold is : %s " % self.llm_threshold);
        if score < self.llm_threshold:
            logger.info("Nothing match in local vector store, continue...");
            e_context.action = EventAction.CONTINUE
        else:
            logger.info("Found in local vector store, continue...");
            prompt = e_context["context"].content + '''
            如果上下文中包含JSON格式，那么里面的条目代表店铺的具体信息，条目之间相互独立。
            其中name代表店铺名称，"人均"代表人均消费，recommend代表该店铺的推荐菜的列表，
            address代表店铺地址，tel代表店铺电话，comment代表用户评价。
            不要开场白直接回答问题，并优先从以下内容中寻找到答案：
             
            ''' + docs[0][0].page_content
            e_context["context"].type = ContextType.TEXT
            e_context["context"].content = prompt.replace("\n", "")
            logger.debug("prompt is : %s " % prompt);

            e_context.action = EventAction.CONTINUE
        
            
    def get_help_text(self, **kwargs):
        return "搜索本地知识库。"
