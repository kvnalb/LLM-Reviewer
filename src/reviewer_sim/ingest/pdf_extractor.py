"""
PDF extraction module for OpenReview papers.

Supports both section-aware extraction (intelligent prioritization) and
full-text extraction with configurable token budgets.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Optional

import requests


class PDFExtractor:
    """Extract text from OpenReview PDFs with section-aware and full-text modes."""

    def __init__(
        self,
        cache_dir: Path,
        extraction_mode: str = "sections",
        max_tokens: int = 6000,
    ):
        """
        Initialize PDF extractor.

        Parameters
        ----------
        cache_dir : Path
            Directory to store downloaded PDFs (e.g., data/pdf_cache/)
        extraction_mode : str
            "sections" (smart extraction) or "fulltext" (complete text)
        max_tokens : int
            Target token budget (rough estimate: chars / 4)
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.extraction_mode = extraction_mode
        self.max_tokens = max_tokens

    def extract_paper(
        self, paper_id: str, pdf_url: str, title: str, abstract: str
    ) -> Dict:
        """
        Extract text from PDF.

        Returns dict with:
        {
            "full_text": str,
            "sections": dict (optional, only if mode="sections"),
            "token_count": int,
            "extraction_metadata": {
                "success": bool,
                "source": "pdf_sections" | "pdf_fulltext" | "abstract_fallback",
                "mode": str,
                "num_pages": int,
                "error": str | None
            }
        }
        """
        try:
            # Download PDF if not cached
            pdf_path = self._download_pdf(pdf_url, paper_id)

            # Extract text using PyMuPDF
            raw_text = self._extract_text_from_pdf(pdf_path)
            num_pages = self._get_page_count(pdf_path)

            # Process based on mode
            if self.extraction_mode == "sections":
                return self._extract_sections(raw_text, title, abstract, num_pages)
            else:  # fulltext
                return self._extract_fulltext(raw_text, title, abstract, num_pages)

        except Exception as e:
            # Fallback to abstract (will be manually fixed)
            return {
                "full_text": f"{title}\n\n{abstract}",
                "token_count": len(title + abstract) // 4,
                "extraction_metadata": {
                    "success": False,
                    "source": "abstract_fallback",
                    "mode": self.extraction_mode,
                    "num_pages": 0,
                    "error": str(e),
                },
            }

    def _download_pdf(self, pdf_url: str, paper_id: str) -> Path:
        """Download PDF to cache if not exists, return path."""
        cache_path = self.cache_dir / f"{paper_id}.pdf"
        if cache_path.exists():
            return cache_path

        response = requests.get(pdf_url, timeout=30)
        response.raise_for_status()

        cache_path.write_bytes(response.content)
        return cache_path

    def _extract_text_from_pdf(self, pdf_path: Path) -> str:
        """Extract raw text using PyMuPDF."""
        import fitz

        doc = fitz.open(pdf_path)
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text

    def _get_page_count(self, pdf_path: Path) -> int:
        """Get page count from PDF."""
        import fitz

        doc = fitz.open(pdf_path)
        count = doc.page_count
        doc.close()
        return count

    def _extract_sections(
        self, text: str, title: str, abstract: str, num_pages: int
    ) -> Dict:
        """Section-aware extraction with priority ordering."""
        sections = self._detect_sections(text)

        # Priority order: title → abstract → introduction → conclusion → methods
        combined = ""
        token_budget = self.max_tokens

        # Always include title
        combined += f"Title: {title}\n\n"
        token_budget -= len(title) // 4

        # Add abstract if available (or use provided abstract)
        section_abstract = sections.get("abstract", "") or abstract
        if section_abstract:
            section_tokens = len(section_abstract) // 4
            if token_budget - section_tokens > 500:  # Keep 500 token safety margin
                combined += f"Abstract:\n{section_abstract}\n\n"
                token_budget -= section_tokens

        # Add sections in priority order
        for section_name in ["introduction", "conclusion", "methods"]:
            section_text = sections.get(section_name, "")
            if section_text:
                section_tokens = len(section_text) // 4
                if token_budget - section_tokens > 500:  # Keep 500 token safety margin
                    combined += f"\n{section_name.upper()}\n{section_text}\n"
                    token_budget -= section_tokens
                else:
                    # Truncate this section to fit budget
                    remaining_chars = token_budget * 4 - 2000  # 500 token margin
                    if remaining_chars > 0:
                        combined += (
                            f"\n{section_name.upper()}\n{section_text[:remaining_chars]}...\n"
                        )
                    break

        return {
            "full_text": combined,
            "sections": sections,
            "token_count": len(combined) // 4,
            "extraction_metadata": {
                "success": True,
                "source": "pdf_sections",
                "mode": "sections",
                "num_pages": num_pages,
                "error": None,
            },
        }

    def _extract_fulltext(
        self, text: str, title: str, abstract: str, num_pages: int
    ) -> Dict:
        """Full-text extraction with simple truncation."""
        # Remove references section (typically last 2-3 pages)
        text = self._remove_references(text)

        # Truncate to max_tokens
        max_chars = self.max_tokens * 4
        if len(text) > max_chars:
            text = text[: max_chars - 50] + "...\n[TRUNCATED]"

        combined = f"Title: {title}\n\nAbstract:\n{abstract}\n\n{text}"

        return {
            "full_text": combined,
            "token_count": len(combined) // 4,
            "extraction_metadata": {
                "success": True,
                "source": "pdf_fulltext",
                "mode": "fulltext",
                "num_pages": num_pages,
                "error": None,
            },
        }

    def _detect_sections(self, text: str) -> Dict[str, str]:
        """Heuristic section detection using common headers."""
        sections = {}

        # Common patterns for section headers
        patterns = {
            "abstract": r"(?i)\babstract\b",
            "introduction": r"(?i)^1\.?\s+introduction|^introduction\s*$",
            "methods": r"(?i)^[\d\.]+\s*(methods|methodology|approach)|^(methods|methodology)\s*$",
            "results": r"(?i)^[\d\.]+\s*results|^results\s*$",
            "conclusion": r"(?i)^[\d\.]+\s*conclusion|^conclusion\s*$",
        }

        lines = text.split("\n")
        current_section = None
        section_text = []

        for line in lines:
            # Check if line matches a section header
            matched = False
            for section_name, pattern in patterns.items():
                if re.search(pattern, line):
                    # Save previous section
                    if current_section and section_text:
                        sections[current_section] = "\n".join(section_text).strip()
                    # Start new section
                    current_section = section_name
                    section_text = []
                    matched = True
                    break

            if not matched and current_section:
                section_text.append(line)

        # Save last section
        if current_section and section_text:
            sections[current_section] = "\n".join(section_text).strip()

        return sections

    def _remove_references(self, text: str) -> str:
        """Remove references section (heuristic: after 'References' header)."""
        ref_match = re.search(r"(?i)\nreferences\s*\n", text)
        if ref_match:
            return text[: ref_match.start()]
        return text
