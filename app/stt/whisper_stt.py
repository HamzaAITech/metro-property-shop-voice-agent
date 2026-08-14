import importlib.util
import os
import sys
from functools import lru_cache

from faster_whisper import WhisperModel

# "small" is a floor, not a preference: "tiny" and "base" were tested and both
# badly mangle Hindi (base even outputs Urdu script instead of Devanagari) -
# see tests/fixtures/stt_model_compare.txt. Since bilingual accuracy is core
# to this project, we eat the extra latency rather than downgrade.
MODEL_SIZE = "small"


def _register_cuda_dll_dirs() -> None:
    """Let ctranslate2 find cuBLAS/cuDNN from their pip packages instead of
    requiring a system-wide CUDA toolkit install."""
    if sys.platform != "win32":
        return
    # os.add_dll_directory() only affects loading of Python extension modules
    # (.pyd files) - it does NOT affect LoadLibrary calls made from inside an
    # already-loaded native extension (which is how ctranslate2 resolves its
    # own cuBLAS/cuDNN dependencies). Prepending to PATH is what actually works.
    bin_dirs = []
    for module_name in ("nvidia.cublas", "nvidia.cudnn"):
        spec = importlib.util.find_spec(module_name)
        if spec is None or not spec.submodule_search_locations:
            continue
        for location in spec.submodule_search_locations:
            bin_dir = os.path.join(location, "bin")
            if os.path.isdir(bin_dir):
                bin_dirs.append(bin_dir)
                os.add_dll_directory(bin_dir)
    if bin_dirs:
        os.environ["PATH"] = os.pathsep.join(bin_dirs) + os.pathsep + os.environ.get("PATH", "")


_register_cuda_dll_dirs()


def _load_model() -> WhisperModel:
    try:
        return WhisperModel(MODEL_SIZE, device="cuda", compute_type="float16")
    except Exception:
        # No GPU, or CUDA libs unavailable - CPU still works, just slower.
        return WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")


@lru_cache(maxsize=1)
def get_model() -> WhisperModel:
    return _load_model()


def transcribe(audio_path: str) -> tuple[str, str]:
    """Returns (transcript_text, detected_language_code)."""
    model = get_model()
    # beam_size=1 (greedy): ~20% faster than beam_size=5 with no meaningful
    # accuracy loss observed in testing - see tests/fixtures/stt_model_compare.txt.
    segments, info = model.transcribe(audio_path, beam_size=1)
    text = " ".join(segment.text.strip() for segment in segments)
    return text.strip(), info.language
