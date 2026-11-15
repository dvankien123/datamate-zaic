"""Local LLM Client supporting OpenAI-compatible local endpoints (vLLM, llama.cpp, Ollama)."""
import json
import urllib.request
import urllib.error
from typing import Optional


class LocalLLMClient:
    """Client to query local offline LLM service."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000/v1",
        model_name: str = "qwen2.5-coder-7b",
        timeout: int = 30
    ):
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.timeout = timeout
        self._online: Optional[bool] = None

    def is_available(self, force_check: bool = False) -> bool:
        """Check if the local LLM endpoint is active (cached)."""
        if self._online is not None and not force_check:
            return self._online
            
        try:
            req = urllib.request.Request(
                f"{self.base_url}/models",
                headers={"User-Agent": "DataMateAgent"}
            )
            with urllib.request.urlopen(req, timeout=1.0) as response:
                self._online = (response.status == 200)
        except Exception:
            self._online = False
            
        return self._online

    def generate(self, prompt: str, temperature: float = 0.0, max_tokens: int = 1024) -> Optional[str]:
        """Send chat completion request to local LLM."""
        if not self.is_available():
            return None

        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": "You are an expert data analysis code generator."},
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "DataMateAgent"}
        )
        
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                res_json = json.loads(resp.read().decode("utf-8"))
                return res_json["choices"][0]["message"]["content"]
        except Exception as e:
            return None
