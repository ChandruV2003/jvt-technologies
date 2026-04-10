from __future__ import annotations

import json
import re
from urllib import error, request

from app.core.paths import resolve_answer_model_cache_root
from app.core.settings import settings
from app.services.types import GeneratedAnswerResult


class ProviderUnavailableError(RuntimeError):
    pass


class AnswerProvider:
    name = "answer-provider"

    def ensure_available(self) -> None:
        return None

    def generate(self, question: str, hits):
        raise NotImplementedError


class JsonCitedAnswerMixin:
    def _build_system_prompt(self) -> str:
        return (
            "You are a private document intelligence assistant. "
            "Answer only from the supplied retrieved chunks. "
            "Return JSON only with keys: answer, citations, confidence, note. "
            "citations must be an array of chunk_id strings drawn only from the supplied context. "
            "If the context is weak, say so in note and keep the answer narrowly grounded."
        )

    def _build_user_prompt(self, question: str, hits) -> str:
        lines = [
            f"Question: {question}",
            "",
            "Use only the following retrieved chunks.",
        ]
        for hit in hits[: settings.retrieval_top_k]:
            lines.extend(
                [
                    f"chunk_id: {hit.chunk_id}",
                    f"filename: {hit.filename}",
                    f"locator: {hit.locator}",
                    f"citation_label: {hit.citation_label}",
                    f"score: {hit.score}",
                    "text:",
                    hit.text,
                    "---",
                ]
            )
        return "\n".join(lines)

    def _parse_generated_answer(self, content: str, hits, provider_name: str, mode: str) -> GeneratedAnswerResult:
        parsed = self._extract_json_payload(content)
        answer_text = str(parsed.get("answer", "")).strip()
        if not answer_text:
            raise ProviderUnavailableError("answer provider returned an empty answer.")

        valid_chunk_ids = {hit.chunk_id for hit in hits}
        citations: list[str] = []
        for citation in parsed.get("citations", []):
            citation_id = str(citation).strip()
            if citation_id in valid_chunk_ids and citation_id not in citations:
                citations.append(citation_id)
        if not citations:
            citations = [hit.chunk_id for hit in hits[:2]]

        confidence = parsed.get("confidence")
        try:
            confidence_value = round(float(confidence), 6) if confidence is not None else None
        except (TypeError, ValueError):
            confidence_value = None

        note = parsed.get("note")
        note_value = str(note).strip() if note is not None else None
        return GeneratedAnswerResult(
            mode=mode,
            provider=provider_name,
            text=answer_text,
            citations=citations,
            confidence=confidence_value,
            note=note_value,
        )

    def _extract_json_payload(self, content: str) -> dict[str, object]:
        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
        try:
            payload = json.loads(cleaned)
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            pass

        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ProviderUnavailableError("answer provider did not return JSON content.")
        try:
            payload = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ProviderUnavailableError("answer provider JSON could not be parsed.") from exc
        if not isinstance(payload, dict):
            raise ProviderUnavailableError("answer provider JSON payload was not an object.")
        return payload


class ExtractiveAnswerProvider(AnswerProvider):
    name = "extractive"

    def generate(self, question: str, hits):
        if not hits:
            return GeneratedAnswerResult(
                mode="extractive",
                provider=self.name,
                text="No grounded passages were available to answer the question.",
                confidence=0.0,
                note="Fallback extractive mode with no retrieved passages.",
            )

        question_terms = self._tokenize(question)
        sentence_candidates: list[tuple[int, str]] = []
        for hit in hits[:3]:
            for sentence in self._split_sentences(hit.text):
                score = len(question_terms.intersection(self._tokenize(sentence)))
                sentence_candidates.append((score, sentence.strip()))

        sentence_candidates.sort(key=lambda item: item[0], reverse=True)
        selected_sentences: list[str] = []
        for _, sentence in sentence_candidates:
            if sentence and sentence not in selected_sentences:
                selected_sentences.append(sentence)
            if len(selected_sentences) == 2:
                break

        if not selected_sentences:
            selected_sentences = [hits[0].text[:240].strip()]

        answer_text = " ".join(selected_sentences)
        if answer_text and answer_text[-1] not in ".!?":
            answer_text += "."

        return GeneratedAnswerResult(
            mode="extractive",
            provider=self.name,
            text=answer_text,
            citations=[hit.chunk_id for hit in hits[:3]],
            confidence=round(max(hits[0].score, 0.0), 6),
            note="Fallback extractive synthesis from retrieved passages.",
        )

    def _split_sentences(self, text: str) -> list[str]:
        return [sentence for sentence in re.split(r"(?<=[.!?])\s+", text) if sentence.strip()]

    def _tokenize(self, text: str) -> set[str]:
        return {
            term
            for term in re.findall(r"[a-z0-9]+", text.lower())
            if len(term) > 1
        }


