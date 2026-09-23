"""
export_globe_weights.py — publish the classifier's weights for the 3D globe.

Writes Ui/globe_weights.json (vocab + hidden-layer biases + top-K weight
edges per layer). The globe draws only the strongest connections, so we
export edges, not the full 774x64 matrix — keeps the JSON small and the
UI load instant.

Run after every retrain:  python export_globe_weights.py
"""

import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
IC = os.path.join(HERE, "intent_classifier")
UI = os.path.join(HERE, "Ui")

TOP_IN = 900    # strongest input->hidden edges to export
TOP_OUT = 150   # strongest hidden->output edges


def main():
    with open(os.path.join(IC, "vocab.json"), encoding="utf-8") as f:
        vocab = json.load(f)
    with open(os.path.join(IC, "intents.json"), encoding="utf-8") as f:
        intents = json.load(f)

    W = np.load(os.path.join(IC, "model_weights.npz"))
    W1, b1, W2, b2 = W["W1"], W["b1"], W["W2"], W["b2"]

    words = list(vocab.keys())

    def top_edges(mat, k):
        idx = np.dstack(np.unravel_index(np.argsort(-np.abs(mat), axis=None), mat.shape))[0][:k]
        return [
            {
                "i": int(i),
                "j": int(j),
                "w": round(float(mat[i, j]), 4),
            }
            for i, j in idx
        ]

    payload = {
        "words": words,
        "intents": [intents[k] for k in sorted(intents, key=lambda x: int(x))]
        if all(k.isdigit() for k in intents)
        else [intents[k] for k in sorted(intents)],
        "b1": [round(float(x), 4) for x in b1],
        "edges1": top_edges(W1, TOP_IN),
        "edges2": top_edges(W2, TOP_OUT),
    }

    out = os.path.join(UI, "globe_weights.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, separators=(",", ":"))
    print(f"wrote {out}: {len(words)} words, {len(payload['intents'])} intents, "
          f"{len(payload['edges1'])}+{len(payload['edges2'])} edges, "
          f"{os.path.getsize(out) // 1024} KB")


if __name__ == "__main__":
    main()
