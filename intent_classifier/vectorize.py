"""
vectorize.py — turns phrases into bag-of-words vectors (Step 2 + 3 from the plan)
 
parse_phrases()   reads phrases.txt into a list of (phrase, intent_name) pairs
vectorize()       turns ONE phrase into a fixed-length 0/1 vector
build_dataset()   turns ALL phrases into the (X, y) arrays the network trains on
"""
 
import numpy as np
from vocab import tokenize
 
 
def parse_phrases(phrases_file: str):
    """Returns a list of (phrase, intent_name) tuples."""
    data = []
    current_intent = None
    with open(phrases_file, "r", encoding="utf-8") as f:
        for line_no, raw_line in enumerate(f, 1):
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("INTENT:"):
                current_intent = line.split("INTENT:")[1].strip()
                if not current_intent:
                    raise ValueError(
                        f"{phrases_file}:{line_no}: empty INTENT: name"
                    )
            elif current_intent is None:
                raise ValueError(
                    f"{phrases_file}:{line_no}: phrase before any INTENT: header"
                )
            else:
                # A leading '- ' is optional — accept bare phrase lines too.
                if line.startswith("-"):
                    line = line[1:].strip()
                data.append((line, current_intent))
    if not data:
        raise ValueError(
            f"{phrases_file}: no phrases found. Expected 'INTENT: <NAME>'"
            " headers followed by phrase lines (a leading '- ' is optional)."
        )
    return data
 
 
def vectorize(phrase: str, vocab: dict) -> np.ndarray:
    """Bag-of-words: 1 if the word is present in the phrase, else 0."""
    vec = np.zeros(len(vocab))
    for word in tokenize(phrase):
        if word in vocab:
            vec[vocab[word]] = 1.0
    return vec
 
 
def build_dataset(phrases_file: str, vocab: dict, intent_to_idx: dict):
    """
    Returns:
        X: (num_examples, vocab_size) array of bag-of-words vectors
        y: (num_examples,) array of integer intent labels
    """
    data = parse_phrases(phrases_file)
    X = np.array([vectorize(phrase, vocab) for phrase, _ in data])
    y = np.array([intent_to_idx[intent] for _, intent in data])
    return X, y
 
 
def get_intents(phrases_file: str) -> dict:
    """Scans the file for every unique INTENT: name, returns {name: index}."""
    intents = []
    seen = set()
    with open(phrases_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("INTENT:"):
                name = line.split("INTENT:")[1].strip()
                if name and name not in seen:
                    seen.add(name)
                    intents.append(name)
    if not intents:
        raise ValueError(f"{phrases_file}: no INTENT: headers found")
    return {name: i for i, name in enumerate(intents)}
