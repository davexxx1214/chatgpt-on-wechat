import requests

response = requests.post(
    f"https://api.stability.ai/v2beta/stable-image/generate/ultra",
    headers={
        "authorization": f"Bearer sk-xxx",
        "accept": "image/*"
    },
    files={
        "none": ''
    },
    data={
        "prompt": "AR scenes, Boy playing games wearing VR glasses, There are virtual game scenes in the scene，The character is scaled down in the picture ",
        "output_format": "png",
    },
)

if response.status_code == 200:
    with open("./result.png", 'wb') as file:
        file.write(response.content)
else:
    raise Exception(str(response.json()))