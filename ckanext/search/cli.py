import click

from ckanext.search.index import (
    rebuild_index,
    clear_index,
)
from ckanext.search.schema import init_schema


@click.group()
def search():
    """Search utilities for CKAN"""
    pass


@search.command()
@click.argument("entity_type", required=False)
def rebuild(entity_type: str):

    # TODO: hook ISearchEntity here!
    # TODO: wrap in actions

    rebuild_index(entity_type)


@search.command()
@click.option("-f", "--force", default=False, help="Don't prompt for confirmation")
def clear(force):
    msg = "This will delete all entries in the search index. Do you want to proceed?"
    if force or click.confirm(msg, abort=True):
        clear_index()


@search.command()
@click.option("-p", "--provider", help="Search provider to initialize (e.g. solr)")
def init(provider):
    init_schema(provider_id=provider)


def get_commands():

    return [search]
