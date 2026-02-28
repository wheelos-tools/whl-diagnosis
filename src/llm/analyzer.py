import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class LLMAnalyzer:
    def __init__(self):
        self.api_key = os.getenv("LLM_API_KEY")
        self.base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
        self.model = os.getenv("LLM_MODEL", "gpt-4o")

        if self.api_key:
            try:
                from openai import OpenAI
                self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            except ImportError:
                logger.warning("openai python package is not installed. LLM analysis will use degraded mock mode. Please pip install openai.")
                self.client = None
        else:
            self.client = None
            logger.warning("LLM_API_KEY environment variable is not set. Skipping real LLM inference.")

    def analyze_report(self, markdown_report: str) -> Optional[str]:
        if not self.client:
            return None

        system_prompt = """You are an expert autonomous driving hardware infrastructure and network reliability engineer.
Your task is to read the diagnostic report, focus on the failures, warnings, and their raw execution output and system logs (like dmesg).
Provide a concise, root-cause analysis and step-by-step actionable remediation guide.

Format your response as a clear markdown document:
1. **Root Cause Analysis**: Briefly explain what went wrong based on the logs.
2. **Action Plan**: Step-by-step commands or actions the operator should take to fix the issue.
"""
        try:
            logger.info(f"Submitting report to LLM ({self.model}) for analysis...")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Here is the diagnostic report:\n\n{markdown_report}"}
                ],
                temperature=0.2,
                max_tokens=1500,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Failed to communicate with LLM: {str(e)}")
            return f"> **Error**: LLM analysis failed due to: {str(e)}"
