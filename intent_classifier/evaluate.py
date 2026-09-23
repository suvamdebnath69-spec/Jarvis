"""
evaluate.py — honest benchmark of the intent network on N held-out phrases.

Protocol (default N=150):
  1. Split phrases.txt: N phrases held out as a test set, rest for training.
  2. Train a fresh network on the training portion (same hyperparameters as
     train.py) so no test phrase was ever seen during training.
  3. Run every test phrase through the real pipeline (tokenize -> vectorize
     -> forward pass) and measure accuracy + inference efficiency.

Usage:
    python evaluate.py           # 150 test phrases
    python evaluate.py --n 300   # custom test size
"""

import argparse
import json
import os
import time

import numpy as np

from vocab import build_vocab, tokenize
from vectorize import build_dataset, get_intents, vectorize
from network import IntentNetwork
from train import split_train_val

PHRASES_FILE = "data/phrases.txt"
HIDDEN_SIZE = 64
EPOCHS = 3000
LEARNING_RATE = 0.2
SEED = 42


def confusion_matrix(y_true, y_pred, n_classes):
    m = np.zeros((n_classes, n_classes), dtype=int)
    for t, p in zip(y_true, y_pred):
        m[t, p] += 1
    return m


def accuracy_points(acc):
    """Up to 70 pts: raw test accuracy."""
    return 70.0 * acc


def f1_points(y_true, y_pred, n_classes):
    """Up to 20 pts: macro-averaged F1 (rewards balance across intents)."""
    f1s = []
    for c in range(n_classes):
        tp = np.sum((y_pred == c) & (y_true == c))
        fp = np.sum((y_pred == c) & (y_true != c))
        fn = np.sum((y_pred != c) & (y_true == c))
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1s.append(2 * prec * rec / (prec + rec) if prec + rec else 0.0)
    return 20.0 * float(np.mean(f1s)), f1s


def confidence_points(conf_correct, conf_wrong):
    """Up to 10 pts: calibration — right answers confident, wrong answers not."""
    gap = conf_correct - conf_wrong  # typically ~1.0 for a well-calibrated net
    return 10.0 * max(0.0, min(1.0, gap))


def latency_points(p50_ms):
    """Up to 35 pts: end-to-end classify latency."""
    if p50_ms <= 1.0:
        return 35.0
    if p50_ms <= 5.0:
        return 25.0
    if p50_ms <= 20.0:
        return 15.0
    return 5.0


def throughput_points(ex_per_sec):
    """Up to 25 pts: training throughput."""
    if ex_per_sec >= 2000:
        return 25.0
    if ex_per_sec >= 500:
        return 18.0
    return 10.0


def size_points(bytes_on_disk):
    """Up to 20 pts: model size on disk."""
    if bytes_on_disk <= 100_000:
        return 20.0
    if bytes_on_disk <= 500_000:
        return 12.0
    return 5.0


def flops_points(flops_per_inference):
    """Up to 20 pts: compute per inference."""
    if flops_per_inference <= 10_000:
        return 20.0
    if flops_per_inference <= 50_000:
        return 12.0
    return 5.0


