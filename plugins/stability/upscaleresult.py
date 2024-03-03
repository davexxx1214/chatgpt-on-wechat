import requests

generation_id = "26c0a0ae2a1d73a3f403eed398fcbe4b9be35d3dd813d70714b926fcfc448c33"

response = requests.request(
    "GET",
    f"https://api.stability.ai/v2alpha/generation/stable-image/upscale/result/{generation_id}",
    headers={
        'Accept': "image/*",  # Use 'application/json' to receive base64 encoded JSON
        'authorization': f"Bearer sk-xxx"
    },
)


print(response.status_code)

if response.status_code == 202:
    print("Generation in-progress, try again in 10 seconds.")
elif response.status_code == 200:
    print("Generation complete!")
    with open("upscaled.png", 'wb') as file:
        file.write(response.content)
else:
    raise Exception(str(response.json()))