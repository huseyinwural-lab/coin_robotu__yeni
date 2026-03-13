import re
from dataclasses import dataclass


ALLOWED_QUERY_FIELDS = {
    "rsi14",
    "rsi7",
    "close",
    "open",
    "high",
    "low",
    "volume",
    "ema20",
    "ema50",
    "sma20",
    "sma50",
    "fibo_161_8",
    "fibo_127_2",
    "fibo_100",
    "fibo_78_6",
}

ALLOWED_COMPARISON_OPERATORS = {"<", "<=", ">", ">=", "=", "!="}

_TOKEN_PATTERN = re.compile(
    r"\s*(<=|>=|!=|=|<|>|\(|\)|AND\b|OR\b|[A-Za-z_][A-Za-z0-9_]*|\d+(?:\.\d+)?)",
    re.IGNORECASE,
)


class QueryParseError(ValueError):
    pass


@dataclass
class QueryToken:
    value: str
    position: int


def tokenize_query_expression(query_expression: str) -> list[QueryToken]:
    source = (query_expression or "").strip()
    if not source:
        raise QueryParseError("Query ifadesi boş olamaz.")

    tokens: list[QueryToken] = []
    cursor = 0
    while cursor < len(source):
        match = _TOKEN_PATTERN.match(source, cursor)
        if not match:
            snippet = source[cursor : cursor + 16]
            raise QueryParseError(f"Bilinmeyen token: '{snippet}' (pozisyon {cursor + 1})")
        token_value = match.group(1)
        tokens.append(QueryToken(value=token_value, position=cursor))
        cursor = match.end()

    return tokens


class _Parser:
    def __init__(self, tokens: list[QueryToken]):
        self.tokens = tokens
        self.cursor = 0

    def _peek(self) -> QueryToken | None:
        if self.cursor >= len(self.tokens):
            return None
        return self.tokens[self.cursor]

    def _consume(self) -> QueryToken:
        token = self._peek()
        if token is None:
            raise QueryParseError("Beklenmeyen ifade sonu.")
        self.cursor += 1
        return token

    def _accept_keyword(self, keyword: str) -> bool:
        token = self._peek()
        if token and token.value.upper() == keyword:
            self._consume()
            return True
        return False

    def _expect_value(self, expected: str):
        token = self._consume()
        if token.value != expected:
            raise QueryParseError(f"'{expected}' bekleniyordu, '{token.value}' alındı.")
        return token

    def parse(self) -> dict:
        ast = self._parse_or()
        if self._peek() is not None:
            token = self._peek()
            raise QueryParseError(f"Beklenmeyen token: '{token.value}'")
        return ast

    def _parse_or(self) -> dict:
        node = self._parse_and()
        while self._accept_keyword("OR"):
            right = self._parse_and()
            node = {"type": "logical", "operator": "OR", "left": node, "right": right}
        return node

    def _parse_and(self) -> dict:
        node = self._parse_factor()
        while self._accept_keyword("AND"):
            right = self._parse_factor()
            node = {"type": "logical", "operator": "AND", "left": node, "right": right}
        return node

    def _parse_factor(self) -> dict:
        token = self._peek()
        if token is None:
            raise QueryParseError("Eksik ifade: karşılaştırma bekleniyordu.")

        if token.value == "(":
            self._consume()
            node = self._parse_or()
            if self._peek() is None:
                raise QueryParseError("Kapanmamış parantez: ')' bekleniyor.")
            self._expect_value(")")
            return node

        return self._parse_comparison()

    def _parse_comparison(self) -> dict:
        field_token = self._consume()
        field_name = field_token.value.lower()
        if field_name.upper() in {"AND", "OR"}:
            raise QueryParseError(f"Alan adı beklenirken '{field_token.value}' bulundu.")
        if field_name not in ALLOWED_QUERY_FIELDS:
            raise QueryParseError(f"Desteklenmeyen alan adı: '{field_token.value}'")

        operator_token = self._consume()
        operator = operator_token.value
        if operator not in ALLOWED_COMPARISON_OPERATORS:
            raise QueryParseError(f"Desteklenmeyen operatör: '{operator}'")

        value_token = self._consume()
        try:
            value = float(value_token.value)
        except ValueError as exc:
            raise QueryParseError(f"Sayısal değer bekleniyordu, '{value_token.value}' alındı.") from exc

        comparison_text = f"{field_name} {operator} {value:g}"
        return {
            "type": "comparison",
            "field": field_name,
            "operator": operator,
            "value": value,
            "text": comparison_text,
        }


def parse_query_expression(query_expression: str) -> dict:
    tokens = tokenize_query_expression(query_expression)
    parser = _Parser(tokens)
    return parser.parse()


def _compare(lhs: float, operator: str, rhs: float) -> bool:
    if operator == "<":
        return lhs < rhs
    if operator == "<=":
        return lhs <= rhs
    if operator == ">":
        return lhs > rhs
    if operator == ">=":
        return lhs >= rhs
    if operator == "=":
        return abs(lhs - rhs) <= 1e-9
    if operator == "!=":
        return abs(lhs - rhs) > 1e-9
    raise QueryParseError(f"Bilinmeyen operatör: {operator}")


def evaluate_query_ast(ast: dict, values: dict[str, float]) -> tuple[bool, list[str], list[str]]:
    node_type = ast.get("type")
    if node_type == "comparison":
        field = ast["field"]
        if field not in values:
            raise QueryParseError(f"Alan değeri bulunamadı: {field}")
        result = _compare(float(values[field]), ast["operator"], float(ast["value"]))
        if result:
            return True, [ast["text"]], [field]
        return False, [], []

    if node_type == "logical":
        left_ok, left_rules, left_fields = evaluate_query_ast(ast["left"], values)
        right_ok, right_rules, right_fields = evaluate_query_ast(ast["right"], values)
        operator = ast["operator"]

        if operator == "AND":
            if left_ok and right_ok:
                return True, left_rules + right_rules, left_fields + right_fields
            return False, [], []
        if operator == "OR":
            if left_ok and right_ok:
                return True, left_rules + right_rules, left_fields + right_fields
            if left_ok:
                return True, left_rules, left_fields
            if right_ok:
                return True, right_rules, right_fields
            return False, [], []
        raise QueryParseError(f"Desteklenmeyen mantıksal operatör: {operator}")

    raise QueryParseError("Geçersiz AST düğümü.")
