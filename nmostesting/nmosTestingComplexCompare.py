# constraint_set schema
#
# {
#   "$schema": "http://json-schema.org/draft-04/schema#",
#   "description": "Describes a Constraint Set",
#   "title": "Constraint Set",
#   "type": "object",
#   "minProperties": 1,
#   "properties": {
#     "urn:x-nmos:cap:meta:label": {
#       "description": "Freeform string label for the Constraint Set",
#       "type": "string"
#     },
#     "urn:x-nmos:cap:meta:preference": {
#       "description": "This value expresses the relative 'weight' that the Receiver assigns to
#          its preference for the streams satisfied by the associated Constraint Set.
#          The weight is an integer in the range -100 through 100,
#          where -100 is least preferred and 100 is most preferred.
#          When the attribute is omitted, the effective value for the associated Constraint Set is 0.",
#       "type": "integer",
#       "default": 0,
#       "maximum": 100,
#       "minimum": -100
#     },
#     "urn:x-nmos:cap:meta:enabled": {
#       "description": "This value indicates whether a Constraint Set is available to use immediately (true)
#         or whether this is an offline capability which can be activated via
#         some unspecified configuration mechanism (false).
#         When the attribute is omitted its value is assumed to be true.",
#       "type": "boolean",
#       "default": true
#     }
#   },
#   "patternProperties": {
#     "^urn:x-nmos:cap:(?!meta:)": {
#       "$ref": "param_constraint.json"
#     }
#   }
# }
#
# We want to compare that two constraint sets are equal based on the properties of teh schema that allow default
# values for properties not defined. For example the "preference" property defined to true or undefined is the
# same such that comparing an object A heving the property set to true and an object B not having the property
# defined will indicate equality because the schema defines a default value.
#
# This function verifies two constraint sets where at most one constraint set is expected and each constraint
# set must have at most one "sample_rate" paremeter constraint. We then compare the two objects based on their
# respective schemas: constraint_set and rational. We expect the constraint to be defined using the "enum"
# keyword with a single array entry.
#
# return true if equal, false otherwise


def compare_complex_sample_rate_constraint(
    response_constraints, sample_rate_constraints
):

    # NOTE: We already know that both response_constraints, sample_rate_constraints are valid
    # and have been each independently been validated against the schemas. We only check equality.

    # Each constraint_sets array must have a single entry
    if len(response_constraints) != 1 or len(sample_rate_constraints) != 1:
        return False

    # If the sample_rate property is not defined, objects are not equivalent
    try:
        response_constraints_enum = response_constraints["constraint_sets"][0][
            "urn:x-nmos:cap:format:sample_rate"
        ]["enum"]
    except Exception:
        return False

    # If the sample_rate property is not defined, objects are not equivalent
    try:
        sample_rate_constraints_enum = sample_rate_constraints["constraint_sets"][0][
            "urn:x-nmos:cap:format:sample_rate"
        ]["enum"]
    except Exception:
        return False

    # There must be a single entry in the enum array
    if len(response_constraints_enum) != 1 or len(sample_rate_constraints_enum) != 1:
        return False

    try:
        response_numerator = response_constraints_enum[0]["numerator"]
        response_denominator = 1

        if "denominator" in response_constraints_enum[0]:
            response_denominator = response_constraints_enum[0]["denominator"]

        sample_rate_numerator = sample_rate_constraints_enum[0]["numerator"]
        sample_rate_denominator = 1

        if "denominator" in sample_rate_constraints_enum[0]:
            sample_rate_denominator = sample_rate_constraints_enum[0]["denominator"]

        if (
            response_numerator != sample_rate_numerator
            or response_denominator != sample_rate_denominator
        ):
            return False
    except Exception:
        return False

    # There must be no other patternProperties
    for prop in sample_rate_constraints["constraint_sets"][0]:
        if (
            prop != "urn:x-nmos:cap:format:sample_rate"
            and prop != "urn:x-nmos:cap:meta:enabled"
            and prop != "urn:x-nmos:cap:meta:preference"
        ):
            return False

    for prop in response_constraints["constraint_sets"][0]:
        if (
            prop != "urn:x-nmos:cap:format:sample_rate"
            and prop != "urn:x-nmos:cap:meta:enabled"
            and prop != "urn:x-nmos:cap:meta:preference"
        ):
            return False

    # Check meta:enabled considering default values
    response_enabled = True
    if "urn:x-nmos:cap:meta:enabled" in response_constraints["constraint_sets"][0]:
        response_enabled = response_constraints["constraint_sets"][0][
            "urn:x-nmos:cap:meta:enabled"
        ]

    sample_rate_enabled = True
    if "urn:x-nmos:cap:meta:enabled" in sample_rate_constraints["constraint_sets"][0]:
        sample_rate_enabled = sample_rate_constraints["constraint_sets"][0][
            "urn:x-nmos:cap:meta:enabled"
        ]

    if response_enabled != sample_rate_enabled:
        return False

    # Check meta:preference considering default values
    response_preference = 0
    if "urn:x-nmos:cap:meta:preference" in response_constraints["constraint_sets"][0]:
        response_preference = response_constraints["constraint_sets"][0][
            "urn:x-nmos:cap:meta:preference"
        ]

    sample_rate_preference = 0
    if (
        "urn:x-nmos:cap:meta:preference"
        in sample_rate_constraints["constraint_sets"][0]
    ):
        sample_rate_preference = sample_rate_constraints["constraint_sets"][0][
            "urn:x-nmos:cap:meta:preference"
        ]

    if response_preference != sample_rate_preference:
        return False

    # If we get here it is because the two objects are equal
    return True


