import requests
from PIL import Image

def resize_image(input_image_path, size):
    original_image = Image.open(input_image_path)
    width, height = original_image.size
    print(f'The original image size is {width} wide x {height} high')

    resized_image = original_image.resize(size)
    width, height = resized_image.size
    print(f'The resized image size is {width} wide x {height} high')
    resized_image.show()

# 在这里将路径替换为你图片的实际路径
input_image_path = './4.png'
size = (1024, 1024)
resize_image(input_image_path, size)

response = requests.post(
    f"https://api.stability.ai/v2alpha/generation/image-to-video",
    headers={"authorization": f"Bearer sk-xxx"},
    files={"image": open("./2.jpg", "rb")},
    data={
        "seed": 0,
        "cfg_scale": 1.8,
        "motion_bucket_id": 127
    },
)

print("Generation ID:", response.json())
print("Generation ID:", response.json().get('id'))