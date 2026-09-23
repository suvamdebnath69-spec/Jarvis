"""
network.py — the neural network. Same mechanics as your AND neuron and the
XOR network, just wider: one hidden layer (ReLU) + one output layer (softmax).
 
Architecture:
    input (vocab_size) -> hidden (hidden_size, ReLU) -> output (num_intents, softmax)
 
No frameworks — every gradient is computed by hand with NumPy, matching the
paper math you worked through.
"""
 
import numpy as np
 
 
class IntentNetwork:
    def __init__(self, input_size: int, hidden_size: int, output_size: int, seed: int = 42):
        rng = np.random.default_rng(seed)
        # Small random starting weights — same idea as picking w1=0.5, w2=0.5 by hand,
        # just automated and scaled to every connection in the network.
        self.W1 = rng.normal(0, 0.5, (input_size, hidden_size))
        self.b1 = np.zeros(hidden_size)
        self.W2 = rng.normal(0, 0.5, (hidden_size, output_size))
        self.b2 = np.zeros(output_size)
 
    # ---- activations ----
    @staticmethod
    def relu(z):
        return np.maximum(0, z)
 
    @staticmethod
    def relu_derivative(z):
        return (z > 0).astype(float)
 
    @staticmethod
    def softmax(z):
        z = z - np.max(z, axis=-1, keepdims=True)  # numerical stability
        e = np.exp(z)
        return e / np.sum(e, axis=-1, keepdims=True)
 
    # ---- forward pass ----
    def forward(self, X):
        self.z1 = X @ self.W1 + self.b1
        self.a1 = self.relu(self.z1)
        self.z2 = self.a1 @ self.W2 + self.b2
        self.a2 = self.softmax(self.z2)
        return self.a2
 
    # ---- loss ----
    def compute_loss(self, y_pred, y_true_idx):
        n = y_pred.shape[0]
        correct_probs = y_pred[np.arange(n), y_true_idx]
        return np.sum(-np.log(correct_probs + 1e-9)) / n
 
    # ---- backward pass (backprop) ----
    def backward(self, X, y_true_idx, learning_rate=0.1):
        n = X.shape[0]
        y_onehot = np.zeros_like(self.a2)
        y_onehot[np.arange(n), y_true_idx] = 1
 
        # Softmax + cross-entropy gradient simplifies to (prediction - actual)
        dz2 = (self.a2 - y_onehot) / n
        dW2 = self.a1.T @ dz2
        db2 = np.sum(dz2, axis=0)
 
        da1 = dz2 @ self.W2.T
        dz1 = da1 * self.relu_derivative(self.z1)
        dW1 = X.T @ dz1
        db1 = np.sum(dz1, axis=0)
 
        self.W1 -= learning_rate * dW1
        self.b1 -= learning_rate * db1
        self.W2 -= learning_rate * dW2
        self.b2 -= learning_rate * db2
 
    # ---- training loop ----
    def train(self, X, y_idx, epochs=2000, learning_rate=0.1, verbose=True):
        for epoch in range(epochs):
            y_pred = self.forward(X)
            loss = self.compute_loss(y_pred, y_idx)
            self.backward(X, y_idx, learning_rate)
            if verbose and epoch % 200 == 0:
                acc = np.mean(np.argmax(y_pred, axis=1) == y_idx)
                print(f"epoch {epoch:5d}  loss {loss:.4f}  acc {acc:.2f}")
 
    # ---- inference ----
    def predict(self, X):
        probs = self.forward(X)
        return np.argmax(probs, axis=1), probs
 
    # ---- persistence ----
    def save(self, path):
        np.savez(path, W1=self.W1, b1=self.b1, W2=self.W2, b2=self.b2)
 
    @classmethod
    def load(cls, path, input_size=None, hidden_size=None, output_size=None):
        """
        Load weights saved by train(). Sizes are inferred from the checkpoint
        itself; passing explicit sizes only runs a consistency check, so a
        stale/mismatched checkpoint fails loudly instead of breaking forward().
        """
        data = np.load(path)
        W1, b1 = data["W1"], data["b1"]
        W2, b2 = data["W2"], data["b2"]

        inferred = (W1.shape[0], W1.shape[1], W2.shape[1])
        expected = (input_size, hidden_size, output_size)
        if any(e is not None and e != i for e, i in zip(expected, inferred)):
            raise ValueError(
                f"Checkpoint {path} has shapes {inferred} (input, hidden, "
                f"output) but sizes {expected} were requested — the model was "
                "trained with a different vocab/intent set. Re-run train.py."
            )

        net = cls(*inferred)
        net.W1, net.b1 = W1, b1
        net.W2, net.b2 = W2, b2
        return net
