#!/usr/bin/env python3
"""Extract Mermaid diagrams from CAPSTONE_FIGURES.md and render to PNG."""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

FIGURES_MD = Path(__file__).resolve().parent.parent / "docs" / "CAPSTONE_FIGURES.md"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "figures"
OUTPUT_DIR.mkdir(exist_ok=True)

# Map figure headings to filenames
FIGURE_MAP = {
    "Figure 1": "fig01-system-architecture",
    "Figure 2": "fig02-alert-pipeline",
    "Figure 3": "fig03-circuit-breaker-state",
    "Figure 4": "fig04-technology-stack",
    "Figure 5": "fig05-project-timeline",
    "Figure 6": "fig06-llm-failover-chain",
    "Figure 7": "fig07-circuit-breaker-detail",
    "Figure 8": "fig08-hitl-governance",
    "Figure 9": "fig09-k8s-topology",
    "Figure 10": "fig10-severity-response",
    "Figure 11": "fig11-dedup-funnel",
    "Figure 12": "fig12-dedup-flowchart",
    "Figure 13": "fig13-attack-severity-pie",
    "Figure 14": "fig14-mitre-attack-coverage",
    "Figure 15": "fig15-before-vs-after",
    "Figure 16": "fig16-llm-provider-comparison",
    "Figure 17": "fig17-cluster-scalability",
    "Figure 18": "fig18-capstone1-vs-2",
    "Figure 19": "fig19-iot-integration",
    "Figure 20": "fig20-key-contributions",
}

def extract_mermaid_blocks(md_text: str) -> list[tuple[str, str]]:
    """Extract (figure_heading, mermaid_code) pairs from markdown."""
    results = []
    # Find all ### Figure N headings and the mermaid block that follows
    pattern = re.compile(
        r'### (Figure \d+)\s*—[^\n]*\n'   # heading
        r'.*?'                              # blockquote etc.
        r'```mermaid\n(.*?)```',            # mermaid block
        re.DOTALL
    )
    for match in pattern.finditer(md_text):
        fig_key = match.group(1)
        mermaid_code = match.group(2).strip()
        results.append((fig_key, mermaid_code))
    return results


def render_mermaid(fig_key: str, mermaid_code: str, output_dir: Path) -> bool:
    """Render a single Mermaid diagram to PNG using mmdc."""
    filename = FIGURE_MAP.get(fig_key, fig_key.lower().replace(" ", ""))
    output_path = output_dir / f"{filename}.png"

    with tempfile.NamedTemporaryFile(mode='w', suffix='.mmd', delete=False) as f:
        f.write(mermaid_code)
        input_path = f.name

    # mmdc config for dark background (matching our diagrams)
    config = {
        "theme": "dark",
        "themeVariables": {
            "darkMode": True,
            "background": "#0d1b2a"
        }
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as cf:
        import json
        json.dump(config, cf)
        config_path = cf.name

    PUPPETEER_CONFIG = Path(__file__).resolve().parent.parent / "puppeteer-config.json"

    try:
        result = subprocess.run(
            [
                "mmdc",
                "-i", input_path,
                "-o", str(output_path),
                "-t", "dark",
                "-b", "transparent",
                "-w", "1600",
                "-s", "2",
                "-q",
                "-p", str(PUPPETEER_CONFIG),
            ],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0 and output_path.exists():
            size_kb = output_path.stat().st_size / 1024
            print(f"  ✅ {fig_key} → {output_path.name} ({size_kb:.0f} KB)")
            return True
        else:
            print(f"  ❌ {fig_key} FAILED: {result.stderr[:200]}")
            return False
    except subprocess.TimeoutExpired:
        print(f"  ❌ {fig_key} TIMEOUT")
        return False
    finally:
        Path(input_path).unlink(missing_ok=True)
        Path(config_path).unlink(missing_ok=True)


def main():
    md_text = FIGURES_MD.read_text()
    blocks = extract_mermaid_blocks(md_text)
    print(f"Found {len(blocks)} Mermaid diagrams in {FIGURES_MD.name}\n")

    success = 0
    failed = 0
    for fig_key, mermaid_code in blocks:
        ok = render_mermaid(fig_key, mermaid_code, OUTPUT_DIR)
        if ok:
            success += 1
        else:
            failed += 1

    print(f"\n{'='*50}")
    print(f"Results: {success} rendered, {failed} failed")
    print(f"Output: {OUTPUT_DIR}/")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
