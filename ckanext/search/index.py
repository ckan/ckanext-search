import logging
from typing import Optional
from collections.abc import Iterator

from ckan import model

from ckan.plugins import PluginImplementations, SingletonPlugin
from ckan.plugins.toolkit import aslist, config

from ckanext.search.entities import DatasetSearchEntity, OrganizationSearchEntity
from ckanext.search.interfaces import ISearchProvider, ISearchFeature, ISearchEntity
from ckanext.search.schema import (
    get_search_schema,
)

log = logging.getLogger(__name__)


def _get_indexing_providers() -> list:
    indexing_providers = aslist(
        config.get(
            "ckan.search.indexing_provider", config["ckan.search.search_provider"]
        )
    )

    return indexing_providers


def _get_indexing_plugins() -> Iterator[SingletonPlugin]:
    for plugin in PluginImplementations(ISearchProvider):
        if plugin.id in _get_indexing_providers():
            yield plugin


def _get_entity_plugins(entity_type: Optional[str] = None):

    # TODO: make core entities extendable but not registered,
    # similar to DefaultDatasetForm

    entity_plugins = [DatasetSearchEntity(), OrganizationSearchEntity()] + [
        p for p in PluginImplementations(ISearchEntity)
    ]
    if entity_type:
        entity_plugin = [p for p in entity_plugins if p.entity_type() == entity_type]
        if not entity_plugin:
            raise ValueError(f"Unknown search entity type: {entity_type}")

        return entity_plugin

    return entity_plugins


def _index_record(entity_type: str, id_: str, search_data: dict) -> None:

    search_schema = get_search_schema(entity_type)

    for provider_plugin in PluginImplementations(ISearchProvider):
        if provider_plugin.id in _get_indexing_providers():

            for feature_plugin in PluginImplementations(ISearchFeature):
                provider_supported = (
                    provider_plugin.id in feature_plugin.supported_providers()
                )
                entity_type_supported = entity_type in feature_plugin.entity_types()

                if provider_supported and entity_type_supported:

                    feature_plugin.before_index(
                        entity_type, id_, search_data, search_schema
                    )

            provider_plugin.index_search_record(
                entity_type, id_, search_data, search_schema
            )
            log.debug(f"Indexed document of type '{entity_type}' with id '{id_}'")


def rebuild_index(
    entity_type: Optional[str] = None, ids: Optional[list] = None
) -> None:

    entity_plugins = _get_entity_plugins(entity_type)

    for plugin in entity_plugins:
        current_entity_type = plugin.entity_type()
        log.debug(f"Indexing entities of type: {current_entity_type}")
        for record in plugin.fetch_records(current_entity_type, ids):
            _index_record(plugin.entity_type(), record["id"], record)


def clear_index():
    for plugin in PluginImplementations(ISearchProvider):
        if plugin.id in _get_indexing_providers():
            plugin.clear_index()
