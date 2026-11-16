"""Local LLM Client supporting OpenAI-compatible local endpoints (vLLM, llama.cpp, Ollama)."""
import json
import urllib.request
import urllib.error
from typing import Optional, List, Dict, Any


class LocalLLMClient:
    """Client to query local offline LLM service."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000/v1",
        model_name: str = "qwen2.5-coder-7b",
        timeout: int = 120,
        max_tokens: int = 768,
        temperature: float = 0.0,
        verbose: bool = False
    ):
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.verbose = verbose
        self._online: Optional[bool] = None
        self.last_response_metadata: Dict[str, Any] = {}

    def is_available(self, force_check: bool = False) -> bool:
        """Check if the local LLM endpoint is active (cached)."""
        if self._online is not None and not force_check:
            return self._online
            
        try:
            req = urllib.request.Request(
                f"{self.base_url}/models",
                headers={"User-Agent": "DataMateAgent"}
            )
            with urllib.request.urlopen(req, timeout=2.0) as response:
                self._online = (response.status == 200)
        except Exception as e:
            if self.verbose:
                print(f"[LLM Check Warning] Could not connect to {self.base_url}/models: {e}")
            self._online = False
            
        return self._online

    def generate(
        self,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stop: Optional[List[str]] = None
    ) -> Optional[str]:
        """Send chat completion request to local LLM."""
        self.last_response_metadata = {}
        if not self.is_available():
            if self.verbose:
                print(f"[LLM Warning] Endpoint {self.base_url} is not online.")
            return None

        url = f"{self.base_url}/chat/completions"
        system_content = (
            "You are an expert DuckDB SQL generator for Vietnamese business analytics. "
            "Output ONLY standard DuckDB SQL inside a single ```sql ... ``` block. "
            "Never provide any conversational text, explanations, or analysis outside the code block."
        )
        
        payload: Dict[str, Any] = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": prompt}
            ],
            "temperature": self.temperature if temperature is None else temperature,
            "max_tokens": self.max_tokens if max_tokens is None else max_tokens
        }
        # Qwen3 otherwise spends a small SQL-generation budget in its <think>
        # channel. vLLM exposes a hard switch through this chat-template option.
        if "qwen3" in self.model_name.lower():
            payload["chat_template_kwargs"] = {"enable_thinking": False}
        if stop:
            payload["stop"] = stop
        
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "DataMateAgent"}
        )
        
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                res_json = json.loads(resp.read().decode("utf-8"))
                choice = res_json["choices"][0]
                usage = res_json.get("usage") or {}
                self.last_response_metadata = {
                    "finish_reason": choice.get("finish_reason"),
                    "prompt_tokens": usage.get("prompt_tokens"),
                    "completion_tokens": usage.get("completion_tokens"),
                    "total_tokens": usage.get("total_tokens"),
                }
                return choice["message"]["content"]
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            print(f"[LLM HTTP ERROR {e.code}] {e.reason}: {err_body}")
            return None
        except urllib.error.URLError as e:
            print(f"[LLM URL/TIMEOUT ERROR] {e.reason} (timeout={self.timeout}s)")
            return None
        except Exception as e:
            print(f"[LLM ERROR {type(e).__name__}]: {e}")
            return None

