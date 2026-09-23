"""
calculator.py — NOVA's local math engine.

Parses natural-language arithmetic into a safe AST-evaluable expression.
NEVER eval()s raw user text: the parser accepts only numbers, the four
operators, percent-of, powers, parentheses and decimal points — everything
else is stripped before ast.literal_eval-style validation.

Supported:
  45 times 12 | 200 divided by 4 | 25 plus 17 | 90 minus 31
  what is 15 percent of 800 | 2 to the power of 8 | 144 square root
  5 squared | 2 cubed | (2+3) * 4 | 3.5 + 1.2
"""

import ast
import operator
import re

# word -> symbol
_WORD_OPS = [
    (re.compile(r"\bto\s+the\s+power\s+(?:of\s+)?|\bpower\s+of\s+|\b\^\s*", re.I), "**"),
    (re.compile(r"\bsquared\b", re.I), "**2"),
    (re.compile(r"\bcubed\b", re.I), "**3"),
    (re.compile(r"\b(?:times|multiplied\s+by|x)\b", re.I), "*"),
    (re.compile(r"\b(?:divided\s+by|over)\b", re.I), "/"),
    (re.compile(r"\b(?:plus|add(ed)?\s+to)\b", re.I), "+"),
    (re.compile(r"\b(?:minus|subtract(ed)?\s+by|less)\b", re.I), "-"),
    (re.compile(r"\bmod(?:ulo|ulus)?\b", re.I), "%"),
]

_SQRT_RE = re.compile(r"\b(?:square\s+root\s+of\s+|sqrt(?:\s+of)?\s+)(\d+(?:\.\d+)?)", re.I)
_SQRT_RE2 = re.compile(r"(\d+(?:\.\d+)?)\s+square\s+root", re.I)
_PCT_OF_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|percent)\s+of\s+(\d+(?:\.\d+)?)", re.I)

_ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_ALLOWED_UNARY = {ast.USub: operator.neg, ast.UAdd: operator.pos}


def _safe_eval(node):
    """Evaluate a whitelist-only AST. Raises ValueError on anything else."""
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINOPS:
        return _ALLOWED_BINOPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARY:
        return _ALLOWED_UNARY[type(node.op)](_safe_eval(node.operand))
    raise ValueError("unsupported expression")


def _format(num) -> str:
    if isinstance(num, float):
        if num.is_integer():
            return str(int(num))
        return f"{num:,.4f}".rstrip("0").rstrip(".")
    return f"{num:,}"


def extract_expression(text: str):
    """
    Returns (python_expr, human_desc) or None if the text isn't math.
    Raises nothing — bad input yields None.
    """
    text = text.strip().rstrip("?.!").strip()
    low = text.lower()

    # Strip leading conversational wrappers
    low = re.sub(
        r"^(?:hey\s+)?(?:nova[,\s]+)?(?:please\s+)?"
        r"(?:what(?:'s| is| are)?\s+|calculate\s+|compute\s+|solve\s+|how\s+much\s+is\s+|"
        r"whats\s+)?",
        "", low,
    ).strip()

    # percent-of: "15 percent of 800"
    m = _PCT_OF_RE.search(low)
    if m:
        a, b = float(m.group(1)), float(m.group(2))
        return f"({a}/100)*{b}", f"{_format(a)} percent of {_format(b)}"

    # square root forms
    m = _SQRT_RE.search(low) or _SQRT_RE2.search(low)
    if m:
        a = float(m.group(1))
        return f"{a}**0.5", f"the square root of {_format(a)}"

    # word operators -> symbols
    expr = low
    for pattern, sym in _WORD_OPS:
        expr = pattern.sub(f" {sym} ", expr)

    # only keep math-safe characters
    expr = re.sub(r"[^0-9+\-*/%.() ]", " ", expr)
    expr = re.sub(r"\s+", " ", expr).strip()

    if not re.search(r"\d", expr):
        return None
    if not re.search(r"[+\-*/%]|\*\*", expr):
        # A bare number isn't a calculation.
        return None
    return expr, low


def calculate(text: str):
    """
    Full natural-language calculation. Returns a speakable persona string.
    Never raises; unsafe/invalid input gets a composed refusal.
    """
    parsed = extract_expression(text)
    if parsed is None:
        return "That doesn't parse as arithmetic I can do locally, sir."
    expr, desc = parsed
    try:
        tree = ast.parse(expr, mode="eval")
        result = _safe_eval(tree)
    except ZeroDivisionError:
        return "Division by zero, sir — even my standards have limits."
    except (ValueError, SyntaxError, OverflowError):
        return "That expression is beyond what I calculate safely, sir."
    except Exception:
        return "The calculation didn't go through, sir."

    if isinstance(result, complex) or abs(result) > 1e15:
        return f"That's an impressively large number, sir — beyond my display range."
    return f"{desc} comes to {_format(result)}, sir."
