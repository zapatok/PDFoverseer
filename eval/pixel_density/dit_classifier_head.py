"""Tiny binary classifier head over frozen DiT embeddings.

Architecture: 768 -> 64 -> 1 MLP with ReLU + dropout.
Training:     BCEWithLogits + pos_weight to handle class imbalance.

Used by benchmark_dit_classifier_lofo.py for leave-one-fixture-out
evaluation. Lightweight enough to train per-fold in seconds on the
GTX 1080. Frozen DiT embeddings (cached) are the input; we never
backprop into DiT itself.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# torch is imported lazily inside functions so the module can be imported on
# CPU-only environments without crashing on the import line. The repo's
# CLAUDE.md guardrail "torch-try-except" expects this pattern.
try:
    import torch
    from torch import nn
except Exception:  # noqa: BLE001
    torch = None  # type: ignore[assignment]
    nn = None  # type: ignore[assignment]


EMBED_DIM = 768
HIDDEN_DIM = 64
DROPOUT = 0.3
DEFAULT_LR = 1e-3
DEFAULT_EPOCHS = 30
DEFAULT_BATCH_SIZE = 256


@dataclass
class TrainResult:
    final_loss: float
    epochs_run: int


def make_model() -> nn.Module:
    """Construct the 768 -> 64 -> 1 head."""
    if nn is None:
        raise RuntimeError("torch unavailable - cannot build classifier head")
    return nn.Sequential(
        nn.Linear(EMBED_DIM, HIDDEN_DIM),
        nn.ReLU(),
        nn.Dropout(DROPOUT),
        nn.Linear(HIDDEN_DIM, 1),
    )


def train_head(
    X_train: np.ndarray,
    y_train: np.ndarray,
    *,
    epochs: int = DEFAULT_EPOCHS,
    lr: float = DEFAULT_LR,
    batch_size: int = DEFAULT_BATCH_SIZE,
    device: str | None = None,
    seed: int = 0,
) -> tuple[nn.Module, TrainResult]:
    """Train a fresh classifier head.

    Args:
        X_train: (N, 768) float32 embeddings.
        y_train: (N,) {0, 1} labels (1 = cover page).
        epochs: gradient passes over the training set.
        lr: Adam learning rate.
        batch_size: minibatch size.
        device: 'cuda' or 'cpu'. Defaults to cuda if available.
        seed: torch RNG seed for reproducibility.

    Returns:
        (trained model in eval mode, TrainResult metadata).
    """
    if torch is None:
        raise RuntimeError("torch unavailable - cannot train")

    torch.manual_seed(seed)
    np.random.seed(seed)

    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"

    model = make_model().to(device)

    n_pos = float((y_train == 1).sum())
    n_neg = float((y_train == 0).sum())
    # Guard against degenerate folds (all-cover or all-non-cover training set).
    pos_weight = torch.tensor(
        [n_neg / max(n_pos, 1.0)],
        dtype=torch.float32,
        device=device,
    )
    criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)

    X = torch.from_numpy(X_train.astype(np.float32)).to(device)
    y = torch.from_numpy(y_train.astype(np.float32)).to(device)

    n = X.shape[0]
    final_loss = float("nan")
    model.train()
    for _epoch in range(epochs):
        perm = torch.randperm(n, device=device)
        epoch_loss = 0.0
        n_batches = 0
        for start in range(0, n, batch_size):
            idx = perm[start : start + batch_size]
            xb = X[idx]
            yb = y[idx]
            logits = model(xb).squeeze(-1)
            loss = criterion(logits, yb)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            epoch_loss += float(loss.item())
            n_batches += 1
        final_loss = epoch_loss / max(n_batches, 1)

    model.eval()
    return model, TrainResult(final_loss=final_loss, epochs_run=epochs)


def predict_proba(model: nn.Module, X: np.ndarray) -> np.ndarray:
    """Return per-row cover probability in [0, 1]."""
    if torch is None:
        raise RuntimeError("torch unavailable")
    device = next(model.parameters()).device
    Xt = torch.from_numpy(X.astype(np.float32)).to(device)
    with torch.no_grad():
        logits = model(Xt).squeeze(-1)
        probs = torch.sigmoid(logits).cpu().numpy()
    return probs.astype(np.float32)
