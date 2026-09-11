import re
import html

def markdown_to_telegram_html(text: str) -> str:
    """
    Converts standard Markdown text (from LLM output) into Telegram-compatible HTML.
    Handles escaping of HTML special chars (&, <, >), bold (**text** or __text__),
    italic (*text* or _text_), inline code (`code`), code blocks (```code```),
    links ([text](url)), and bullet point lists (* or -).
    """
    if not text:
        return ""

    # Extract code blocks to preserve their content from markdown formatting
    code_blocks = []
    def save_code_block(match):
        code_content = match.group(2)
        escaped_code = html.escape(code_content.strip())
        placeholder = f"TGCODEBLOCK{len(code_blocks)}TG"
        code_blocks.append(f"<pre><code>{escaped_code}</code></pre>")
        return placeholder

    # Match ```lang\ncode``` or ```code```
    text = re.sub(r'```(\w*)\n?(.*?)```', save_code_block, text, flags=re.DOTALL)

    # Extract inline code
    inline_codes = []
    def save_inline_code(match):
        code_content = match.group(1)
        escaped_code = html.escape(code_content)
        placeholder = f"TGINLINECODE{len(inline_codes)}TG"
        inline_codes.append(f"<code>{escaped_code}</code>")
        return placeholder

    text = re.sub(r'`([^`]+)`', save_inline_code, text)

    # Escape HTML special characters in the remaining text
    text = html.escape(text)

    # Convert Markdown Links: [label](url) -> <a href="url">label</a>
    def format_link(match):
        label = match.group(1)
        url = match.group(2).strip()
        if url.startswith("/"):
            url = f"http://127.0.0.1:8000{url}"
        return f'<a href="{url}">{label}</a>'

    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', format_link, text)

    # Convert Bold: **text** or __text__ -> <b>text</b>
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text, flags=re.DOTALL)
    text = re.sub(r'__(.*?)__', r'<b>\1</b>', text, flags=re.DOTALL)

    # Convert Italic: *text* or _text_ -> <i>text</i>
    text = re.sub(r'(?<!\*)\*([^\*\s][^\*]*?[^\*\s]|\w)\*(?!\*)', r'<i>\1</i>', text)
    text = re.sub(r'(?<!_)_([^_\s][^_]*?[^_\s]|\w)_(?!_)', r'<i>\1</i>', text)

    # Convert Strikethrough: ~~text~~ -> <s>text</s>
    text = re.sub(r'~~(.*?)~~', r'<s>\1</s>', text, flags=re.DOTALL)

    # Convert Markdown Bullet Points: lines starting with '* ' or '- ' or '+ '
    lines = text.split('\n')
    formatted_lines = []
    for line in lines:
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        indent_str = ' ' * indent
        if stripped.startswith(('* ', '- ', '+ ')):
            bullet_content = stripped[2:]
            formatted_lines.append(f"{indent_str}• {bullet_content}")
        else:
            formatted_lines.append(line)
    text = '\n'.join(formatted_lines)

    # Restore inline code blocks
    for i, code_html in enumerate(inline_codes):
        text = text.replace(f"TGINLINECODE{i}TG", code_html)

    # Restore pre/code blocks
    for i, code_html in enumerate(code_blocks):
        text = text.replace(f"TGCODEBLOCK{i}TG", code_html)

    return text
