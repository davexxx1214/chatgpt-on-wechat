import requests

response = requests.post(
    f"https://api.stability.ai/v2beta/stable-image/upscale/fast",
    headers={
        "authorization": f"Bearer sk-xxx",
        "accept": "image/*"
    },
    files={
        "image": open("./1.png", "rb")
    },
    data={
        "output_format": "png",
    },
)

if response.status_code == 200:
    with open("./result.png", 'wb') as file:
        file.write(response.content)
else:
    raise Exception(str(response.json()))

# print("Generation ID:", response.json().get('id'))