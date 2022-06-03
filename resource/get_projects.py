import dataiku
import dataikuapi

def do(payload, config, plugin_config, inputs):
    """
    Create list of options of projects in instance.
    """
    local_client = dataiku.api_client()
    projects = local_client.list_projects()
    choices = []
    for project in projects:
        choices.append({"value": project.get('projectKey'), "label": project.get('name')})
    return {"choices": choices}
