# import requests

# response = requests.post(
#     f"https://api.stability.ai/v2alpha/generation/stable-image/inpaint",
#     headers={"authorization": f"Bearer sk-xxx"},
#     files={"image": open("./dog_digital_art.png", "rb")},
#     data={
#         "prompt": "猫",
#         "mode": "search",
#         "search_prompt": "狗",
#         "output_format": "jpeg",
#     },
# )

# if response.status_code == 200:
#     with open("./cat.jpg", 'wb') as file:
#         file.write(response.content)
# else:
#     raise Exception(str(response.json()))

# import re

# def extract_keywords(s):
#     pattern = r"把(.*?)替换成([^，。,.!?;:\s]*).*"
#     match = re.search(pattern, s)

#     if match:
#         return match[1].strip(), match[2].strip()

#     return None, None


# # 测试代码
# test_string1 = '把煎饼替换成油条'
# test1, test2 = extract_keywords(test_string1)
# print("test1:", test1)
# print("test2:", test2)

import requests

response = requests.post(
    f"https://api.stability.ai/v2beta/stable-image/edit/search-and-replace",
    headers={
        "authorization": f"Bearer sk-MYAPIKEY",
        "accept": "image/*"
    },
    files={
        "image": open("./husky-in-a-field.png", "rb")
    },
    data={
        "prompt": "golden retriever in a field",
        "search_prompt": "dog",
        "output_format": "webp",
    },
)

if response.status_code == 200:
    with open("./golden-retriever-in-a-field.webp", 'wb') as file:
        file.write(response.content)
else:
    raise Exception(str(response.json()))