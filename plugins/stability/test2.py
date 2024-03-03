import re

def check_match(text):
    # 使用正则查找
    pattern = re.compile(r'replace (.*?) to (.*?)$')

    match = pattern.search(text)
    
    if match is None:
        print("字符串不符合要求的格式.")
        return False
    else:
        print("字符串符合要求的格式.")
        part1, part2 = match.groups()
        print(f"第一部分: {part1}")  # 输出: a box of sand
        print(f"第二部分: {part2}")  # 输出: a hug dragon
        return True
 

# 使用示例
text = "replace water to sand"
check_match(text)