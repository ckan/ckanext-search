from ckan.plugins import PluginImplementations
from ckanext.search.interfaces import SearchSchema, ISearchProvider, ISearchFeature


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


_search_schemas: dict[str, SearchSchema] = {}


def reset_search_schemas() -> None:

    global _search_schemas

    _search_schemas = {}


def register_search_schema(name: str, schema: SearchSchema) -> None:

    global _search_schemas

    _search_schemas[name] = schema


def get_search_schema(entity_type: str) -> SearchSchema:

    global _search_schemas

    # TODO: return custom entities
    # TODO: include fields from ISearchFeature plugins (per entity?)
    if entity_type not in _search_schemas:
        # TODO: custom exception
        raise ValueError(f"Unknown search entity type: {entity_type}")

    return _search_schemas[entity_type]


def get_search_schemas() -> dict[str, SearchSchema]:

    global _search_schemas

    return _search_schemas


def init_schema(provider_id: str | None = None):

    from ckanext.search.index import _get_indexing_plugins

    # TODO: combine different entities, schemas provided by extensions

    # TODO: validate with navl

    search_schemas = get_search_schemas()

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
        plugin.initialize_search_provider(search_schemas, clear=False)

    # Search feature plugins can add things later
    for plugin in PluginImplementations(ISearchFeature):
        if any(
            provider_id in plugin.supported_providers() for provider_id in provider_ids
        ):
            plugin.initialize_search_provider(search_schemas, clear=False)
