# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║          SanStudio · AI Image Generator for Google Colab                   ║
# ║          ComfyUI-style · Stable Diffusion · Advanced Controls              ║
# ║          Built by SanStudio  |  https://a-santhosh-hub.github.io/in/       ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

# ─────────────────────────────────────────────────────────────────────────────
#  STEP 1 ── Install Dependencies  (run this cell first, then restart runtime)
# ─────────────────────────────────────────────────────────────────────────────
import subprocess, sys

def install(pkg):
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", pkg])

print("📦 Installing dependencies …")
install("diffusers>=0.27.0")
install("transformers>=4.38.0")
install("accelerate>=0.28.0")
install("safetensors")
install("xformers")          # optional – speeds up if compatible GPU found
install("compel")            # advanced prompt weighting
install("invisible_watermark")
install("Pillow")
install("ipywidgets")
install("tqdm")
print("✅ All packages installed.\n")

# ─────────────────────────────────────────────────────────────────────────────
#  STEP 2 ── Imports
# ─────────────────────────────────────────────────────────────────────────────
import os, gc, time, math, warnings
warnings.filterwarnings("ignore")

import torch
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from IPython.display import display, clear_output, HTML
import ipywidgets as widgets
from diffusers import (
    StableDiffusionPipeline,
    StableDiffusionImg2ImgPipeline,
    StableDiffusionInpaintPipeline,
    DPMSolverMultistepScheduler,
    DPMSolverSinglestepScheduler,
    EulerAncestralDiscreteScheduler,
    EulerDiscreteScheduler,
    DDIMScheduler,
    LMSDiscreteScheduler,
    HeunDiscreteScheduler,
    KDPM2DiscreteScheduler,
    KDPM2AncestralDiscreteScheduler,
    UniPCMultistepScheduler,
)
from compel import Compel

# ─────────────────────────────────────────────────────────────────────────────
#  STEP 3 ── Config & Model Registry
# ─────────────────────────────────────────────────────────────────────────────
DEVICE        = "cuda" if torch.cuda.is_available() else "cpu"
DTYPE         = torch.float16 if DEVICE == "cuda" else torch.float32
OUTPUT_DIR    = "/content/SanStudio_outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

print(f"🖥️  Device : {DEVICE.upper()}  |  dtype : {DTYPE}")
if DEVICE == "cuda":
    props = torch.cuda.get_device_properties(0)
    print(f"🎮  GPU    : {props.name}  |  VRAM : {props.total_memory/1e9:.1f} GB")

MODELS = {
    "Stable Diffusion 1.5 (General)"      : "runwayml/stable-diffusion-v1-5",
    "Dreamshaper v8 (Artistic)"            : "Lykon/dreamshaper-8",
    "Realistic Vision v5 (Photorealistic)": "SG161222/Realistic_Vision_V5.1_noVAE",
    "Anything v5 (Anime)"                  : "stablediffusionapi/anything-v5",
    "DivineEleganceMix (Fantasy)"          : "digiplay/DivineEleganceMix_v6",
    "AbsoluteReality (Ultra Real)"         : "digiplay/AbsoluteReality_v1.8.1",
    "Deliberate v3 (Semi-Realistic)"       : "XpucT/Deliberate",
    "OpenJourney v4 (Midjourney-style)"    : "prompthero/openjourney-v4",
}

SCHEDULERS = {
    "DPM++ 2M Karras (Recommended)"  : DPMSolverMultistepScheduler,
    "DPM++ SDE Karras"               : DPMSolverSinglestepScheduler,
    "Euler a"                        : EulerAncestralDiscreteScheduler,
    "Euler"                          : EulerDiscreteScheduler,
    "DDIM"                           : DDIMScheduler,
    "LMS Karras"                     : LMSDiscreteScheduler,
    "Heun"                           : HeunDiscreteScheduler,
    "KDPM2 Karras"                   : KDPM2DiscreteScheduler,
    "KDPM2 Ancestral"                : KDPM2AncestralDiscreteScheduler,
    "UniPC"                          : UniPCMultistepScheduler,
}

