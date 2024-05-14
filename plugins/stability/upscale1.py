import replicate
import os

import base64


# 设置环境变量
os.environ['REPLICATE_API_TOKEN'] = 'r8_6lfxAzr995cdd1KJHt3lWifkXDHt3At2rvMze'


with open("./1.jpg", "rb")as file:
  data = base64.b64encode(file.read()).decode('utf-8')
  image = f"data:application/octet-stream;base64,{data}"


input = {
    "image": image,
    "creativity": 0.1
}

output = replicate.run(
    "philz1337x/clarity-upscaler:b889f2d6c5720b5eb296e6338990fc40036994307ed660cdc8c10c0343d652ca",
    input=input
)
print(output)