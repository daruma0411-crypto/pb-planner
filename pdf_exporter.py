"""Markdown → PDF（WeasyPrint 経由）"""
import markdown
from weasyprint import HTML


_CSS = """
@page { size: A4; margin: 18mm; }
body { font-family: 'Hiragino Sans', 'Yu Gothic', sans-serif; font-size: 10.5pt; line-height: 1.7; }
h1 { font-size: 18pt; border-bottom: 2px solid #333; padding-bottom: 0.3em; }
h2 { font-size: 14pt; border-bottom: 1px solid #888; padding-bottom: 0.2em; margin-top: 1.5em; }
h3 { font-size: 12pt; margin-top: 1.2em; }
table { border-collapse: collapse; width: 100%; margin: 0.8em 0; }
th, td { border: 1px solid #666; padding: 0.3em 0.5em; }
th { background: #eee; }
code { background: #f4f4f4; padding: 0.1em 0.3em; border-radius: 3px; font-family: monospace; }
blockquote { border-left: 4px solid #ccc; margin-left: 0; padding-left: 1em; color: #555; }
"""


def md_to_pdf(md_text: str, output_path: str) -> None:
    html_body = markdown.markdown(md_text, extensions=["tables", "fenced_code"])
    full_html = f"""<!DOCTYPE html><html lang='ja'><head><meta charset='utf-8'>
<style>{_CSS}</style></head><body>{html_body}</body></html>"""
    HTML(string=full_html).write_pdf(output_path)
