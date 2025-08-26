from typing import Optional
from ckan.plugins import PluginImplementations
from ckanext.search.interfaces import SearchSchema, ISearchProvider, ISearchFeature


def merge_search_schemas(schemas: list[SearchSchema]) -> SearchSchema:
    """
    Merge multiple search schemas into one, ensuring fields with the same name
    have identical properties.

    Raises ValueError if conflicting field definitions are found.
    """
    if not schemas:
        return {"version": 1, "fields": {}}

    # Use the version from the first schema
    result: SearchSchema = {"version": schemas[0].get("version", 1), "fields": {}}

    for schema in schemas:
        for field_name, field_props in schema.get("fields", {}).items():
            if field_name in result["fields"]:
                # Check if the new field definition matches the existing one
                existing_props = result["fields"][field_name]

                if field_props != existing_props:
                    raise ValueError(
                        f"Conflicting definitions for field '{field_name}': "
                        f"{existing_props} vs {field_props}"
                    )
            else:
                result["fields"][field_name] = field_props

    return result


DEFAULT_DATASET_SEARCH_SCHEMA: SearchSchema = {
    "version": 1,
    "fields": {
        "id": {"type": "string"},
        "entity_type": {"type": "string"},
        "dataset_type": {"type": "string"},
        "name": {"type": "text"},
        "title": {"type": "text"},
        "notes": {"type": "text"},
        "version": {"type": "text"},
        "tags": {"type": "string", "multiple": True},
        "groups": {"type": "string", "multiple": True},
        "owner_org": {"type": "string"},
        "private": {"type": "bool"},
        "metadata_created": {"type": "date"},
        "metadata_modified": {"type": "date"},
        "permission_labels": {"type": "string", "multiple": True},
        "validated_data_dict": {
            "type": "string",
            "indexed": False,
            "stored": True,
        },
        # TODO: nested fields (e.g. resources)
    },
}

DEFAULT_ORGANIZATION_SEARCH_SCHEMA: SearchSchema = {
    "version": 1,
    "fields": {
        "id": {"type": "string"},
        "entity_type": {"type": "string"},
        "organization_type": {"type": "string"},  # TODO: group_type?
        "name": {"type": "text"},
        "title": {"type": "text"},
        "description": {"type": "text"},
        "validated_data_dict": {
            "type": "string",
            "indexed": False,
            "stored": True,
        },
    },
}


def get_search_schema(entity_type: Optional[str] = None) -> SearchSchema:
    search_schemas = [
        DEFAULT_DATASET_SEARCH_SCHEMA,
        DEFAULT_ORGANIZATION_SEARCH_SCHEMA,
    ]

    # TODO: return custom entities
    # TODO: include fields from ISearchFeature plugins (per entity?)
    if entity_type == "dataset":
        return DEFAULT_DATASET_SEARCH_SCHEMA
    elif entity_type == "organization":
        return DEFAULT_ORGANIZATION_SEARCH_SCHEMA
    else:
        return merge_search_schemas(search_schemas)


def init_schema(provider_id: str | None = None):

    from ckanext.search.index import _get_indexing_plugins

    # TODO: combine different entities, schemas provided by extensions

    # TODO: validate with navl

    combined_search_schema = get_search_schema()

    provider_ids = []
    # Search providers set things up first

    if provider_id:
        plugins = [
            plugin
            for plugin in PluginImplementations(ISearchProvider)
            if plugin.id == provider_id
        ]
        provider_ids.append(provider_id)
    else:
        plugins = [plugin for plugin in _get_indexing_plugins()]
        provider_ids = [p.id for p in plugins]

    for plugin in plugins:
        plugin.initialize_search_provider(combined_search_schema, clear=False)

    # Search feature plugins can add things later
    for plugin in PluginImplementations(ISearchFeature):
        if any(
            provider_id in plugin.supported_providers() for provider_id in provider_ids
        ):
            plugin.initialize_search_provider(combined_search_schema, clear=False)
