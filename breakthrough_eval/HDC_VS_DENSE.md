# HDC versus dense representations

No matched downstream HDC-versus-dense result currently exists. Frozen provider experiments test
binary index backends and synthetic vector geometry; they do not hold a real semantic interpreter,
governance policy, assistant task, and candidate pool fixed while swapping HDC and dense heads.

The available infrastructure evidence supports only an efficiency statement: at tested binary
geometries, FAISS BinaryMultiHash is fast at 100K/1M, while FAISS BinaryIVF is faster than the HNG
index at matched 10M top-1 agreement. This says nothing about whether HDC semantics improve
assistant behavior or compositional state representation.

The required experiment needs a real semantic source (or a legitimately trained matched pair),
identical governance, equal memory/compute budgets, matched recall, and downstream tasks. Synthetic
random vectors cannot satisfy the real HDC gate. HDC is therefore neither protected nor dismissed;
its claimed cognitive advantage is `UNPROVEN`.
