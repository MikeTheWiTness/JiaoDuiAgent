"""text nav tools"""
import re
from typing import Optional
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool

_current_text: Optional[str] = None

def set_current_text(text: str):
    global _current_text
    _current_text = text

class LocateParagraphParams(BaseModel):
    keywords: str = Field(description="keywords to locate")

class LocateParagraphTool(BaseTool):
    name: str = "locate_paragraph"
    description: str = "Search for keywords in the source text and return the surrounding paragraphs."
    args_schema: type[BaseModel] = LocateParagraphParams
    def _run(self, keywords: str) -> str:
        global _current_text
        if not _current_text:
            return "[error: no text]"
        text = _current_text
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        if not paragraphs:
            paragraphs = [l.strip() for l in text.split("\n") if l.strip()]
        for i, para in enumerate(paragraphs):
            if keywords in para:
                start = max(0, i - 1)
                end = min(len(paragraphs), i + 2)
                return "found at para " + str(i+1) + ":\n\n" + "\n\n".join(paragraphs[start:end])
        return "[not found]"

class ReadSectionParams(BaseModel):
    start: int = Field(description="start paragraph number (1-based)")
    end: int = Field(description="end paragraph number (inclusive)")

class ReadSectionTool(BaseTool):
    name: str = "read_section"
    description: str = "Read paragraphs by range. start and end are 1-based."
    args_schema: type[BaseModel] = ReadSectionParams
    def _run(self, start: int, end: int) -> str:
        global _current_text
        if not _current_text:
            return "[error: no text]"
        text = _current_text
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        if not paragraphs:
            paragraphs = [l.strip() for l in text.split("\n") if l.strip()]
        if start < 1 or end > len(paragraphs) or start > end:
            return f"[error: invalid range {start}-{end} of {len(paragraphs)}]"
        return "\n\n".join(paragraphs[start-1:end])
