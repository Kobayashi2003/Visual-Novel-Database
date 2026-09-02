"""Syntax check for the multi-value filter expressions used by search.

A filter value like `Maid,Tsundere+(Comedy,Drama)` combines terms with `,` for OR
and `+` for AND, with parentheses to group. Both the local and the remote filter
builders evaluate such an expression themselves; this module only answers whether
it is well formed, so an invalid one is rejected before either builder runs.

    expression ::= term (',' term)*
    term       ::= factor ('+' factor)*
    factor     ::= '(' expression ')' | TERM
"""

from enum import Enum
import re


# A nesting bound. The grammar is parsed by recursive descent, so depth costs
# Python stack frames: past a few thousand the parse dies with a RecursionError,
# which is not one of the three kinds and surfaces as a `500` for a value the
# caller sent. Nothing legitimate nests anywhere near this.
MAX_NESTING = 64


class TokenizeError(Exception):
    def __init__(self, message: str, position: int):
        self.message = message
        self.position = position
        super().__init__(f"Tokenize error at position {position}: {message}")

class ParserError(Exception):
    def __init__(self, message: str, position: int):
        self.message = message
        self.position = position
        super().__init__(f"Parser error at position {position}: {message}")


class TokenType(Enum):
    LPAREN = '('
    RPAREN = ')'
    AND = '+'
    OR = ','
    TERM = 'term'
    EOF = 'EOF'

class Token:
    def __init__(self, type: TokenType, value: str = None, position: int = 0):
        self.type = type
        self.value = value
        self.position = position

class Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.current = 0
        self.current_token = tokens[0]

    def advance(self) -> Token:
        self.current += 1
        if self.current < len(self.tokens):
            self.current_token = self.tokens[self.current]
        return self.current_token

    def peek(self) -> Token:
        if self.current + 1 < len(self.tokens):
            return self.tokens[self.current + 1]
        return self.tokens[-1]

    def check(self, type: TokenType) -> bool:
        return self.current_token.type == type

    def match(self, type: TokenType) -> Token:
        """Consume the current token, or raise ParserError if it is not `type`."""
        if self.check(type):
            return self.advance()
        raise ParserError(
            f"Expected {type.value}, got {self.current_token.type.value}",
            self.current_token.position
        )

    def validate_expression(self) -> bool:
        """Whether the whole token stream parses. Never raises."""
        try:
            self._validate_expression()
            # Parsing an expression stops at the first token it cannot use, so a
            # trailing "b)" only shows up as input left over at the end.
            if not self.check(TokenType.EOF):
                raise ParserError(
                    f"Unexpected token after expression: {self.current_token.type.value}",
                    self.current_token.position
                )
            return True
        except ParserError:
            return False

    def _validate_expression(self) -> None:
        self._validate_term()

        while self.check(TokenType.OR):
            self.match(TokenType.OR)
            self._validate_term()

    def _validate_term(self) -> None:
        self._validate_factor()

        while self.check(TokenType.AND):
            self.match(TokenType.AND)
            self._validate_factor()

    def _validate_factor(self) -> None:
        if self.check(TokenType.LPAREN):
            self.match(TokenType.LPAREN)
            self._validate_expression()
            self.match(TokenType.RPAREN)
        elif self.check(TokenType.TERM):
            self.match(TokenType.TERM)
        else:
            raise ParserError(
                f"Unexpected token: {self.current_token.type.value}",
                self.current_token.position
            )


def normalize_expression(expression: str) -> str:
    """Strip spaces around the operators and parentheses only — a term is allowed
    to contain spaces, so `Gang Rape + Netorare` must keep the one inside the
    term while losing the ones around `+`."""
    normalized = re.sub(r'\s*\+\s*', '+', expression)
    normalized = re.sub(r'\s*,\s*', ',', normalized)
    normalized = re.sub(r'\s*\(\s*', '(', normalized)
    normalized = re.sub(r'\s*\)\s*', ')', normalized)

    return normalized

def tokenize(expression: str) -> list[Token]:
    """Raises TokenizeError on any character the grammar has no token for."""
    tokens = []
    position = 0

    patterns = {
        'LPAREN': r'\(',
        'RPAREN': r'\)',
        'AND': r'\+',
        'OR': r',',
        'TERM': r'[^\(\)\+,]+',
    }
    pattern = '|'.join(f'(?P<{k}>{v})' for k, v in patterns.items())
    regex = re.compile(pattern)

    for match in regex.finditer(expression):
        token_type = match.lastgroup
        token_value = match.group(token_type)
        start_pos = match.start()

        # finditer skips what it cannot match, so a gap between the last token
        # and this one is the only evidence of an unrecognised character.
        if start_pos > position:
            raise TokenizeError(f"Invalid characters at position {position}", position)

        tokens.append(Token(TokenType[token_type], token_value, start_pos))
        position = match.end()

    if position < len(expression):
        raise TokenizeError(f"Invalid characters at position {position}", position)

    tokens.append(Token(TokenType.EOF, position=len(expression)))
    return tokens

def validate_logical_expression(expression: str) -> bool:
    """The module's entry point: True when `expression` is well formed. Swallows
    both failure modes, so callers get a boolean rather than two exceptions.

    An expression that is blank, or nested deeper than `MAX_NESTING`, is not
    well formed either — the second because the parse would otherwise recurse
    until the interpreter stopped it.
    """
    if not expression or not expression.strip():
        return False
    if expression.count('(') > MAX_NESTING or expression.count(')') > MAX_NESTING:
        return False
    try:
        normalized = normalize_expression(expression)
        tokens = tokenize(normalized)
        parser = Parser(tokens)
        return parser.validate_expression()
    except TokenizeError:
        return False
    except ParserError:
        return False
    except RecursionError:
        return False
