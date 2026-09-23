"""
train.py — trains on 80% of phrases.txt, validates on the held-out 20%.
 
Why this matters: training accuracy alone doesn't prove the network
generalizes — it could just be memorizing. Validation accuracy is
measured on examples the network never saw during training, so it's
the honest signal of whether it actually learned the pattern.
 
Run this whenever you edit data/phrases.txt.
"""
 
import json
import os
import numpy as np
 
from vocab import build_vocab
from vectorize import build_dataset, get_intents
from network import IntentNetwork
 
PHRASES_FILE = "data/phrases.txt"
HIDDEN_SIZE = 64
EPOCHS = 3000
LEARNING_RATE = 0.2
VAL_FRACTION = 0.2
SEED = 42
 
 
def split_train_val(X, y, val_fraction=0.2, seed=42, return_indices=False):
    X = np.asarray(X)
    y = np.asarray(y)

    if X.shape[0] == 0:
        raise ValueError(
            "No training examples found — check that the phrase parser "
            "actually extracted phrases from the data file."
        )

    # Make sure labels are 1D integer class IDs
    if y.ndim > 1:
        if y.shape[1] == 1:
            y = y.ravel()
        else:
            y = np.argmax(y, axis=1)

    rng = np.random.default_rng(seed)

    train_parts = []
    val_parts = []

    for intent in np.unique(y):
        idx = np.flatnonzero(y == intent).astype(np.int64)
        rng.shuffle(idx)

        if len(idx) <= 1:
            n_val = 0
        else:
            n_val = max(1, int(len(idx) * val_fraction))
            n_val = min(n_val, len(idx) - 1)

        val_parts.append(idx[:n_val])
        train_parts.append(idx[n_val:])

    train_idx = np.concatenate(train_parts).astype(np.int64)
    val_idx = np.concatenate(val_parts).astype(np.int64)

    rng.shuffle(train_idx)
    rng.shuffle(val_idx)

    if return_indices:
        return X[train_idx], y[train_idx], X[val_idx], y[val_idx], train_idx, val_idx
    return X[train_idx], y[train_idx], X[val_idx], y[val_idx]
 
 
if __name__ == "__main__":
    # Stale artifacts from a previous run must not survive a retrain: old
    # weights + old vocab silently poison predict.py against the new data.
    for stale in ("model_weights.npz", "model_weights.npy"):
        if os.path.exists(stale):
            os.remove(stale)

    vocab = build_vocab(PHRASES_FILE)
    intent_to_idx = get_intents(PHRASES_FILE)
    idx_to_intent = {v: k for k, v in intent_to_idx.items()}
 
    X, y = build_dataset(PHRASES_FILE, vocab, intent_to_idx)
    X_train, y_train, X_val, y_val = split_train_val(X, y, VAL_FRACTION, SEED)
 
    print(f"Vocabulary size: {len(vocab)}")
    print(f"Intents: {list(intent_to_idx.keys())}")
    print(f"Total examples: {X.shape[0]}  ->  train: {X_train.shape[0]}  val: {X_val.shape[0]}")
    print("-" * 40)
 
    net = IntentNetwork(
        input_size=len(vocab),
        hidden_size=HIDDEN_SIZE,
        output_size=len(intent_to_idx),
    )
 
    # train only on the training split — validation set stays untouched
    for epoch in range(EPOCHS):
        y_pred = net.forward(X_train)
        train_loss = net.compute_loss(y_pred, y_train)
        net.backward(X_train, y_train, LEARNING_RATE) 
        if epoch % 200 == 0:
            train_acc = np.mean(np.argmax(y_pred, axis=1) == y_train)
            val_preds, val_probs = net.predict(X_val)
            val_acc = np.mean(val_preds == y_val)
            val_loss = net.compute_loss(val_probs, y_val)
            print(
                f"epoch {epoch:5d}  "
                f"train_loss {train_loss:.4f}  train_acc {train_acc:.2f}  |  "
                f"val_loss {val_loss:.4f}  val_acc {val_acc:.2f}"
            )
 
    net.save("model_weights.npz")
    with open("vocab.json", "w") as f:
        json.dump(vocab, f)
    with open("intents.json", "w") as f:
        json.dump(idx_to_intent, f)
 
    print("-" * 40)
    print("Saved model_weights.npz, vocab.json, intents.json")
 
    # final honest numbers
    train_preds, _ = net.predict(X_train)
    val_preds, _ = net.predict(X_val)
    train_acc = np.mean(train_preds == y_train)
    val_acc = np.mean(val_preds == y_val)
    print(f"Final training accuracy:   {train_acc:.2%}")
    print(f"Final validation accuracy: {val_acc:.2%}")
 
    if train_acc - val_acc > 0.15:
        print(
            "\nWarning: training accuracy is much higher than validation accuracy.\n"
            "That's a sign of overfitting — the network may be memorizing your\n"
            "training phrases rather than generalizing. Try adding more and more\n"
            "varied example phrases per intent."
        )
