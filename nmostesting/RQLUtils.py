# Copyright (C) 2026 Advanced Media Workflow Association
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Minimal Resource Query Language (RQL) support for the mock registry Query API."""

import re

SUPPORTED_OPERATORS = frozenset({
    'and', 'or', 'not',
    'eq', 'ne', 'gt', 'ge', 'lt', 'le',
    'in', 'out',
    'matches', 'rel', 'sub',
})

TYPED_VALUE_TYPES = frozenset({
    'string', 'number', 'integer', 'boolean',
    'version', 'api_version', 'rational', 'sampling',
})

SUPPORTED_QUERY_PARAMS = frozenset({
    'query.rql', 'query.downgrade', 'query.strip', 'query.match_type',
})


class RQLParseError(Exception):
    """Raised when an RQL query string cannot be parsed."""


class UnsupportedRQLOperator(RQLParseError):
    """Raised when an RQL operator is not supported by this implementation."""


class RQLParser(object):
    def __init__(self, query):
        self.query = query
        self.length = len(query)
        self.position = 0

    def parse(self):
        self._skip_whitespace()
        if self.position >= self.length:
            raise RQLParseError("Empty RQL query")
        expression = self._parse_value()
        self._skip_whitespace()
        if self.position < self.length:
            raise RQLParseError("Unexpected trailing input in RQL query")
        return expression

    def _peek(self):
        if self.position >= self.length:
            return ''
        return self.query[self.position]

    def _advance(self, count=1):
        self.position += count

    def _skip_whitespace(self):
        while self.position < self.length and self.query[self.position].isspace():
            self.position += 1

    def _expect(self, character):
        self._skip_whitespace()
        if self._peek() != character:
            raise RQLParseError("Expected '{}' in RQL query".format(character))
        self._advance()

    def _parse_identifier(self):
        self._skip_whitespace()
        start = self.position
        while self.position < self.length:
            character = self.query[self.position]
            if character.isalnum() or character in '._:-/':
                self.position += 1
            else:
                break
        if start == self.position:
            raise RQLParseError("Expected identifier in RQL query")
        return self.query[start:self.position]

    def _parse_quoted_string(self):
        quote = self._peek()
        self._advance()
        start = self.position
        while self.position < self.length and self.query[self.position] != quote:
            if self.query[self.position] == '\\' and self.position + 1 < self.length:
                self.position += 2
            else:
                self.position += 1
        if self.position >= self.length:
            raise RQLParseError("Unterminated string in RQL query")
        value = self.query[start:self.position]
        self._advance()
        return value

    def _parse_parenthesized_list(self, parse_item):
        self._expect('(')
        items = []
        self._skip_whitespace()
        if self._peek() != ')':
            items.append(parse_item())
            while True:
                self._skip_whitespace()
                if self._peek() != ',':
                    break
                self._advance()
                items.append(parse_item())
        self._expect(')')
        return items

    def _parse_tuple(self):
        return self._parse_parenthesized_list(self._parse_atom)

    def _parse_atom(self):
        self._skip_whitespace()
        character = self._peek()
        if character in '"\'':
            return self._parse_quoted_string()
        if character == '(':
            return self._parse_tuple()
        return _literal_from_identifier(self._parse_identifier())

    def _parse_call(self):
        operator_name = self._parse_identifier()
        if operator_name not in SUPPORTED_OPERATORS:
            raise UnsupportedRQLOperator(operator_name)
        arguments = self._parse_parenthesized_list(self._parse_value)
        return {'name': operator_name, 'args': arguments}

    def _parse_value(self):
        self._skip_whitespace()
        character = self._peek()
        if character in '"\'':
            return self._parse_quoted_string()
        if character == '(':
            return self._parse_tuple()

        identifier_start = self.position
        identifier = self._parse_identifier()
        self._skip_whitespace()
        if self._peek() == '(':
            self.position = identifier_start
            return self._parse_call()
        return _literal_from_identifier(identifier)


def _typed_value_from_identifier(identifier):
    colon_index = identifier.find(':')
    if colon_index <= 0:
        return None
    type_name = identifier[:colon_index]
    if type_name not in TYPED_VALUE_TYPES:
        return None
    return {'type': type_name, 'value': identifier[colon_index + 1:]}


def _literal_from_identifier(identifier):
    if identifier == 'true':
        return True
    if identifier == 'false':
        return False
    if identifier == 'null':
        return None
    typed_value = _typed_value_from_identifier(identifier)
    if typed_value is not None:
        return typed_value
    try:
        if '.' in identifier:
            return float(identifier)
        return int(identifier)
    except ValueError:
        return identifier


def _is_typed_value(value):
    return isinstance(value, dict) and 'type' in value and 'value' in value


def _unwrap_value(value):
    if _is_typed_value(value):
        return value['value']
    return value


def _resolve_related_resource(relation_name, relation_id, all_resources):
    if all_resources is None or relation_id is None:
        return None

    relation_property_name = relation_name.rsplit('.', 1)[-1]
    if not relation_property_name.endswith('_id'):
        return None

    return all_resources.get(relation_property_name[:-3], {}).get(str(relation_id))


def parse_query(query_string):
    return RQLParser(query_string).parse()


def extract_property_values(resource, property_path):
    """Return all values reachable via a dot-separated property path."""
    if resource is None:
        return []

    current_values = [resource]
    for part in property_path.split('.'):
        next_values = []
        for value in current_values:
            if isinstance(value, dict):
                if part in value:
                    next_values.append(value[part])
            elif isinstance(value, list):
                for element in value:
                    if isinstance(element, dict) and part in element:
                        next_values.append(element[part])
                    elif not isinstance(element, dict) and part == '':
                        next_values.append(element)
        current_values = next_values

    flattened_values = []
    for value in current_values:
        if isinstance(value, list):
            flattened_values.extend(value)
        else:
            flattened_values.append(value)
    return flattened_values


def _grain_rate_from_rational_string(rational_string):
    if '/' in rational_string:
        numerator_string, denominator_string = rational_string.split('/', 1)
        return {
            'numerator': int(numerator_string),
            'denominator': int(denominator_string),
        }
    return {'numerator': int(rational_string), 'denominator': 1}


def _normalize_grain_rate(value):
    if value is None:
        return None
    if _is_typed_value(value) and value['type'] == 'rational':
        return _grain_rate_from_rational_string(value['value'])
    if isinstance(value, dict) and 'numerator' in value and 'denominator' in value:
        return value
    if isinstance(value, str):
        try:
            return _grain_rate_from_rational_string(value)
        except ValueError:
            return None
    return None


def _values_equal(left, right):
    if left is None or right is None:
        return left is right
    if isinstance(left, bool) or isinstance(right, bool):
        return left is right

    left_grain_rate = _normalize_grain_rate(left)
    right_grain_rate = _normalize_grain_rate(right)
    if left_grain_rate is not None and right_grain_rate is not None:
        if (left_grain_rate['numerator'] * right_grain_rate['denominator']
                == right_grain_rate['numerator'] * left_grain_rate['denominator']):
            return True

    if type(left) is not type(right):
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            return left == right
        return str(left) == str(right)
    return left == right


def _string_matches_pattern(target, pattern, ignore_case):
    if not isinstance(target, str):
        return False
    flags = re.IGNORECASE if ignore_case else 0
    try:
        return re.search(pattern, target, flags) is not None
    except re.error as error:
        raise RQLParseError("Invalid regular expression in matches(): {}".format(error))


def evaluate_query(expression, resource, all_resources=None):
    if isinstance(expression, dict):
        operator_name = expression['name']
        arguments = expression['args']

        if operator_name == 'and':
            return all(evaluate_query(argument, resource, all_resources) for argument in arguments)
        if operator_name == 'or':
            return any(evaluate_query(argument, resource, all_resources) for argument in arguments)
        if operator_name == 'not':
            return not evaluate_query(arguments[0], resource, all_resources)

        if operator_name == 'matches':
            property_path = arguments[0]
            if not isinstance(property_path, str):
                raise RQLParseError("Property path must be a string")
            pattern = str(_unwrap_value(arguments[1]))
            ignore_case = len(arguments) > 2 and _unwrap_value(arguments[2]) == 'i'
            property_values = extract_property_values(resource, property_path)
            return any(
                _string_matches_pattern(str(property_value), pattern, ignore_case)
                for property_value in property_values
            )

        if operator_name == 'rel':
            relation_name = arguments[0]
            if not isinstance(relation_name, str):
                raise RQLParseError("Relation name must be a string")
            subquery = arguments[1]
            relation_values = extract_property_values(resource, relation_name)
            for relation_value in relation_values:
                related_resource = _resolve_related_resource(
                    relation_name, _unwrap_value(relation_value), all_resources)
                if related_resource and evaluate_query(subquery, related_resource, all_resources):
                    return True
            return False

        if operator_name == 'sub':
            property_path = arguments[0]
            if not isinstance(property_path, str):
                raise RQLParseError("Property path must be a string")
            subquery = arguments[1]
            sub_resources = extract_property_values(resource, property_path)
            if not sub_resources:
                return False
            return any(
                evaluate_query(subquery, sub_resource, all_resources)
                for sub_resource in sub_resources
                if isinstance(sub_resource, dict)
            )

        if operator_name in ('eq', 'ne', 'gt', 'ge', 'lt', 'le', 'in', 'out'):
            property_path = arguments[0]
            if not isinstance(property_path, str):
                raise RQLParseError("Property path must be a string")
            comparison_value = arguments[1] if _is_typed_value(arguments[1]) else _unwrap_value(arguments[1])
            property_values = extract_property_values(resource, property_path)
            if not property_values:
                if operator_name == 'eq' and comparison_value is None:
                    return True
                if operator_name == 'in' and isinstance(arguments[1], list):
                    return any(candidate is None for candidate in arguments[1])
                return False

            if operator_name in ('in', 'out'):
                if not isinstance(arguments[1], list):
                    raise RQLParseError("{}() requires a tuple argument".format(operator_name))
                if operator_name == 'in':
                    return any(
                        _values_equal(property_value, candidate)
                        for property_value in property_values
                        for candidate in arguments[1]
                    )
                return all(
                    not any(_values_equal(property_value, candidate) for candidate in arguments[1])
                    for property_value in property_values
                )

            return any(
                _evaluate_relation(operator_name, property_value, comparison_value)
                for property_value in property_values
            )

    raise RQLParseError("Invalid RQL expression")


def _evaluate_relation(operator_name, left, right):
    if operator_name == 'eq':
        return _values_equal(left, right)
    if operator_name == 'ne':
        return not _values_equal(left, right)

    if type(left) is not type(right):
        try:
            left = float(left)
            right = float(right)
        except (TypeError, ValueError):
            left = str(left)
            right = str(right)

    if operator_name == 'gt':
        return left > right
    if operator_name == 'ge':
        return left >= right
    if operator_name == 'lt':
        return left < right
    if operator_name == 'le':
        return left <= right
    return False


def resource_matches_query_params(resource, query_params, all_resources=None, rql_expression=None):
    """Return True when resource satisfies basic and/or RQL query parameters."""
    if resource is None:
        return False

    for parameter_name, parameter_value in query_params.items():
        if parameter_name.startswith('paging.'):
            continue
        if parameter_name == 'id' or parameter_name == 'transport':
            continue
        if parameter_name.startswith('query.'):
            if parameter_name == 'query.rql':
                expression = rql_expression if rql_expression is not None else parse_query(parameter_value)
                if not evaluate_query(expression, resource, all_resources):
                    return False
            elif parameter_name in SUPPORTED_QUERY_PARAMS:
                continue
            else:
                raise UnsupportedRQLOperator(parameter_name)
        else:
            property_values = extract_property_values(resource, parameter_name)
            if not property_values or not any(
                    _values_equal(property_value, parameter_value) for property_value in property_values):
                return False

    return True


def has_unsupported_query_params(query_params):
    for parameter_name in query_params:
        if not parameter_name.startswith('query.'):
            continue
        if parameter_name in SUPPORTED_QUERY_PARAMS:
            continue
        return True
    return False
