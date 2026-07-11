from PIL import Image

# Load the original app icon
img = Image.open('icon.png').convert('RGBA')

# The image is 1024x1024 (or whatever size). We want to crop the central logo.
# Let's crop a square in the middle, assuming the text is at the bottom.
width, height = img.size
# Assuming the logo is roughly in the center, and text is at the bottom 20%
# Let's crop the top 80% and center it.
# Actually, the logo in the generated image is usually vertically centered in the top 80%.
# Let's crop to a bounding box.
crop_box = (int(width*0.15), int(height*0.1), int(width*0.85), int(height*0.8))
img_cropped = img.crop(crop_box)

# Now, convert to grayscale
gray = img_cropped.convert('L')

# We want the white parts of the logo to become opaque (alpha=255) 
# and the black background to become transparent (alpha=0).
# In a macOS Template image, the image should be all black (or any single color),
# and the alpha channel defines the shape.
# So we create a new image: all black (0,0,0), and the alpha channel is the grayscale image.

template_img = Image.new('RGBA', gray.size, (0, 0, 0, 0))
template_img.putalpha(gray)

# Resize to menu bar size, e.g., 22x22 or 18x18
template_img = template_img.resize((18, 18), Image.Resampling.LANCZOS)
template_img.save('menubar_iconTemplate.png')
print("Created menubar_iconTemplate.png")