ASPECT_RATIOS = {
    "Square 512×512"       : (512,  512),
    "Square 768×768"       : (768,  768),
    "Portrait 512×768"     : (512,  768),
    "Portrait 512×912"     : (512,  912),
    "Landscape 768×512"    : (768,  512),
    "Landscape 912×512"    : (912,  512),
    "Widescreen 768×432"   : (768,  432),
    "HD 1024×576"          : (1024, 576),
    "Tall 576×1024"        : (576, 1024),
    "Custom"               : None,
}

STYLE_PRESETS = {
    "None"                   : ("", ""),
    "Cinematic"              : ("cinematic lighting, film grain, dramatic shadows, anamorphic lens, 35mm", "cartoon, flat, low quality"),
    "Photorealistic"         : ("RAW photo, 8k uhd, DSLR, sharp focus, photorealistic, ultra-detailed, award-winning photography", "painting, cartoon, anime"),
    "Digital Art"            : ("digital art, concept art, artstation trending, 4k, detailed illustration", "photo, realistic"),
    "Anime / Manga"          : ("anime style, studio ghibli, detailed linework, vibrant colors, 4k anime wallpaper", "realistic, photo, 3d render"),
    "Oil Painting"           : ("oil painting, classical art, canvas texture, brush strokes, old masters style, museum quality", "digital, photo, anime"),
    "Watercolor"             : ("watercolor painting, soft colors, wet on wet, artistic, loose brushwork", "sharp, photo, digital"),
    "3D Render"              : ("3D render, octane render, unreal engine 5, physically based rendering, HDR", "flat, 2D, sketch"),
    "Cyberpunk"              : ("cyberpunk city, neon lights, rain, dark alley, blade runner aesthetic, volumetric fog", "medieval, daylight, nature"),
    "Fantasy Illustration"   : ("fantasy art, magical, ethereal, storybook illustration, artstation, dramatic lighting", "modern, photorealistic, mundane"),
    "Vintage / Retro"        : ("vintage photo, retro aesthetic, aged, film emulation, faded colors, 70s style", "modern, digital, crisp"),
    "Minimalist"             : ("minimalist, clean lines, simple shapes, white background, elegant, negative space", "busy, cluttered, detailed"),
    "Studio Portrait"        : ("studio portrait, professional photography, soft box lighting, sharp focus, 85mm lens, bokeh", "outdoor, candid, motion blur"),
}

# ─────────────────────────────────────────────────────────────────────────────
#  STEP 4 ── Pipeline Manager
# ─────────────────────────────────────────────────────────────────────────────
class PipelineManager:
    def __init__(self):
        self.pipe        = None
        self.loaded_model = None
        self.loaded_mode  = None
        self.compel_proc  = None

    def load(self, model_id: str, mode: str = "txt2img"):
        if self.loaded_model == model_id and self.loaded_mode == mode and self.pipe:
            print("✅ Model already loaded.")
            return
        print(f"\n🔄 Loading: {model_id} [{mode}] …")
        if self.pipe:
            del self.pipe, self.compel_proc
            gc.collect()
            if DEVICE == "cuda":
                torch.cuda.empty_cache()

        kwargs = dict(torch_dtype=DTYPE, safety_checker=None, requires_safety_checker=False)

        if mode == "txt2img":
            self.pipe = StableDiffusionPipeline.from_pretrained(model_id, **kwargs)
        elif mode == "img2img":
            self.pipe = StableDiffusionImg2ImgPipeline.from_pretrained(model_id, **kwargs)
        elif mode == "inpaint":
            self.pipe = StableDiffusionInpaintPipeline.from_pretrained(model_id, **kwargs)

        self.pipe = self.pipe.to(DEVICE)

        # Memory optimizations
        if DEVICE == "cuda":
            try:
                self.pipe.enable_xformers_memory_efficient_attention()
                print("   ⚡ xFormers attention enabled")
            except Exception:
                self.pipe.enable_attention_slicing()
                print("   🧠 Attention slicing enabled")
            self.pipe.enable_vae_slicing()

        # Compel for prompt weighting
        self.compel_proc = Compel(
            tokenizer=self.pipe.tokenizer,
            text_encoder=self.pipe.text_encoder
        )

        self.loaded_model = model_id
        self.loaded_mode  = mode
        print(f"✅ Model ready!\n")

    def set_scheduler(self, scheduler_class, config):
        self.pipe.scheduler = scheduler_class.from_config(
            config,
            use_karras_sigmas=True if "Karras" in str(scheduler_class) else False
        )

