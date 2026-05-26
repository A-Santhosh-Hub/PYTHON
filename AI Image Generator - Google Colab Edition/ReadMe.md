# 🎨 AI Image Generator - Google Colab Edition

Generate AI images directly inside **Google Colab** using **Stable Diffusion** and **Python**.

This project uses **Hugging Face Diffusers + Stable Diffusion v1.5** to generate high-quality images from text prompts.

---

## ✨ Features

✔️ Single Python Script

✔️ Google Colab Ready

✔️ GPU Support (CUDA)

✔️ Prompt-Based AI Image Generation

✔️ Stable Diffusion v1.5 Model

✔️ Automatic Image Display

✔️ Auto Save Generated Image

✔️ Beginner Friendly Setup

---

## 📷 Example Prompt

```txt
Cyberpunk futuristic city at night, ultra realistic, neon lights, cinematic, 8k
```

---

## 🛠 Requirements

Before running the project, make sure you have:

- Python 3.10+
- Google Colab Account
- GPU Runtime Enabled
- Internet Connection

---

## 🚀 Google Colab Setup

### Step 1 — Open Google Colab

Go to:

https://colab.research.google.com

---

### Step 2 — Enable GPU

Click:

Runtime → Change Runtime Type → Hardware Accelerator → GPU

Select:

**GPU**

Click **Save**

---

### Step 3 — Create New Notebook

Create a new notebook.

---

### Step 4 — Paste the Script

Copy and paste the Python script into a Colab cell.

---

### Step 5 — Run the Code

Press:

```txt
Shift + Enter
```

The script will automatically:

- Install dependencies
- Load Stable Diffusion
- Ask for prompt input
- Generate image
- Display image
- Save image

---

## 📦 Installation

Dependencies are installed automatically inside Colab.

Manual installation:

```bash
pip install diffusers transformers accelerate torch safetensors
```

---

## 💻 Usage

Run:

```python
prompt = input("Enter your image prompt: ")
```

Example:

```txt
A futuristic robot warrior, ultra realistic, cinematic lighting, 8k
```

Generated image will be:

```txt
generated_image.png
```

---

## 📁 Project Structure

```txt
AI-Image-Generator/
│
├── image_generator.py
├── README.md
│
└── generated_image.png
```

---

## 🔥 Model Used

Model:

```txt
runwayml/stable-diffusion-v1-5
```

Framework:

- Hugging Face Diffusers
- PyTorch
- Transformers

---

## ⚡ Performance Notes

Recommended GPU:

- T4 GPU
- A100 GPU
- L4 GPU

Generation speed depends on:

- GPU type
- Image size
- Inference steps

---

## 🐞 Troubleshooting

### CUDA Error

Enable GPU Runtime inside Google Colab.

---

### Out Of Memory Error

Reduce image size:

```python
height=512
width=512
```

Reduce inference steps:

```python
num_inference_steps=20
```

---

### Slow Generation

Use a better GPU runtime.

---

## 📄 License

This project is licensed under the MIT License.

---

## 👨‍💻 Author

**Santhosh A**

Founder — **SanStudio**

GitHub: https://github.com/YOUR_USERNAME

---

## ⭐ Support

If you like this project:

⭐ Star this repository

🍴 Fork this repository

🚀 Share with others
