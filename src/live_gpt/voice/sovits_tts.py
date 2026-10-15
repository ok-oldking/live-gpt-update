from __future__ import annotations

import atexit
import json
import os
import shutil
import socket
import struct
import subprocess
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from collections.abc import Iterable
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from ..logger import Logger


logger = Logger.get_logger(__name__)


SOVITS_LANGUAGES = (
    "auto", "auto_yue", "zh", "en", "ja", "yue", "ko",
    "all_zh", "all_ja", "all_yue", "all_ko",
)


class SovitsTtsProvider:
    """Run an existing GPT-SoVITS installation through its embedded Python."""

    display_name = "GPT-SoVITS"
    continuous_audio_stream = True
    stream_prebuffer_seconds = 0.25
    audio_timeout_seconds = 30.0
    startup_timeout_seconds = 240.0

    def __init__(self) -> None:
        self.prompt_text = ""
        self.prompt_lang = "auto"
        self.ref_audio_path = ""
        self.text_lang = "auto"
        self._server_voice: tuple[str, str, str, str] | None = None
        self._weights = ("", "")
        self._server_weights: tuple[str, str] | None = None
        self.gpu_index = 0
        self._server_gpu_index: int | None = None
        self._server_device = ""
        self._process: subprocess.Popen[bytes] | None = None
        self._installation: Path | None = None
        self._server_installation: Path | None = None
        self._port: int | None = None
        self._lock = threading.RLock()
        self._server_output: deque[str] = deque(maxlen=40)
        self._server_output_thread: threading.Thread | None = None
        atexit.register(self.close)

    @staticmethod
    def validate_weights(ckpt_path: str, pth_path: str) -> tuple[str, str]:
        paths = (ckpt_path.strip(), pth_path.strip())
        if bool(paths[0]) != bool(paths[1]):
            raise ValueError("Select both the .ckpt and .pth model files, or leave both blank")
        if not paths[0]:
            return "", ""
        resolved = []
        for value, extension in zip(paths, (".ckpt", ".pth")):
            path = Path(value).expanduser().resolve()
            if path.suffix.lower() != extension:
                raise ValueError(f"Expected a {extension} model file: {value}")
            if not path.is_file():
                raise ValueError(f"Model file does not exist: {value}")
            resolved.append(str(path))
        return resolved[0], resolved[1]

    def configure(self, prompt_text: str = "", prompt_lang: str = "auto",
                  ckpt_path: str = "", pth_path: str = "", gpu_index: int = 0,
                  ref_audio_path: str = "", text_lang: str = "auto") -> None:
        weights = self.validate_weights(ckpt_path, pth_path)
        if type(gpu_index) is not int or gpu_index < 0:
            raise ValueError("Choose a valid NVIDIA GPU index (0 or greater)")
        self.gpu_index = gpu_index
        self.prompt_text = prompt_text.strip()
        self.prompt_lang = prompt_lang.lower()
        self.ref_audio_path = ref_audio_path.strip()
        self.text_lang = text_lang.lower()
        # Update the pair together without blocking the UI on server warmup.
        self._weights = weights

    @property
    def ckpt_path(self) -> str:
        return self._weights[0]

    @property
    def pth_path(self) -> str:
        return self._weights[1]

    @staticmethod
    def _paths(installation: str | Path) -> tuple[Path, Path, Path]:
        root = Path(installation).expanduser().resolve()
        python = root / "runtime" / "python.exe"
        config = root / "GPT_SoVITS" / "configs" / "tts_infer.yaml"
        return root, python, config

    def dependency_status(self) -> tuple[bool, str]:
        if self._installation is None:
            return False, "Choose an existing GPT-SoVITS installation folder"
        root, python, config = self._paths(self._installation)
        missing = [str(path) for path in (python, config) if not path.is_file()]
        if missing:
            return False, "Missing GPT-SoVITS file: " + missing[0]
        return True, f"Embedded runtime found in {root}"

    def install_dependencies(self, *args: Any, **kwargs: Any) -> str:
        raise RuntimeError("GPT-SoVITS must already be installed; choose its folder")

    def download_model(self, *args: Any, **kwargs: Any) -> str:
        raise RuntimeError("GPT-SoVITS models are managed by its installation")

    def model_status(self, model_type: str, model_key: str) -> tuple[bool, str]:
        if model_type != "tts":
            return False, "GPT-SoVITS only provides text to speech"
        self._installation = Path(model_key).expanduser() if model_key else None
        ok, message = self.dependency_status()
        return ok, message if not ok else "GPT-SoVITS model configuration is available"

    @staticmethod
    def _free_port() -> int:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    def _health(self, timeout: float = 1.0) -> dict[str, Any]:
        assert self._port is not None
        with urllib.request.urlopen(
            f"http://127.0.0.1:{self._port}/health", timeout=timeout
        ) as response:
            return json.loads(response.read())

    def preload(self, model_key: str) -> str:
        started = time.perf_counter()
        self._ensure_server(model_key)
        message = f"GPT-SoVITS server warmed in {time.perf_counter() - started:.1f} s"
        return f"{message} · {self._server_device}" if self._server_device else message

    @staticmethod
    def nvidia_gpus() -> list[tuple[int, str]]:
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=index,name", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5, check=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            devices = []
            for line in result.stdout.splitlines():
                index, name = line.split(",", 1)
                devices.append((int(index.strip()), name.strip()))
            return sorted(devices)
        except (OSError, subprocess.SubprocessError, ValueError):
            return []

    def _capture_server_output(self, process: subprocess.Popen[bytes]) -> None:
        output = process.stdout
        if output is None:
            return
        try:
            for raw_line in output:
                line = raw_line.decode("utf-8", errors="replace").rstrip()
                self._server_output.append(line)
                logger.debug(f"GPT-SoVITS: {line}")
        finally:
            output.close()

    def _server_error(self, message: str) -> str:
        detail = "\n".join(list(self._server_output)[-12:]).strip()
        return f"{message}\n{detail[-4000:]}" if detail else message

    def _ensure_server(self, installation: str, *, speaker: str | None = None,
                       language: str | None = None) -> None:
        root, python, config = self._paths(installation)
        with self._lock:
            weights = self.validate_weights(*self._weights)
            voice = (self.ref_audio_path if speaker is None else speaker,
                     self.prompt_text, self.prompt_lang,
                     self.text_lang if language is None else language)
            if (
                self._process is not None
                and self._process.poll() is None
                and self._server_installation == root
                and self._server_weights == weights
                and self._server_gpu_index == self.gpu_index
                and self._server_voice == voice
            ):
                self._health()
                return
            self.close()
            self._installation = root
            ok, message = self.dependency_status()
            if not ok:
                raise RuntimeError(message)
            source = Path(__file__).with_name("sovits_server.py")
            destination = root / "sovits_server.py"
            shutil.copy2(source, destination)
            self._port = self._free_port()
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            command = [
                    str(python), "-u", str(destination), "--port", str(self._port),
                    "--config", str(config),
                    "--gpu", str(self.gpu_index),
                    "--ref-audio", voice[0], "--prompt-text", voice[1],
                    "--prompt-lang", voice[2], "--text-lang", voice[3],
                ]
            if weights[0]:
                command.extend(["--ckpt", weights[0], "--pth", weights[1]])
            self._server_output.clear()
            logger.info(f"Starting GPT-SoVITS server in {root}")
            environment = {**os.environ, "PYTHONIOENCODING": "utf-8", "CUDA_DEVICE_ORDER": "PCI_BUS_ID"}
            environment.pop("CUDA_VISIBLE_DEVICES", None)
            self._process = subprocess.Popen(
                command,
                cwd=root,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                creationflags=creationflags,
                env=environment,
            )
            self._server_output_thread = threading.Thread(
                target=self._capture_server_output,
                args=(self._process,),
                name="sovits-server-output",
                daemon=True,
            )
            self._server_output_thread.start()
            self._server_installation = root
            self._server_weights = weights
            self._server_gpu_index = self.gpu_index
            self._server_voice = voice
            deadline = time.monotonic() + self.startup_timeout_seconds
            while time.monotonic() < deadline:
                if self._process.poll() is not None:
                    self._server_output_thread.join(timeout=1)
                    message = self._server_error(
                        f"GPT-SoVITS server exited with code {self._process.returncode}"
                    )
                    self.close()
                    raise RuntimeError(message)
                try:
                    health = self._health()
                    if health.get("ready"):
                        self._server_device = f"{health.get('device', f'cuda:{self.gpu_index}')} · {health.get('gpu_name', 'NVIDIA GPU')}"
                        logger.info(f"GPT-SoVITS server is ready on {self._server_device}")
                        return
                except (OSError, ValueError, urllib.error.URLError):
                    pass
                time.sleep(0.25)
            self.close()
            raise TimeoutError(self._server_error(
                f"GPT-SoVITS voice warmup timed out after {self.startup_timeout_seconds:g} seconds"
            ))

    def close(self) -> None:
        process = self._process
        self._process = None
        self._port = None
        self._server_installation = None
        self._server_weights = None
        self._server_gpu_index = None
        self._server_voice = None
        self._server_device = ""
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        output_thread = self._server_output_thread
        self._server_output_thread = None
        if output_thread is not None:
            output_thread.join(timeout=1)

    @staticmethod
    def _read_exact(response: Any, size: int) -> bytes:
        chunks = bytearray()
        while len(chunks) < size:
            part = response.read(size - len(chunks))
            if not part:
                break
            chunks.extend(part)
        return bytes(chunks)

    @staticmethod
    @contextmanager
    def _cancellable_response(response: Any, cancel_event: threading.Event | None):
        finished = threading.Event()
        raw = getattr(getattr(response, "fp", None), "raw", None)
        connection = getattr(raw, "_sock", None)

        def watch_cancel() -> None:
            while not finished.is_set():
                if not cancel_event.wait(0.1):
                    continue
                # Closing a buffered HTTP reader alone can wait for an active
                # read. Shut down its socket and let the reading thread close
                # the response after it exits the read.
                if connection is not None:
                    try:
                        connection.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                else:
                    response.close()
                return

        if cancel_event is not None:
            threading.Thread(target=watch_cancel, name="sovits-stream-cancel", daemon=True).start()
        try:
            yield
        finally:
            finished.set()

    def synthesize_stream(
        self, model_key: str, text: str, speaker: str, language: str = "auto",
        *, cancel_event: threading.Event | None = None,
    ) -> Iterable[tuple[Any, int, str]]:
        import numpy as np

        if not text.strip():
            raise ValueError("Text is required for GPT-SoVITS playback")
        if language not in SOVITS_LANGUAGES:
            raise ValueError(f"Unsupported GPT-SoVITS language {language!r}")
        self._ensure_server(model_key, speaker=speaker, language=language)
        if cancel_event is not None and cancel_event.is_set():
            return
        assert self._port is not None
        payload = json.dumps(
            {
                "text": text,
                "text_lang": language,
                "ref_audio_path": speaker,
                "prompt_text": self.prompt_text,
                "prompt_lang": self.prompt_lang,
                "text_split_method": "cut5",
                "fragment_interval": 0.15,
            }
        ).encode()
        request = urllib.request.Request(
            f"http://127.0.0.1:{self._port}/tts",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with (
                urllib.request.urlopen(request, timeout=self.audio_timeout_seconds) as response,
                self._cancellable_response(response, cancel_event),
            ):
                while True:
                    if cancel_event is not None and cancel_event.is_set():
                        return
                    header = self._read_exact(response, 8)
                    if cancel_event is not None and cancel_event.is_set():
                        return
                    if not header:
                        break
                    if len(header) != 8:
                        raise RuntimeError("Truncated GPT-SoVITS audio frame")
                    sample_rate, byte_count = struct.unpack("!II", header)
                    pcm = self._read_exact(response, byte_count)
                    if cancel_event is not None and cancel_event.is_set():
                        return
                    if len(pcm) != byte_count:
                        raise RuntimeError("Truncated GPT-SoVITS audio data")
                    if sample_rate == 0:
                        detail = json.loads(pcm.decode("utf-8")).get("message", "Synthesis failed")
                        raise RuntimeError(f"GPT-SoVITS synthesis failed: {detail}")
                    samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32)
                    samples /= 32768.0
                    yield samples, sample_rate, ""
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            try:
                detail = json.loads(detail).get("message", detail)
            except ValueError:
                pass
            raise RuntimeError(f"GPT-SoVITS request failed: {detail}") from error
        except (TimeoutError, urllib.error.URLError) as error:
            if isinstance(error, urllib.error.URLError) and not isinstance(error.reason, TimeoutError):
                raise
            # A stalled inference may still hold the server's model lock.
            # Stop it so retrying starts a fresh server rather than queuing
            # behind the same blocked request.
            self.close()
            raise TimeoutError(
                f"GPT-SoVITS did not return audio within {self.audio_timeout_seconds:g} seconds. "
                "The speech server was stopped; try again."
            ) from error

    def synthesize(
        self, model_key: str, text: str, speaker: str, language: str = "auto"
    ) -> tuple[Any, int]:
        import numpy as np

        chunks = list(self.synthesize_stream(model_key, text, speaker, language))
        if not chunks:
            raise RuntimeError("GPT-SoVITS generated no audio")
        rate = chunks[0][1]
        if any(chunk_rate != rate for _, chunk_rate, _ in chunks):
            raise RuntimeError("GPT-SoVITS changed sample rate during synthesis")
        return np.concatenate([samples for samples, _, _ in chunks]), rate


__all__ = ["SOVITS_LANGUAGES", "SovitsTtsProvider"]