mgr = PipelineManager()

# ─────────────────────────────────────────────────────────────────────────────
#  STEP 5 ── Post-Processing Helpers
# ─────────────────────────────────────────────────────────────────────────────
def apply_postprocess(img: Image.Image, cfg: dict) -> Image.Image:
    if cfg.get("sharpen", 0) > 0:
        for _ in range(cfg["sharpen"]):
            img = img.filter(ImageFilter.SHARPEN)
    if cfg.get("brightness", 1.0) != 1.0:
        img = ImageEnhance.Brightness(img).enhance(cfg["brightness"])
    if cfg.get("contrast", 1.0) != 1.0:
        img = ImageEnhance.Contrast(img).enhance(cfg["contrast"])
    if cfg.get("saturation", 1.0) != 1.0:
        img = ImageEnhance.Color(img).enhance(cfg["saturation"])
    if cfg.get("upscale", 1) > 1:
        w, h  = img.size
        scale = cfg["upscale"]
        img   = img.resize((w * scale, h * scale), Image.LANCZOS)
    return img

def add_watermark(img: Image.Image, text: str = "SanStudio") -> Image.Image:
    draw = ImageDraw.Draw(img)
    w, h = img.size
    draw.text((w - 110, h - 22), text, fill=(255, 255, 255, 120))
    return img

