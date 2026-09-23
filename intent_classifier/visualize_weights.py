"""
visualize_weights.py — see what the network actually learned, as heatmaps.
 
Run this after train.py. It loads model_weights.npz and plots:
  1. W1 (input -> hidden) — which words drive which hidden neurons
  2. W2 (hidden -> output) — which hidden neurons drive which intent
 
Usage:
    python visualize_weights.py
"""
 
import json
import numpy as np
import matplotlib.pyplot as plt
 
data = np.load("model_weights.npz")
W1, W2 = data["W1"], data["W2"]
 
with open("vocab.json") as f:
    vocab = json.load(f)
with open("intents.json") as f:
    idx_to_intent = {int(k): v for k, v in json.load(f).items()}
 
words = list(vocab.keys())
intents = [idx_to_intent[i] for i in range(len(idx_to_intent))]
 
fig, axes = plt.subplots(1, 2, figsize=(16, 8))
 
# W1: vocab_size x hidden_size
im1 = axes[0].imshow(W1, aspect="auto", cmap="RdBu_r", vmin=-1, vmax=1)
axes[0].set_title("W1 — input words -> hidden neurons")
axes[0].set_xlabel("hidden neuron")
axes[0].set_ylabel("word")
axes[0].set_yticks(range(len(words)))
axes[0].set_yticklabels(words, fontsize=6)
fig.colorbar(im1, ax=axes[0], label="weight value")
 
# W2: hidden_size x num_intents
im2 = axes[1].imshow(W2, aspect="auto", cmap="RdBu_r", vmin=-1, vmax=1)
axes[1].set_title("W2 — hidden neurons -> intents")
axes[1].set_xlabel("intent")
axes[1].set_ylabel("hidden neuron")
axes[1].set_xticks(range(len(intents)))
axes[1].set_xticklabels(intents, rotation=45, ha="right")
fig.colorbar(im2, ax=axes[1], label="weight value")
 
plt.tight_layout()
plt.savefig("network_weights.png", dpi=150)
print("Saved network_weights.png — open it to see the heatmaps")
plt.show()