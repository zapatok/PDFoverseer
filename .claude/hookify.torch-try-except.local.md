---
name: torch-try-except
enabled: true
event: file
action: warn
pattern: ^import torch|^from torch
---

**Bare `import torch` detected.**

Wrap torch imports in try/except for CPU fallback:
```python
try:
    import torch
except ImportError:
    torch = None
```
This project must work without CUDA/PyTorch installed.