class OpenAICompatibleAnswerProvider(JsonCitedAnswerMixin, AnswerProvider):
    name = "openai-compatible"

    def ensure_available(self) -> None:
        if not settings.answer_api_base_url.strip():
            raise ProviderUnavailableError("ANSWER_API_BASE_URL is not configured.")
        if not settings.answer_model_name.strip():
            raise ProviderUnavailableError("ANSWER_MODEL_NAME is not configured.")

    def generate(self, question: str, hits):
        if not hits:
            return GeneratedAnswerResult(
                mode="model-generated",
                provider=self.name,
                text="No grounded passages were available to answer the question.",
                confidence=0.0,
                note="Model provider received no retrieval hits.",
            )

        self.ensure_available()
        endpoint = self._endpoint_url()
        payload = {
            "model": settings.answer_model_name,
            "temperature": 0.1,
            "messages": [
                {"role": "system", "content": self._build_system_prompt()},
                {"role": "user", "content": self._build_user_prompt(question, hits)},
            ],
        }
        headers = {"Content-Type": "application/json"}
        if settings.answer_api_key.strip():
            headers["Authorization"] = f"Bearer {settings.answer_api_key.strip()}"

        request_body = json.dumps(payload).encode("utf-8")
        http_request = request.Request(endpoint, data=request_body, headers=headers, method="POST")
        timeout = max(float(settings.answer_api_timeout_seconds), 1.0)

        try:
            with request.urlopen(http_request, timeout=timeout) as response:
                response_body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            response_body = exc.read().decode("utf-8", errors="ignore")
            raise ProviderUnavailableError(
                f"answer provider returned HTTP {exc.code}: {response_body[:200]}"
            ) from exc
        except Exception as exc:
            raise ProviderUnavailableError(f"answer provider request failed: {exc}") from exc

        try:
            payload = json.loads(response_body)
            content = payload["choices"][0]["message"]["content"]
        except Exception as exc:
            raise ProviderUnavailableError("answer provider returned an unexpected response shape.") from exc

        return self._parse_generated_answer(content, hits, provider_name=self.name, mode="model-generated")

    def _endpoint_url(self) -> str:
        base_url = settings.answer_api_base_url.strip().rstrip("/")
        if base_url.endswith("/chat/completions"):
            return base_url
        if base_url.endswith("/v1"):
            return f"{base_url}/chat/completions"
        return f"{base_url}/v1/chat/completions"


class MlxLocalAnswerProvider(JsonCitedAnswerMixin, AnswerProvider):
    name = "mlx-local"

    def __init__(self) -> None:
        self.model_name = settings.local_answer_model_name.strip()
        self.cache_root = resolve_answer_model_cache_root()
        self.model_directory = self.cache_root / self.model_name.replace("/", "--")
        self._model = None
        self._tokenizer = None

    def ensure_available(self) -> None:
        if self._model is not None and self._tokenizer is not None:
            return
        if not self.model_name:
            raise ProviderUnavailableError("LOCAL_ANSWER_MODEL_NAME is not configured.")
        self.cache_root.mkdir(parents=True, exist_ok=True)
        try:
            from huggingface_hub import snapshot_download
            from mlx_lm import load
        except Exception as exc:  # pragma: no cover - import failures depend on env
            raise ProviderUnavailableError(f"mlx local answer runtime is not available: {exc}") from exc

        try:
            snapshot_download(
                repo_id=self.model_name,
                local_dir=self.model_directory,
            )
            self._model, self._tokenizer = load(str(self.model_directory))
        except Exception as exc:  # pragma: no cover - model init depends on env
            raise ProviderUnavailableError(f"local answer model could not be loaded: {exc}") from exc

    def generate(self, question: str, hits):
        if not hits:
            return GeneratedAnswerResult(
                mode="local-model",
                provider=self.name,
                text="No grounded passages were available to answer the question.",
                confidence=0.0,
                note="Local model provider received no retrieval hits.",
            )

        self.ensure_available()
        prompt = self._build_prompt(question, hits)

        try:
            from mlx_lm import generate
            from mlx_lm.sample_utils import make_sampler
        except Exception as exc:  # pragma: no cover - import failures depend on env
            raise ProviderUnavailableError(f"mlx local answer runtime is not available: {exc}") from exc

        try:
            generated = generate(
                self._model,
                self._tokenizer,
                prompt,
                verbose=False,
                max_tokens=settings.local_answer_max_tokens,
                sampler=make_sampler(temp=settings.local_answer_temperature),
            )
        except Exception as exc:  # pragma: no cover - generation depends on env
            raise ProviderUnavailableError(f"local answer generation failed: {exc}") from exc

        return self._parse_generated_answer(generated, hits, provider_name=self.name, mode="local-model")

    def _build_prompt(self, question: str, hits) -> str:
        messages = [
            {"role": "system", "content": self._build_system_prompt()},
            {"role": "user", "content": self._build_user_prompt(question, hits)},
        ]
        apply_chat_template = getattr(self._tokenizer, "apply_chat_template", None)
        if callable(apply_chat_template):
            try:
                return apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            except Exception:
                pass

        plain_prompt = [self._build_system_prompt(), "", self._build_user_prompt(question, hits), "", "JSON response:"]
        return "\n".join(plain_prompt)


class LocalAnswerProviderPlaceholder(AnswerProvider):
    name = "local-answer-placeholder"

    def ensure_available(self) -> None:
        raise ProviderUnavailableError("Local answer model is not configured yet.")


class ApiAnswerProviderPlaceholder(AnswerProvider):
    name = "api-answer-placeholder"

    def ensure_available(self) -> None:
        raise ProviderUnavailableError("API answer provider is not configured yet.")


def build_answer_provider(configured_name: str) -> AnswerProvider:
    normalized = configured_name.strip().lower()
    if normalized in {"extractive", "", "none"}:
        return ExtractiveAnswerProvider()
    if normalized in {"mlx-local", "local", "local-mlx", "mlx"}:
        return MlxLocalAnswerProvider()
    if normalized in {"local-placeholder"}:
        return LocalAnswerProviderPlaceholder()
    if normalized in {"api", "openai-compatible", "openai", "api-openai-compatible"}:
        return OpenAICompatibleAnswerProvider()
    if normalized in {"api-placeholder"}:
        return ApiAnswerProviderPlaceholder()
    return ExtractiveAnswerProvider()
