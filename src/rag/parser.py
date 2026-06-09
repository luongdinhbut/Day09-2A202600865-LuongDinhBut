from __future__ import annotations


def parse_policy_markdown(markdown_text: str) -> list[dict]:
    chunks = []
    current_h2 = ""
    current_h3 = ""
    current_content = []
    
    def save_chunk():
        if current_h3 and current_content:
            text = "\n".join(current_content).strip()
            if text:
                rendered_text = f"## {current_h2}\n### {current_h3}\n{text}"
                chunks.append({
                    "section_h2": current_h2,
                    "section_h3": current_h3,
                    "citation": f"{current_h2} > {current_h3}",
                    "rendered_text": rendered_text
                })

    for line in markdown_text.split('\n'):
        if line.startswith("## "):
            save_chunk()
            current_h2 = line.replace("## ", "").strip()
            current_h3 = ""
            current_content = []
        elif line.startswith("### "):
            save_chunk()
            current_h3 = line.replace("### ", "").strip()
            current_content = []
        else:
            if current_h3:
                current_content.append(line)
                
    save_chunk()
    return chunks
