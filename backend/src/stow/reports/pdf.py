from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), autoescape=True)


def _rupees(paise: int) -> str:
    """Format paise integer as Indian rupee string with comma grouping."""
    negative = paise < 0
    abs_paise = abs(paise)
    rupees = abs_paise // 100
    ps = abs_paise % 100
    # Indian number grouping: last 3 digits, then groups of 2
    s = str(rupees)
    if len(s) > 3:
        s = s[:-3] + "," + s[-3:]
        i = len(s) - 7
        while i > 0:
            s = s[:i] + "," + s[i:]
            i -= 2
    result = f"₹{s}.{ps:02d}"
    return f"({result})" if negative else result


def render_pdf(template_name: str, report: Any) -> bytes:
    template = _env.get_template(f"{template_name}.html")
    html_str = template.render(report=report, rupees=_rupees)
    result = HTML(string=html_str).write_pdf()
    assert result is not None
    return result
