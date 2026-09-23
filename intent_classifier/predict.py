"""
predict.py — load the trained model and classify a NEW phrase (one it has
never seen). This is the real test of whether it learned the pattern.

Usage:
    python predict.py "please open discord for me"
"""

import sys
import json
import numpy as np

from vectorize import vectorize
from network import IntentNetwork

with open("vocab.json") as f:
    vocab = json.load(f)
with open("intents.json") as f:
    idx_to_intent = {int(k): v for k, v in json.load(f).items()}

net = IntentNetwork.load(
    "model_weights.npz",
    input_size=len(vocab),
    hidden_size=HIDDEN_SIZE,
    output_size=len(idx_to_intent),
)


def classify(phrase: str):
    vec = vectorize(phrase, vocab).reshape(1, -1)
    pred_idx, probs = net.predict(vec)
    intent = idx_to_intent[int(pred_idx[0])]
    confidence = probs[0][pred_idx[0]]
    return intent, confidence


if __name__ == "__main__":
    phrase = " ".join(sys.argv[1:]) or "open discord please"
    intent, confidence = classify(phrase)
    print(f'"{phrase}" -> {intent}  (confidence: {confidence:.2%})')