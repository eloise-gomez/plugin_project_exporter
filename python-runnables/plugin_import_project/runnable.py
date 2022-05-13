import time
import os
import sys
import json
import os.path
import datetime
import dataiku
import dataikuapi

from datetime import datetime
from dataiku.runnables import Runnable
from dataikuapi.utils import DataikuException


class MyRunnable(Runnable):

    def __init__(self, project, config, plugin_config):
        """
        :param project_key: the project in which the runnable executes
        :param config: the dict of the configuration of the object
        :param plugin_config: contains the plugin settings
        """
        self.project = project
        self.config = config
        self.plugin_config = plugin_config

    def get_codenv(self, project, definition, client):
        code_envs = []
        for env_definition in definition:
            if "plugin_" not in env_definition["envName"]:
                local_code_env = client.get_code_env('PYTHON', env_definition["envName"])
                if project in (str(local_code_env.list_usages())):
                    code_envs.append(env_definition)
        return code_envs

    def create_codenv_instance(self, external_code_env, remote_client, local_client):
        # Delete codenv if exists
        try:
            code_env = remote_client.get_code_env('PYTHON', external_code_env['envName'])
            code_env.delete()
        except:
            print("The codenv does not exist")

        code_env_to_create = local_client.get_code_env('PYTHON', external_code_env['envName'])
        pythonInterpreter = code_env_to_create.get_definition()["desc"]["pythonInterpreter"]
        code_env = remote_client.create_code_env('PYTHON', external_code_env['envName'], 'DESIGN_MANAGED', {"pythonInterpreter": pythonInterpreter})

        external_code_env_definition = local_client.get_code_env('PYTHON', external_code_env['envName'])

        packages = external_code_env_definition.get_definition()['specPackageList'].split('\n')
        packages = '\n'.join(map(str, packages))


        # Setup packages to install
        definition = code_env.get_definition()
        definition["desc"]["installCorePackages"] = True
        definition["desc"]["installJupyterSupport"] = True
        # install package
        definition["specPackageList"] = packages
        #Save the new settings
        code_env.set_definition(definition)

        # Actually perform the installation
        code_env.update_packages()
        code_env.set_jupyter_support(True)


    def run(self, progress_callback):
        remote_host = self.config.get("remote_host", "")
        if remote_host == "":
            raise Exception("destination is required")

        remote_apiKey = self.config.get("api_key", "")
        if remote_apiKey == "":
            raise Exception("API key is required")

        project_to_import = self.config.get("project_to_import", "")
        if project_to_import == "":
            raise Exception("Project id is required")

        # use public python api to get access to remote host
        remote_client = dataikuapi.DSSClient(remote_host, remote_apiKey)

        # ignore SSL Certificates if selected
        if self.config.get("ignore_ssl_certs"):
            remote_client._session.verify = False

        html = '<div> Successfully connected to remote host: %s</div>' %(remote_client.host)

        local_client = dataiku.api_client()
        now = datetime.now()
        today = now.strftime("%d-%m-%Y_%H-%M")

        # Get codenv
        definition = local_client.list_code_envs()
        codenvs_to_create = self.get_codenv(project_to_import, definition, local_client)

        # Create codenv
        for codenv in codenvs_to_create:
            self.create_codenv_instance(codenv, remote_client, local_client)

        # Create Bundle on local instance
        project = local_client.get_project(project_to_import)
        project.export_bundle(project_to_import + "_bundle-" + today)
        project.download_exported_bundle_archive_to_file(project_to_import + "_bundle-" + today,
                                                         project_to_import + "_bundle-"+ today+".zip")
        html += "<div> Bundle " + project_to_import + "_bundle-" + today +" was created"

        # Import bundle on remote instance
        if not (os.path.exists(project_to_import + "_bundle-" + today + ".zip")):
            html += "<div> Bundle file named ", project_to_import + "_bundle-" + today +".zip does not exist, cancelling"
            sys.exit(1)

        bundle_file_stream = open(project_to_import + "_bundle-" + today+".zip", 'rb')

        if project_to_import in remote_client.list_project_keys():
            test_project = local_client.get_project(project_to_import)
            test_project.import_bundle_from_stream(bundle_file_stream)
        else:
            remote_client.create_project_from_bundle_archive(bundle_file_stream)
            test_project = remote_client.get_project(project_to_import)

        # Activate Bundle
        latest_bundle = test_project.list_imported_bundles()["bundles"][-1]["bundleId"]
        html += "<div> Using latest bundle defined as " + latest_bundle

        preload_result = test_project.preload_bundle(latest_bundle)
        print("Preload result =", json.dumps(preload_result, indent=4))
        try:
            activation_result = test_project.activate_bundle(latest_bundle)
            html += "<div> Activation result = " + json.dumps(activation_result, indent=4)
        except:
            html += "<div> Exception when activating bundle, cancelling operation"
            sys.exit(1)

        html += '</div>'
        return html
