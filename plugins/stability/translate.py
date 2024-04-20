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

q_text = '四十多岁中国秃头女程序员穿着浅蓝宽松圆领卫衣，struggling的表情在有落地窗的办公室痛苦的写着代码'

print(ts.translate_text(q_text,  translator='baidu'))