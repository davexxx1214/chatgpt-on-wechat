# from googletrans import Translator
# from langdetect import detect

# def is_chinese(text):
#     try:
#         lang = detect(text)
#         print(lang)
#         return lang == 'zh-cn' or lang == 'zh-tw'
#     except:
#         return False
    
# def translate_to_english(text):
#     translator = Translator(service_urls=['translate.google.com'])
#     translation = translator.translate(text, dest='en')
#     return translation.text

# # 用法示例
# chinese_text = "你好，世界"
# if is_chinese(chinese_text):
#     english_text = translate_to_english(chinese_text)
#     print(english_text)
# else:
#     print("no need to translate")

import translators as ts

q_text = '把图片中女生的头发换成灰色'

print(ts.translate_text(q_text,  translator='alibaba'))