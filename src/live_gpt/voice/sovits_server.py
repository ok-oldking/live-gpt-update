"""Small standalone GPT-SoVITS streaming server copied into an installation.

This file intentionally only imports GPT-SoVITS/runtime dependencies so it can
be launched by the installation's embedded Python rather than LiveAI's Python.
"""
from __future__ import annotations

import argparse
import json
import os
import struct
import sys
import threading
import time
import traceback

import anyio
import numpy as np
import torch
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool
import uvicorn


ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "GPT_SoVITS"))

parser = argparse.ArgumentParser()
parser.add_argument("--host", default="127.0.0.1")
parser.add_argument("--port", type=int, required=True)
parser.add_argument(
    "--config", default="GPT_SoVITS/configs/tts_infer.yaml"
)
parser.add_argument("--ckpt", default="")
parser.add_argument("--pth", default="")
parser.add_argument("--gpu", type=int, default=0)
parser.add_argument("--ref-audio", default="")
parser.add_argument("--prompt-text", default="")
parser.add_argument("--prompt-lang", default="auto")
parser.add_argument("--text-lang", default="auto")
args = parser.parse_args()
if not torch.version.cuda or getattr(torch.version, "hip", None) or not torch.cuda.is_available():
    raise RuntimeError("GPT-SoVITS requires an NVIDIA GPU and a CUDA-enabled PyTorch runtime. CPU fallback is disabled.")
if args.gpu < 0 or args.gpu >= torch.cuda.device_count():
    raise RuntimeError(f"NVIDIA GPU {args.gpu} is unavailable; detected {torch.cuda.device_count()} CUDA GPU(s). CPU fallback is disabled.")
torch.cuda.set_device(args.gpu)
gpu_name = torch.cuda.get_device_name(args.gpu)
print(f"GPT-SoVITS using NVIDIA GPU {args.gpu}: {gpu_name} (CUDA, FP16)", flush=True)
if bool(args.ckpt) != bool(args.pth):
    parser.error("--ckpt and --pth must both be supplied or both omitted")
for value, extension in ((args.ckpt, ".ckpt"), (args.pth, ".pth")):
    if value and (not value.lower().endswith(extension) or not os.path.isfile(value)):
        parser.error(f"Expected an existing {extension} model file: {value}")

# Construction loads and retains all model weights. TTS itself retains the
# semantic prompt and reference spectrogram when the same reference is reused.
from GPT_SoVITS.TTS_infer_pack.TTS import TTS, TTS_Config  # noqa: E402


config = TTS_Config(args.config)
config.device = torch.device(f"cuda:{args.gpu}")
config.is_half = True
if args.ckpt:
    config.t2s_weights_path = os.path.abspath(args.ckpt)
    config.vits_weights_path = os.path.abspath(args.pth)
pipeline = TTS(config)
pipeline_lock = threading.Lock()
app = FastAPI()
pipeline_ready = False


def _warm_pipeline():
    """Finish lazy pronunciation and CUDA initialization before accepting speech."""
    global pipeline_ready
    pipeline_ready = False
    started = time.perf_counter()
    print("GPT-SoVITS warming pronunciation models and voice; first startup may take several minutes", flush=True)
    language = args.text_lang
    samples = {
        "zh": "这是语音测试。", "yue": "呢個係語音測試。",
        "en": "This is a voice test.", "ja": "これは音声テストです。",
        "ko": "음성 테스트입니다.",
    }
    text = samples.get(language.removeprefix("all_"), samples["zh"])
    with pipeline_lock:
        if args.ref_audio:
            # Consume a complete, silent test synthesis so both reference caches
            # and the first ONNX/CUDA inference are ready for real playback.
            produced_audio = False
            for _rate, audio in pipeline.run({
                "text": text, "text_lang": language,
                "ref_audio_path": os.path.abspath(args.ref_audio),
                "prompt_text": args.prompt_text, "prompt_lang": args.prompt_lang,
                "text_split_method": "cut5", "return_fragment": True,
                "parallel_infer": False, "fragment_interval": 0.15,
            }):
                produced_audio = produced_audio or bool(np.any(audio))
            if not produced_audio:
                raise RuntimeError("GPT-SoVITS voice warmup generated no audio")
        else:
            pipeline.text_preprocessor.segment_and_extract_feature_for_text(
                text, language, pipeline.configs.version
            )
        torch.cuda.synchronize()
    pipeline_ready = True
    print(f"GPT-SoVITS voice warmup finished in {time.perf_counter() - started:.1f} s", flush=True)


@app.get("/health")
def health():
    return {"ready": pipeline_ready, "version": pipeline.configs.version,
            "device": str(pipeline.configs.device), "gpu_name": gpu_name,
            "is_half": pipeline.configs.is_half}


def _frames(payload: dict):
    # GPU inference is serialized because the shared pipeline and its prompt
    # cache are mutable. The lock remains held for the lifetime of the stream.
    try:
        with pipeline_lock:
            for sample_rate, samples in pipeline.run(payload):
                pcm = np.asarray(samples, dtype="<i2").reshape(-1).tobytes()
                yield struct.pack("!II", int(sample_rate), len(pcm)) + pcm
    except Exception as error:
        # StreamingResponse has already sent HTTP 200. Send the failure in
        # the frame protocol so the client can display the actual exception.
        traceback.print_exc()
        detail = json.dumps({"message": str(error)}).encode("utf-8")
        yield struct.pack("!II", 0, len(detail)) + detail


class _SynthesisResponse(StreamingResponse):
    """Release the shared pipeline even when an audio client disconnects."""

    def __init__(self, frames):
        self.frames = frames
        super().__init__(frames, media_type="application/octet-stream")

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            with anyio.CancelScope(shield=True):
                await run_in_threadpool(self.frames.close)


@app.post("/tts")
async def tts(request: Request):
    try:
        payload = await request.json()
        text = str(payload.get("text", "")).strip()
        text_lang = str(payload.get("text_lang", "")).lower()
        ref_audio = str(payload.get("ref_audio_path", "")).strip()
        prompt_text = str(payload.get("prompt_text", "")).strip()
        prompt_lang = str(payload.get("prompt_lang", "")).lower()
        if not text:
            raise ValueError("text is required")
        if text_lang not in pipeline.configs.languages:
            raise ValueError(f"unsupported text_lang: {text_lang}")
        if not ref_audio or not os.path.isfile(ref_audio):
            raise ValueError("ref_audio_path must be an existing audio file")
        if prompt_text and prompt_lang not in pipeline.configs.languages:
            raise ValueError(f"unsupported prompt_lang: {prompt_lang}")
        payload.update(
            text=text,
            text_lang=text_lang,
            ref_audio_path=os.path.abspath(ref_audio),
            prompt_text=prompt_text,
            prompt_lang=prompt_lang if prompt_text else text_lang,
            return_fragment=True,
            parallel_infer=False,
        )
        return _SynthesisResponse(_frames(payload))
    except Exception as error:
        return JSONResponse(status_code=400, content={"message": str(error)})


if __name__ == "__main__":
    _warm_pipeline()
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