def make_grid(images, cols=None) -> Image.Image:
    n    = len(images)
    cols = cols or math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)
    W, H = images[0].size
    grid = Image.new("RGB", (cols * W, rows * H), (20, 20, 20))
    for i, im in enumerate(images):
        grid.paste(im, ((i % cols) * W, (i // cols) * H))
    return grid

def save_image(img: Image.Image, prefix: str = "output") -> str:
    ts   = int(time.time())
    path = os.path.join(OUTPUT_DIR, f"{prefix}_{ts}.png")
    img.save(path, "PNG")
    return path

# ─────────────────────────────────────────────────────────────────────────────
#  STEP 6 ── Core Generator
# ─────────────────────────────────────────────────────────────────────────────
def generate(
    prompt         : str,
    negative_prompt: str  = "",
    model_key      : str  = "Stable Diffusion 1.5 (General)",
    scheduler_key  : str  = "DPM++ 2M Karras (Recommended)",
    style_key      : str  = "None",
    width          : int  = 512,
    height         : int  = 512,
    steps          : int  = 30,
    cfg_scale      : float= 7.5,
    num_images     : int  = 1,
    seed           : int  = -1,
    clip_skip      : int  = 1,
    mode           : str  = "txt2img",
    init_image     : Image.Image | None = None,
    strength       : float= 0.7,
    postprocess    : dict = None,
    watermark      : bool = False,
    show_grid      : bool = True,
) -> list:

    # ── Apply style preset ──────────────────────────────────────────────────
    style_pos, style_neg = STYLE_PRESETS.get(style_key, ("",""))
    full_prompt    = f"{prompt}, {style_pos}".strip(", ") if style_pos else prompt
    full_neg       = f"{negative_prompt}, {style_neg}".strip(", ") if style_neg else negative_prompt
    if not full_neg:
        full_neg = (
            "lowres, bad anatomy, bad hands, missing fingers, extra digit, "
            "fewer digits, cropped, worst quality, low quality, nsfw, "
            "blurry, text, watermark, ugly, deformed"
        )

    model_id = MODELS[model_key]
    mgr.load(model_id, mode)

    # ── Scheduler ───────────────────────────────────────────────────────────
    sched_cls = SCHEDULERS[scheduler_key]
    try:
        mgr.set_scheduler(sched_cls, mgr.pipe.scheduler.config)
    except Exception:
        mgr.pipe.scheduler = sched_cls.from_config(mgr.pipe.scheduler.config)

    # ── CLIP skip (layer offset) ─────────────────────────────────────────────
    if clip_skip > 1 and hasattr(mgr.pipe, "text_encoder"):
        mgr.pipe.text_encoder.config.num_hidden_layers -= (clip_skip - 1)

    # ── Seed ────────────────────────────────────────────────────────────────
    seeds = []
    rng   = []
    for i in range(num_images):
        s = seed if seed != -1 else torch.randint(0, 2**32 - 1, (1,)).item()
        seeds.append(s)
        rng.append(torch.Generator(device=DEVICE).manual_seed(s))

    # ── Prompt embeddings via Compel ─────────────────────────────────────────
    pos_embeds = mgr.compel_proc(full_prompt)
    neg_embeds = mgr.compel_proc(full_neg)

    print(f"\n🎨 Generating {num_images} image(s) …")
    print(f"   Model    : {model_key}")
    print(f"   Scheduler: {scheduler_key}")
    print(f"   Style    : {style_key}")
    print(f"   Size     : {width}×{height}")
    print(f"   Steps    : {steps}  |  CFG : {cfg_scale}  |  Seed(s) : {seeds}\n")

    generated = []
    postprocess = postprocess or {}

    for i in range(num_images):
        print(f"  🖼️  Image {i+1}/{num_images}  seed={seeds[i]} …")
        t0 = time.time()

        common = dict(
            prompt_embeds         = pos_embeds,
            negative_prompt_embeds= neg_embeds,
            num_inference_steps   = steps,
            guidance_scale        = cfg_scale,
            generator             = rng[i],
        )

        if mode == "txt2img":
            out = mgr.pipe(width=width, height=height, **common)
        elif mode == "img2img":
            assert init_image, "init_image required for img2img"
            init_resized = init_image.resize((width, height))
            out = mgr.pipe(image=init_resized, strength=strength, **common)
        elif mode == "inpaint":
            assert init_image, "init_image required for inpaint"
            out = mgr.pipe(image=init_image, **common)

        img = out.images[0]
        img = apply_postprocess(img, postprocess)
        if watermark:
            img = add_watermark(img)

        path = save_image(img, prefix=f"san_{mode}")
        print(f"     ✅ Saved → {path}  [{time.time()-t0:.1f}s]")
        generated.append(img)

    # ── Display ──────────────────────────────────────────────────────────────
    if show_grid and len(generated) > 1:
        grid = make_grid(generated)
        grid_path = save_image(grid, "san_grid")
        print(f"\n🗂️  Grid → {grid_path}")
        display(grid)
    else:
        for img in generated:
            display(img)

    print("\n✨ Generation complete!\n")
    return generated

# ─────────────────────────────────────────────────────────────────────────────
#  STEP 7 ── Interactive Widget UI  (ComfyUI-style inside Colab)
# ─────────────────────────────────────────────────────────────────────────────
def launch_ui():
    # ── Style ────────────────────────────────────────────────────────────────
    display(HTML("""
    <style>
      .widget-label { color: #e0d7ff !important; font-weight: 600; font-size: 13px; }
      .section-header {
        background: linear-gradient(90deg, #1a0533, #2d0b5e);
        color: #c9a0ff;
        padding: 6px 14px;
        border-radius: 6px;
        font-weight: bold;
        font-size: 13px;
        letter-spacing: 1px;
        margin: 8px 0 4px 0;
        border-left: 3px solid #8b5cf6;
      }
    </style>
    <div style="
      background: linear-gradient(135deg,#0d0221,#1a0533,#0d0221);
      padding: 18px 22px 12px;
      border-radius: 12px;
      border: 1px solid #4c1d95;
      box-shadow: 0 0 30px #7c3aed44;
      margin-bottom: 12px;
    ">
      <h2 style="color:#c9a0ff;margin:0 0 4px;font-family:monospace;letter-spacing:2px;">
        ⚡ SanStudio · AI Image Generator
      </h2>
      <p style="color:#7c6898;font-size:12px;margin:0;">
        ComfyUI-style Studio · Stable Diffusion · Google Colab
        &nbsp;|&nbsp; <a href="https://a-santhosh-hub.github.io/in/" style="color:#8b5cf6;">SanStudio</a>
      </p>
    </div>
    """))

    # ── Widgets ──────────────────────────────────────────────────────────────
    lyt_full = widgets.Layout(width="100%")
    lyt_half = widgets.Layout(width="49%")

    w_prompt = widgets.Textarea(
        placeholder="Enter your prompt here … e.g.  a futuristic city at night, neon lights, cinematic",
        layout=widgets.Layout(width="100%", height="80px"),
        style={"description_width": "initial"}
    )
    w_neg = widgets.Textarea(
        value="lowres, bad anatomy, worst quality, blurry, watermark, text, ugly",
        layout=widgets.Layout(width="100%", height="60px"),
        style={"description_width": "initial"}
    )
    w_model    = widgets.Dropdown(options=list(MODELS.keys()),     layout=lyt_full)
    w_sched    = widgets.Dropdown(options=list(SCHEDULERS.keys()), layout=lyt_full)
    w_style    = widgets.Dropdown(options=list(STYLE_PRESETS.keys()), layout=lyt_full)
    w_aspect   = widgets.Dropdown(options=list(ASPECT_RATIOS.keys()), layout=lyt_half)
    w_mode     = widgets.Dropdown(options=["txt2img", "img2img"], layout=lyt_half)

    w_steps    = widgets.IntSlider(value=30, min=10, max=100, step=1,
                                   description="Steps:", style={"description_width":"80px"}, layout=lyt_half)
    w_cfg      = widgets.FloatSlider(value=7.5, min=1.0, max=20.0, step=0.5,
                                     description="CFG:", style={"description_width":"80px"}, layout=lyt_half)
    w_num      = widgets.IntSlider(value=1, min=1, max=8, step=1,
                                   description="Count:", style={"description_width":"80px"}, layout=lyt_half)
    w_seed     = widgets.IntText(value=-1, description="Seed (-1=random):",
                                  style={"description_width":"120px"}, layout=lyt_half)
    w_strength = widgets.FloatSlider(value=0.7, min=0.1, max=1.0, step=0.05,
                                     description="Strength:", style={"description_width":"80px"}, layout=lyt_half)
    w_clip     = widgets.IntSlider(value=1, min=1, max=4, step=1,
                                   description="CLIP skip:", style={"description_width":"80px"}, layout=lyt_half)

    # Custom size
    w_cw = widgets.IntText(value=512, description="Width:",  style={"description_width":"60px"}, layout=lyt_half)
    w_ch = widgets.IntText(value=512, description="Height:", style={"description_width":"60px"}, layout=lyt_half)
    w_custom_box = widgets.HBox([w_cw, w_ch])
    w_custom_box.layout.display = "none"

    def on_aspect_change(change):
        w_custom_box.layout.display = "flex" if change["new"] == "Custom" else "none"
    w_aspect.observe(on_aspect_change, names="value")

    # Post-process
    w_sharp  = widgets.IntSlider(value=0, min=0, max=5, step=1,
                                  description="Sharpen:", style={"description_width":"80px"}, layout=lyt_half)
    w_bright = widgets.FloatSlider(value=1.0, min=0.5, max=2.0, step=0.05,
                                    description="Brightness:", style={"description_width":"90px"}, layout=lyt_half)
    w_contra = widgets.FloatSlider(value=1.0, min=0.5, max=2.0, step=0.05,
                                    description="Contrast:", style={"description_width":"90px"}, layout=lyt_half)
    w_satur  = widgets.FloatSlider(value=1.0, min=0.5, max=2.0, step=0.05,
                                    description="Saturation:", style={"description_width":"90px"}, layout=lyt_half)
    w_upscale = widgets.Dropdown(options=[("None",1),("2×",2),("4×",4)],
                                  description="Upscale:", style={"description_width":"80px"}, layout=lyt_half)
    w_watermark = widgets.Checkbox(value=False, description="Add SanStudio watermark")
    w_grid      = widgets.Checkbox(value=True,  description="Show grid for multiple images")

    # ── Generate button ───────────────────────────────────────────────────────
    w_btn = widgets.Button(
        description="⚡  GENERATE",
        button_style="",
        layout=widgets.Layout(width="100%", height="46px")
    )
    w_btn.style.button_color = "#7c3aed"
    w_btn.style.font_weight  = "bold"
    w_out = widgets.Output()

    def on_generate(b):
        w_btn.disabled    = True
        w_btn.description = "⏳  Generating …"
        with w_out:
            clear_output(wait=True)
            # Resolve size
            ar = ASPECT_RATIOS[w_aspect.value]
            W, H = (w_cw.value, w_ch.value) if ar is None else ar
            # Align to 64
            W = (W // 64) * 64
            H = (H // 64) * 64

            generate(
                prompt          = w_prompt.value,
                negative_prompt = w_neg.value,
                model_key       = w_model.value,
                scheduler_key   = w_sched.value,
                style_key       = w_style.value,
                width           = W,
                height          = H,
                steps           = w_steps.value,
                cfg_scale       = w_cfg.value,
                num_images      = w_num.value,
                seed            = w_seed.value,
                clip_skip       = w_clip.value,
                mode            = w_mode.value,
                strength        = w_strength.value,
                postprocess     = {
                    "sharpen"   : w_sharp.value,
                    "brightness": w_bright.value,
                    "contrast"  : w_contra.value,
                    "saturation": w_satur.value,
                    "upscale"   : w_upscale.value,
                },
                watermark       = w_watermark.value,
                show_grid       = w_grid.value,
            )
        w_btn.disabled    = False
        w_btn.description = "⚡  GENERATE"

    w_btn.on_click(on_generate)

    # ── Assemble layout ───────────────────────────────────────────────────────
    def H2(txt):
        return widgets.HTML(f'<div class="section-header">{txt}</div>')

    ui = widgets.VBox([
        H2("📝  PROMPT"),
        widgets.HTML("<b style='color:#c9a0ff'>Positive Prompt</b>"),
        w_prompt,
        widgets.HTML("<b style='color:#c9a0ff'>Negative Prompt</b>"),
        w_neg,

        H2("🤖  MODEL & SAMPLER"),
        widgets.HTML("<b style='color:#c9a0ff'>Model</b>"),
        w_model,
        widgets.HTML("<b style='color:#c9a0ff'>Scheduler / Sampler</b>"),
        w_sched,
        widgets.HTML("<b style='color:#c9a0ff'>Style Preset</b>"),
        w_style,

        H2("⚙️  GENERATION SETTINGS"),
        widgets.HBox([w_mode, w_aspect]),
        w_custom_box,
        widgets.HBox([w_steps, w_cfg]),
        widgets.HBox([w_num,   w_seed]),
        widgets.HBox([w_clip,  w_strength]),

        H2("🎨  POST-PROCESS"),
        widgets.HBox([w_sharp,  w_bright]),
        widgets.HBox([w_contra, w_satur]),
        widgets.HBox([w_upscale]),
        widgets.HBox([w_watermark, w_grid]),

        H2(""),
        w_btn,
        w_out,
    ], layout=widgets.Layout(
        padding="16px",
        background="transparent",
        border="1px solid #4c1d95",
        border_radius="12px",
    ))
    display(ui)

# ─────────────────────────────────────────────────────────────────────────────
#  STEP 8 ── Quick-Use Functions (no UI)
# ─────────────────────────────────────────────────────────────────────────────
def quick_generate(
    prompt: str,
    style : str  = "None",
    model : str  = "Dreamshaper v8 (Artistic)",
    size  : str  = "Square 512×512",
    steps : int  = 30,
    seed  : int  = -1,
    count : int  = 1,
):
    """One-liner helper for quick generation."""
    W, H = ASPECT_RATIOS[size] or (512, 512)
    return generate(
        prompt=prompt, style_key=style,
        model_key=model, width=W, height=H,
        steps=steps, seed=seed, num_images=count
    )

def txt2img(prompt, **kw):  return generate(prompt, mode="txt2img", **kw)
def img2img(prompt, init_image, **kw):  return generate(prompt, mode="img2img", init_image=init_image, **kw)

# ─────────────────────────────────────────────────────────────────────────────
#  STEP 9 ── Launch
# ─────────────────────────────────────────────────────────────────────────────
print("""
╔════════════════════════════════════════════════════════════╗
║     ⚡ SanStudio AI Image Generator · Ready!              ║
╠════════════════════════════════════════════════════════════╣
║  Options:                                                  ║
║   1. launch_ui()          → Full ComfyUI-style panel       ║
║   2. quick_generate(...)  → Simple one-liner               ║
║   3. generate(...)        → Full control programmatic      ║
╚════════════════════════════════════════════════════════════╝
""")

# ── Auto-launch the UI ───────────────────────────────────────────────────────
launch_ui()
