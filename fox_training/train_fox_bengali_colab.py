# ==============================================================================
# FOX-MECHA Qwen2.5-0.5B Bengali & C-Router Fine-Tuning Script for Google Colab
# Speed: ~3-5 minutes on Colab Free T4 GPU using Unsloth
# ==============================================================================

# 1. Install Unsloth and dependencies (Run in Colab cell):
# !pip install "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"
# !pip install --no-deps "xformers<0.0.27" "trl<0.9.0" peft accelerate bitsandbytes

import torch
from unsloth import FastLanguageModel
from datasets import load_dataset
from trl import SFTTrainer
from transformers import TrainingArguments

max_seq_length = 512
dtype = None # Auto detect (Float16 for T4)
load_in_4bit = True # 4bit quantization for fast training & low VRAM

print("Loading Base Qwen2.5-0.5B-Instruct...")
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name = "Qwen/Qwen2.5-0.5B-Instruct",
    max_seq_length = max_seq_length,
    dtype = dtype,
    load_in_4bit = load_in_4bit,
)

# Apply LoRA adapters
model = FastLanguageModel.get_peft_model(
    model,
    r = 16,
    target_modules = ["q_proj", "k_proj", "v_proj", "o_proj",
                      "gate_proj", "up_proj", "down_proj"],
    lora_alpha = 16,
    lora_dropout = 0,
    bias = "none",
    use_gradient_checkpointing = "unsloth",
    random_state = 3407,
)

# Prepare Dataset
dataset = load_dataset("json", data_files="fox_bengali_dataset.jsonl", split="train")

def formatting_prompts_func(examples):
    convos = examples["messages"]
    texts = [tokenizer.apply_chat_template(convo, tokenize=False, add_generation_prompt=False) for convo in convos]
    return { "text" : texts }

dataset = dataset.map(formatting_prompts_func, batched = True)

# SFT Trainer
trainer = SFTTrainer(
    model = model,
    tokenizer = tokenizer,
    train_dataset = dataset,
    dataset_text_field = "text",
    max_seq_length = max_seq_length,
    dataset_num_proc = 2,
    packing = False,
    args = TrainingArguments(
        per_device_train_batch_size = 2,
        gradient_accumulation_steps = 4,
        warmup_steps = 5,
        max_steps = 60, # ~2-3 epochs over 238 items
        learning_rate = 2e-4,
        fp16 = not torch.cuda.is_bf16_supported(),
        bf16 = torch.cuda.is_bf16_supported(),
        logging_steps = 5,
        optim = "adamw_8bit",
        weight_decay = 0.01,
        lr_scheduler_type = "linear",
        seed = 3407,
        output_dir = "outputs",
    ),
)

print("Starting Fine-Tuning...")
trainer.train()

# Export to GGUF (Ready for Termux llama-server on port 8327)
print("Exporting trained Fox-Mecha to GGUF format...")
model.save_pretrained_gguf("fox_mecha_qwen05b_bengali", tokenizer, quantization_method = "q4_k_m")
print("Done! Download fox_mecha_qwen05b_bengali-q4_k_m.gguf to Termux!")
