---
name: "ai-dev-guide"
description: "Guides AI prompt engineering, model tuning, and integration patterns. Invoke for tasks related to prompts, LLM config, or model behavior."
---

# AI Development Guide

This skill provides guidelines for developing AI features, specifically focusing on Prompt Engineering and Model Integration.

## Reference Documentation

- [PROMPT_ENGINEERING_GUIDE.md](file:///root/zzp/langextract-main/generate_report_test/docs/ai_dev/PROMPT_ENGINEERING_GUIDE.md): Best practices for designing prompts, handling formats, and model-specific tuning.

## Key Concepts

### Prompt Engineering
1.  **Format Authorization**: Explicitly authorize rich text (Markdown/Tables) in System Prompts to avoid model self-censorship.
    *   *Good*: "If user asks for tables, you must provide them. Output in Markdown."
    *   *Bad*: "Use formal language only." (Often leads to text-only output)
2.  **Model Specifics**: 
    *   **Qwen3-Coder**: Needs explicit format instructions.
    *   **DeepSeek**: Needs strict grounding to avoid hallucinations.

### Integration Patterns
- **Streaming**: Ensure error handling distinguishes between content chunks and exception messages (e.g., SSE `data: {"error": "..."}`).
- **Docker Networking**: Use `host.docker.internal` for containers to access host-local models (Ollama).

## Common Tasks
- **Tuning Prompts**: Refer to `docs/ai_dev/PROMPT_ENGINEERING_GUIDE.md` for templates.
- **Debugging Streams**: Check backend logs for mixed error/content signals.
