from rembg import remove 
from PIL import Image 
input_path = 'animal-1.jpg' 
output_path = 'animal-11.png' 
inp = Image.open(input_path) 
outpout = remove(inp) 
outpout.save(output_path)