def main():
    parser = argparse.ArgumentParser(description="Benchmark the intent network")
    parser.add_argument("--n", type=int, default=150, help="number of test phrases")
    args = parser.parse_args()
    n_test = args.n

    vocab = build_vocab(PHRASES_FILE)
    intent_to_idx = get_intents(PHRASES_FILE)
    idx_to_intent = {v: k for k, v in intent_to_idx.items()}
    n_classes = len(intent_to_idx)
    X, y = build_dataset(PHRASES_FILE, vocab, intent_to_idx)

    if n_test >= X.shape[0]:
        raise SystemExit(f"--n {n_test} exceeds dataset size {X.shape[0]}")

    # Step 1: carve out the test set (stratified), keep the rest for training.
    X_pool, y_pool, X_test, y_test, _, test_idx = split_train_val(
        X, y, val_fraction=n_test / X.shape[0], seed=SEED, return_indices=True
    )
    # split_train_val caps val at fraction of each class; if that doesn't
    # land on exactly N, fall back to a simple random holdout of exactly N.
    if len(y_test) != n_test:
        rng = np.random.default_rng(SEED)
        all_idx = rng.permutation(len(y))
        test_idx = all_idx[:n_test]
        train_mask = np.ones(len(y), dtype=bool)
        train_mask[test_idx] = False
        X_pool, y_pool = X[train_mask], y[train_mask]
        X_test, y_test = X[test_idx], y[test_idx]

    # Recover the raw phrase for each test row so errors are readable.
    data = None
    try:
        from vectorize import parse_phrases

        data = parse_phrases(PHRASES_FILE)
    except Exception:
        pass

    print(f"Vocabulary size: {len(vocab)}   Intents: {n_classes}")
    print(f"Dataset: {X.shape[0]} phrases  ->  train {len(y_pool)}  test {len(y_test)}")
    print("-" * 60)

    # Step 2: fresh network, trained only on the training portion.
    net = IntentNetwork(
        input_size=len(vocab), hidden_size=HIDDEN_SIZE, output_size=n_classes, seed=SEED
    )
    t0 = time.perf_counter()
    for epoch in range(EPOCHS):
        y_pred = net.forward(X_pool)
        net.backward(X_pool, y_pool, LEARNING_RATE)
        if epoch % 500 == 0:
            loss = net.compute_loss(y_pred, y_pool)
            print(f"  epoch {epoch:5d}  loss {loss:.4f}")
    train_secs = time.perf_counter() - t0
    print(f"Trained in {train_secs:.2f}s")
    print("-" * 60)

    # Step 3: run the full real-world pipeline on each test phrase.
    test_phrases = (
        [data[i][0] for i in test_idx] if data else [""] * len(y_test)
    )
    preds, confs, vec_times, fwd_times = [], [], [], []
    for i, phrase in enumerate(test_phrases):
        t0 = time.perf_counter()
        vec = vectorize(phrase, vocab).reshape(1, -1)
        t1 = time.perf_counter()
        probs = net.forward(vec)
        t2 = time.perf_counter()
        preds.append(int(np.argmax(probs[0])))
        confs.append(float(probs[0][preds[-1]]))
        vec_times.append(t1 - t0)
        fwd_times.append(t2 - t1)
    preds = np.array(preds)
    confs = np.array(confs)
    y_test = np.asarray(y_test)

    # ---------------- ACCURACY ----------------
    acc = float(np.mean(preds == y_test))
    correct = preds == y_test
    conf_correct = float(confs[correct].mean()) if correct.any() else 0.0
    conf_wrong = float(confs[~correct].mean()) if (~correct).any() else 0.0

    a_pts = accuracy_points(acc)
    f_pts, f1s = f1_points(y_test, preds, n_classes)
    c_pts = confidence_points(conf_correct, conf_wrong)
    accuracy_score = a_pts + f_pts + c_pts

    print("ACCURACY")
    print(f"  Test accuracy:        {acc:6.1%}  ({correct.sum()}/{len(y_test)})   -> {a_pts:5.1f} / 70 pts")
    print(f"  Macro F1:             {np.mean(f1s):6.1%}                       -> {f_pts:5.1f} / 20 pts")
    print(f"  Conf when correct:    {conf_correct:6.1%}")
    print(f"  Conf when wrong:      {conf_wrong:6.1%}                       -> {c_pts:5.1f} / 10 pts")
    print(f"  ACCURACY SCORE:       {accuracy_score:6.1f} / 100")
    print("-" * 60)

    print("PER-INTENT RECALL")
    for c in range(n_classes):
        m = y_test == c
        if m.sum():
            rec = np.mean(preds[m] == c)
            bar = "#" * int(round(rec * 20))
            print(f"  {idx_to_intent[c]:14} {m.sum():4} tests  recall {rec:6.1%}  {bar}")
    print("-" * 60)

    print("CONFUSIONS (true -> predicted, wrong only)")
    cm = confusion_matrix(y_test, preds, n_classes)
    any_err = False
    for t in range(n_classes):
        for p in range(n_classes):
            if t != p and cm[t, p]:
                any_err = True
                print(f"  {idx_to_intent[t]:14} -> {idx_to_intent[p]:14} x{cm[t, p]}")
    if not any_err:
        print("  none")
    print("-" * 60)

    print("MISCLASSIFIED EXAMPLES (up to 10)")
    shown = 0
    for i in np.flatnonzero(~correct):
        if shown >= 10:
            break
        phrase = test_phrases[i] or "(phrase text unavailable)"
        print(
            f'  "{phrase[:48]}"  expected {idx_to_intent[y_test[i]]},'
            f" got {idx_to_intent[preds[i]]} ({confs[i]:.0%})"
        )
        shown += 1
    if shown == 0:
        print("  none")
    print("-" * 60)

    # ---------------- EFFICIENCY ----------------
    # Steady-state latency over many repeats, then percentiles.
    reps = 400
    probe = test_phrases[0] or "open chrome"
    t_e2e = []
    for _ in range(reps):
        t0 = time.perf_counter()
        vec = vectorize(probe, vocab).reshape(1, -1)
        net.forward(vec)
        t_e2e.append((time.perf_counter() - t0) * 1000)
    p50, p95 = float(np.percentile(t_e2e, 50)), float(np.percentile(t_e2e, 95))

    # Pure forward-pass throughput (batched, the training-hot-path number).
    t0 = time.perf_counter()
    for _ in range(50):
        net.forward(X_pool)
    fwd_secs = (time.perf_counter() - t0) / 50
    train_ex_per_sec = len(y_pool) / (train_secs / EPOCHS)

    params = sum(p.size for p in (net.W1, net.b1, net.W2, net.b2))
    nnz = int(np.count_nonzero(vectorize(probe, vocab)))
    flops = 2 * (nnz * HIDDEN_SIZE + HIDDEN_SIZE * n_classes) + n_classes
    disk = os.path.getsize("model_weights.npz") if os.path.exists("model_weights.npz") else params * 8

    l_pts = latency_points(p50)
    th_pts = throughput_points(train_ex_per_sec)
    s_pts = size_points(disk)
    fl_pts = flops_points(flops)
    efficiency_score = l_pts + th_pts + s_pts + fl_pts

    print("EFFICIENCY")
    print(f"  Classify latency p50: {p50:8.3f} ms                      -> {l_pts:5.1f} / 35 pts")
    print(f"  Classify latency p95: {p95:8.3f} ms")
    print(f"  Train throughput:     {train_ex_per_sec:8.0f} ex/s               -> {th_pts:5.1f} / 25 pts")
    print(f"  Batched forward:      {X_pool.shape[0] / fwd_secs:8.0f} rows/s")
    print(f"  Parameters:           {params:8d}  ({disk / 1024:.1f} KB on disk)  -> {s_pts:5.1f} / 20 pts")
    print(f"  FLOPs / inference:    {flops:8d}  ({nnz} active words)     -> {fl_pts:5.1f} / 20 pts")
    print(f"  EFFICIENCY SCORE:     {efficiency_score:6.1f} / 100")
    print("=" * 60)
    print(
        f"FINAL  (N={len(y_test)} held-out phrases)   "
        f"accuracy {accuracy_score:5.1f}/100   efficiency {efficiency_score:5.1f}/100   "
        f"overall {(accuracy_score + efficiency_score) / 2:5.1f}/100"
    )


if __name__ == "__main__":
    main()
