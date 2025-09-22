# This will eventually live in ckan/logic/action/get.py

from ckan.lib.plugins import get_permission_labels
from ckan.plugins import PluginImplementations
from ckan.plugins.toolkit import (
    check_access,
    config,
    get_or_bust,
    side_effect_free,
    navl_validate,
    ValidationError,
)
from ckan.types import Context, DataDict
from ckanext.search.interfaces import ISearchProvider, ISearchFeature, ISearchEntity
from ckanext.search.schema import get_search_schema
from ckanext.search.logic.schema import default_search_query_schema
from ckanext.search.filters import FilterOp
from ckanext.search.index import _get_entity_plugins


@side_effect_free
def search(context: Context, data_dict: DataDict):

    check_access("search", context, data_dict)

    schema = default_search_query_schema()

    entity_type = get_or_bust(data_dict, "entity_type")

    additional_params_schema = {}
    # Allow search providers to add custom params
    for plugin in PluginImplementations(ISearchProvider):
        additional_params_schema.update(plugin.search_query_schema())

    # Allow search extensions to add custom params
    for plugin in PluginImplementations(ISearchFeature):
        additional_params_schema.update(plugin.search_query_schema())

    # Allow search entities to add custom params
    for plugin in _get_entity_plugins():
        if plugin.entity_type() == entity_type:
            additional_params_schema.update(plugin.search_query_schema())

    # Any fields not in the default schema are moved to additional_params
    default_query_fields = schema.keys()

    query_dict = {}
    additional_params = {}

    for param in data_dict.keys():
        if param in default_query_fields:
            query_dict[param] = data_dict[param]
        else:
            additional_params[param] = data_dict[param]

    # Validate common params
    query_dict, errors = navl_validate(query_dict, schema, context)
    if errors:
        raise ValidationError(errors)

    # Validate additional params
    additional_params, errors = navl_validate(
        additional_params, additional_params_schema, context
    )
    if errors:
        raise ValidationError(errors)
    elif "__extras" in additional_params:
        unknown_params = ", ".join(additional_params["__extras"].keys())
        raise ValidationError({"message": f"Unknown parameters: {unknown_params}"})

    query_dict["additional_params"] = additional_params

    # Make sure all default query params are present
    query_dict.update({k: None for k in default_query_fields if k not in query_dict})

    # Allow search extensions to modify the query params
    for plugin in PluginImplementations(ISearchFeature):
        plugin.before_query(query_dict, context)

    # Allow search entities to modify the query params
    for plugin in _get_entity_plugins():
        if plugin.entity_type() == entity_type:
            plugin.before_query(query_dict, context)

    # This is valid and a search schema exists for it
    entity_type = query_dict["entity_type"]

    search_schema = get_search_schema(entity_type)
    query_dict["search_schema"] = search_schema
    search_provider = config["ckan.search.search_provider"]

    result = {}
    for plugin in PluginImplementations(ISearchProvider):
        if plugin.id == search_provider:
            result = plugin.search_query(**query_dict)
            break
    query_dict.pop("search_schema")

    # TODO: pass search_schema here
    # Allow search extensions to modify the query results
    for plugin in PluginImplementations(ISearchFeature):
        plugin.after_query(result, query_dict)

    # TODO
    # if context.get('for_view'):
    #    for item in plugins.PluginImplementations(
    #        plugins.IPackageController):
    #    package_dict = item.before_dataset_view(
    #        package_dict)

    return result
