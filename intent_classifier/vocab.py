"""
vocab.py — builds the word -> index mapping (the vocabulary) from phrases.txt
 
This is Step 1 from the plan: every unique word across all your example
phrases gets a fixed index number. The vocabulary size becomes the input
size of the neural network (one input neuron per known word).
"""
 
import re
 
 
def tokenize(phrase: str):
    """Lowercase and split into words, stripping punctuation."""
    # Normalize curly apostrophes (from IMEs/STT) so "don’t" matches "don't"
    return re.findall(r"[a-z']+", phrase.lower().replace("\u2019", "'"))
 
 
def build_vocab(phrases_file: str) -> dict:
    """
    Reads phrases.txt and returns {word: index}.
    Ignores 'INTENT:' header lines, reads only lines starting with '-'.
    """
    vocab = {}
    with open(phrases_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("INTENT:"):
                continue
            # A leading '- ' is optional — accept bare phrase lines too.
            if line.startswith("-"):
                line = line[1:].strip()
            for word in tokenize(line):
                if word not in vocab:
                    vocab[word] = len(vocab)
    return vocab
 
 
if __name__ == "__main__":
    vocab = build_vocab("data/phrases.txt")
    print(f"Vocabulary size: {len(vocab)}")
    print(vocab)