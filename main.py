"""
CLI entry point for the literature extraction pipeline.

Usage examples:
    python main.py --matrix meat
    python main.py --matrix meat --model claude-haiku-4-5-20251001
    python main.py --matrix meat --skip-download --skip-parsing
"""

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Literature acquisition and information extraction pipeline."
    )
    parser.add_argument(
        "--matrix",
        default="meat",
        help="Food matrix identifier (must match a key in configs/search.json "
             "and configs/schemas/{matrix}_schema.yaml). Default: meat",
    )
    parser.add_argument(
        "--model",
        default="gpt-4o-mini",
        help="LiteLLM model string (e.g. gpt-4o-mini, claude-haiku-4-5-20251001). "
             "Default: gpt-4o-mini",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Skip Stage 1 and use existing PDFs in data/raw_pdfs/{matrix}/",
    )
    parser.add_argument(
        "--skip-parsing",
        action="store_true",
        help="Skip Stage 2 and use existing Markdown in data/parsed_markdown/{matrix}/",
    )
    args = parser.parse_args()

    from src.data_retrieval.pipeline import run_pipeline

    run_pipeline(
        matrix=args.matrix,
        config_dir=Path("configs"),
        data_dir=Path("data"),
        model_id=args.model,
        api_key=os.getenv("SEMANTIC_SCHOLAR_API_KEY"),
        skip_download=args.skip_download,
        skip_parsing=args.skip_parsing,
    )


if __name__ == "__main__":
    main()