def compare_complex_grain_rate_constraint(response_constraints, grain_rate_constraints):

    # NOTE: We already know that both response_constraints, grain_rate_constraints are valid
    # and have been each independently been validated against the schemas. We only check equality.

    # Each constraint_sets array must have a single entry
    if len(response_constraints) != 1 or len(grain_rate_constraints) != 1:
        return False

    # If the grain_rate property is not defined, objects are not equivalent
    try:
        response_constraints_enum = response_constraints["constraint_sets"][0][
            "urn:x-nmos:cap:format:grain_rate"
        ]["enum"]
    except Exception:
        return False

    # If the grain_rate property is not defined, objects are not equivalent
    try:
        grain_rate_constraints_enum = grain_rate_constraints["constraint_sets"][0][
            "urn:x-nmos:cap:format:grain_rate"
        ]["enum"]
    except Exception:
        return False

    # There must be a single entry in the enum array
    if len(response_constraints_enum) != 1 or len(grain_rate_constraints_enum) != 1:
        return False

    try:
        response_numerator = response_constraints_enum[0]["numerator"]
        response_denominator = 1

        if "denominator" in response_constraints_enum[0]:
            response_denominator = response_constraints_enum[0]["denominator"]

        grain_rate_numerator = grain_rate_constraints_enum[0]["numerator"]
        grain_rate_denominator = 1

        if "denominator" in grain_rate_constraints_enum[0]:
            grain_rate_denominator = grain_rate_constraints_enum[0]["denominator"]

        if (
            response_numerator != grain_rate_numerator
            or response_denominator != grain_rate_denominator
        ):
            return False
    except Exception:
        return False

    # There must be no other patternProperties
    for prop in grain_rate_constraints["constraint_sets"][0]:
        if (
            prop != "urn:x-nmos:cap:format:grain_rate"
            and prop != "urn:x-nmos:cap:meta:enabled"
            and prop != "urn:x-nmos:cap:meta:preference"
        ):
            return False

    for prop in response_constraints["constraint_sets"][0]:
        if (
            prop != "urn:x-nmos:cap:format:grain_rate"
            and prop != "urn:x-nmos:cap:meta:enabled"
            and prop != "urn:x-nmos:cap:meta:preference"
        ):
            return False

    # Check meta:enabled considering default values
    response_enabled = True
    if "urn:x-nmos:cap:meta:enabled" in response_constraints["constraint_sets"][0]:
        response_enabled = response_constraints["constraint_sets"][0][
            "urn:x-nmos:cap:meta:enabled"
        ]

    grain_rate_enabled = True
    if "urn:x-nmos:cap:meta:enabled" in grain_rate_constraints["constraint_sets"][0]:
        grain_rate_enabled = grain_rate_constraints["constraint_sets"][0][
            "urn:x-nmos:cap:meta:enabled"
        ]

    if response_enabled != grain_rate_enabled:
        return False

    # Check meta:preference considering default values
    response_preference = 0
    if "urn:x-nmos:cap:meta:preference" in response_constraints["constraint_sets"][0]:
        response_preference = response_constraints["constraint_sets"][0][
            "urn:x-nmos:cap:meta:preference"
        ]

    grain_rate_preference = 0
    if "urn:x-nmos:cap:meta:preference" in grain_rate_constraints["constraint_sets"][0]:
        grain_rate_preference = grain_rate_constraints["constraint_sets"][0][
            "urn:x-nmos:cap:meta:preference"
        ]

    if response_preference != grain_rate_preference:
        return False

    # If we get here it is because the two objects are equal
    return True
