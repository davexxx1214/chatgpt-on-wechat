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

q_text = 'A stunning 3D render of a diverse group of Pokémon gathered in a lush, vibrant environment. The Pokémon include Pikachu, Charizard, Squirtle, Bulbasaur, and Jigglypuff, each showcasing their unique abilities. The background features a colorful, layered landscape with towering mountains, a shimmering lake, and a candy-colored sunset sky. The scene exudes a sense of adventure and excitement, with the Pokémon appearing to be on the brink of an epic battle., 3d render, illustration'

print(ts.translate_text(q_text,  translator='google'))