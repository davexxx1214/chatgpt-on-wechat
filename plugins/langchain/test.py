import os

from pinecone import Pinecone
from langchain_community.vectorstores import Pinecone as PineconeStore
from langchain_community.embeddings.openai import OpenAIEmbeddings

import json

class _langchainApi:
    def __init__(self):
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

    
    def get_docs(self, content):
        try:
            # configure client
            pc = Pinecone(api_key=self.pinecone_api_key)
            index_name = self.pinecone_index_name
            index = pc.Index(index_name)

            embed = OpenAIEmbeddings(
                model=self.openai_model_name,
                deployment=self.openai_model_name,
                openai_api_key=self.openai_api_key,
                openai_api_base=self.openai_api_base,
                openai_api_version=self.openai_api_version,
                openai_api_type=self.openai_api_type
            )
            vectorstore = PineconeStore(
                index, embed, 'text',namespace=self.pinecone_name_space
            )
            docs = vectorstore.similarity_search_with_score(
                content,  # our search query
                k=1  # return 3 most relevant docs
            )
            score = docs[0][1]
            print("search docs with score : %s " % score )
            print(docs[0][0].page_content)
        except Exception as e:
            raise e
    
        # score = docs[0][1]
        # print("search docs with score : %s " % score );
        # print("LLM  threshold is : %s " % self.llm_threshold);
        # if score < self.llm_threshold:
        #     print("Nothing match in local vector store, continue...");
        # else:
        #     print("Found in local vector store, continue...");
        #     prompt = '''
        #     结合上下文，请优先尝试从以下内容中寻找到答案：
             
        #     ''' + docs[0][0].page_content

def main():

    
    api = _langchainApi()

    api.get_docs('如何学好数理')

if __name__ == '__main__':
    main()