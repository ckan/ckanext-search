import ckan.plugins as plugins
import ckan.plugins.toolkit as toolkit

from ckanext.search import cli
from ckanext.search.logic import actions, auth
import ckanext.search.schema as search_schema

# TODO: All this whole plugin will eventually live in CKAN core


class SearchPlugin(plugins.SingletonPlugin):
    plugins.implements(plugins.IConfigurer)
    plugins.implements(plugins.IClick)
    plugins.implements(plugins.IActions)
    plugins.implements(plugins.IAuthFunctions)

    # IConfigurer
    def update_config(self, config):

        # TODO: this will be done in core (config/environment.py) for the
        # core entities
        search_schema.reset_search_schemas()
        search_schema.register_search_schema(
            "dataset", search_schema.DEFAULT_DATASET_SEARCH_SCHEMA
        )
        search_schema.register_search_schema(
            "organization",
            search_schema.DEFAULT_ORGANIZATION_SEARCH_SCHEMA,
        )

    # IActions
    def get_actions(self):
        return {"search": actions.search}

    # IAuthFunctions
    def get_auth_functions(self):
        return {"search": auth.search}

    # IClick

    def get_commands(self):
        return cli.get_commands()
