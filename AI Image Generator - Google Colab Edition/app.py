# ==============================
# Google Colab - AI Image Generator
# Single Script
# ==============================

# Install dependencies
!pip -q install diffusers transformers accelerate torch safetensors

import torch
from diffusers import StableDiffusionPipeline
from PIL import Image
from IPython.display import display

# Load AI Model
model_id = "runwayml/stable-diffusion-v1-5"

pipe = StableDiffusionPipeline.from_pretrained(
    model_id,
    torch_dtype=torch.float16
)

pipe = pipe.to("cuda")

# Input Prompt
prompt = input("Enter your image prompt: ")

# Generate Image
print("Generating Image...")

image = pipe(
    prompt,
    height=768,
    width=768,
    num_inference_steps=30,
    guidance_scale=8
).images[0]

# Save Image
image.save("generated_image.png")

# Display Image
display(image)

print("Done! Saved as generated_image.png")
