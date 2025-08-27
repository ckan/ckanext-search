from typing import Any

from ckan.plugins.toolkit import validator_args

from ckan.types import (
    Schema,
    Validator,
    ValidatorFactory,
    FlattenKey,
    FlattenDataDict,
    FlattenErrorDict,
    Context,
)

from ckan.plugins.toolkit import ValidationError, Invalid, missing
from ckanext.search.filters import parse_query_filters
from ckanext.search.schema import get_search_schema, get_search_schemas


def query_filters_validator(
    key: FlattenKey,
    data: FlattenDataDict,
    errors: FlattenErrorDict,
    context: Context,
) -> Any:

    value = data.get(key)

    entity_type = data.get(("entity_type",))
    if entity_type is missing:
        errors[key] = ["Could not find schema, no entity type provided"]
        return

    search_schema = get_search_schema(entity_type)

    if not search_schema:
        errors[key] = [f"Could not find schema for entity type: {entity_type}"]
        return

    try:
        # TODO: typing
        data[key] = parse_query_filters(value, search_schema)
    except ValidationError as e:
        errors[key] = e.error_dict["filters"]


def known_entity_type(value):

    if value not in get_search_schemas().keys():
        raise Invalid(f"Unknown entity type: {value}")

    return value


@validator_args
def default_search_query_schema(
    not_empty: Validator,
    ignore_missing: Validator,
    ignore_empty: Validator,
    remove_whitespace: Validator,
    unicode_safe: Validator,
    list_of_strings: Validator,
    json_list_or_string: Validator,
    natural_number_validator: Validator,
    convert_to_json_if_string: Validator,
    convert_to_list_if_string: Validator,
    limit_to_configured_maximum: ValidatorFactory,
    default: ValidatorFactory,
) -> Schema:

    return {
        "q": [ignore_missing, unicode_safe],
        "entity_type": [not_empty, known_entity_type, unicode_safe],
        "limit": [
            default(10),
            natural_number_validator,
            limit_to_configured_maximum("ckan.search.rows_max", 1000),
        ],
        "sort": [ignore_missing, json_list_or_string],
        # TODO: index value based ordering
        "start": [default(0), natural_number_validator],
        "filters": [
            ignore_missing,
            convert_to_json_if_string,
            query_filters_validator,
        ],
        "lang": [ignore_missing],
    }
