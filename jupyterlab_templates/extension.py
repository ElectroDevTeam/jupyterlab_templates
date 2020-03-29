import fnmatch
import json
import os
import os.path
import jupyter_core.paths

from io import open
from datetime import datetime
from notebook.utils import url_path_join
from notebook.base.handlers import IPythonHandler

DATE_FORMAT = "%Y-%m-%d"
TIME_FORMAT = "%H:%M:%S"
DEFAULT_USERNAME = "anonymous"
USERNAME_TEMPLATE = "##username##"
TEMPLATES_TO_FUNCTION = {
    "##datetime##": lambda: datetime.now().strftime(DATE_FORMAT + " " + TIME_FORMAT),
    "##date##": lambda: datetime.now().strftime(DATE_FORMAT),
    "##time##": lambda: datetime.now().strftime(TIME_FORMAT),
}


class TemplatesLoader():
    def __init__(self, template_dirs):
        self.template_dirs = template_dirs

    def get_templates(self, username=DEFAULT_USERNAME):
        templates = {}

        for path in self.template_dirs:
            # in order to produce correct filenames, abspath should point to the parent directory of path
            abspath = os.path.abspath(os.path.join(os.path.realpath(path), os.pardir))
            files = []
            # get all files in subdirectories
            for dirname, dirnames, filenames in os.walk(path):
                if dirname.startswith("."):
                    # Skip hidden paths
                    continue
                for filename in fnmatch.filter(filenames, '*.ipynb'):
                    if '.ipynb_checkpoints' not in dirname:
                        files.append((os.path.join(dirname, filename), dirname.replace(path, ''), filename))
            # pull contents and push into templates list
            for f, dirname, filename in files:
                with open(os.path.join(abspath, f), 'r', encoding='utf8') as fp:
                    content = fp.read()
                templates[os.path.join(dirname, filename)] = {'path': f,
                                                              'dirname': dirname,
                                                              'filename': filename,
                                                              'content': format_content(content, username),
                                                              'username': username}

        return templates


def format_content(content, username):
    formatted_content = content.replace(USERNAME_TEMPLATE, username)
    for pattern, func in TEMPLATES_TO_FUNCTION.items():
        formatted_content = formatted_content.replace(pattern, func())
    return formatted_content


class TemplatesHandler(IPythonHandler):
    def initialize(self, loader):
        self.loader = loader

    def get(self):
        temp = self.get_argument('template', '')
        if temp:
            self.finish(self.loader.get_templates(get_username(self))[temp])
        else:
            self.set_status(404)


class TemplateNamesHandler(IPythonHandler):
    def initialize(self, loader):
        self.loader = loader

    def get(self):
        template_names = self.loader.get_templates(get_username(self)).keys()
        self.finish(json.dumps(sorted(template_names)))


class TemplateTotorialPathHandler(IPythonHandler):
    def initialize(self, totorial_path):
        self.totorial_path = totorial_path

    def get(self):
        self.finish(json.dumps(self.totorial_path))


def get_username(web_handler):
    data = web_handler.get_current_user()
    if data == DEFAULT_USERNAME:
        return data
    return data['name']


def convert_template_to_relative_path(absolute_path, root_dirs):
    for root_dir in root_dirs:
        if os.path.commonpath([absolute_path, root_dir]) == root_dir:
            return absolute_path[len(root_dir) + 1:]


def load_jupyter_server_extension(nb_server_app):
    """
    Called when the extension is loaded.

    Args:
        nb_server_app (NotebookWebApplication): handle to the Notebook webserver instance.
    """
    web_app = nb_server_app.web_app
    template_dirs = nb_server_app.config.get('JupyterLabTemplates', {}).get('template_dirs', [])
    totorial_path = nb_server_app.config.get('JupyterLabTemplates', {}).get('totorial_path')

    if nb_server_app.config.get('JupyterLabTemplates', {}).get('include_default', True):
        template_dirs.append(os.path.join(os.path.dirname(__file__), 'templates'))

    base_url = web_app.settings['base_url']

    host_pattern = '.*$'
    print('Installing jupyterlab_templates handler on path %s' % url_path_join(base_url, 'templates'))

    if nb_server_app.config.get('JupyterLabTemplates', {}).get('include_core_paths', True):
        template_dirs.extend([os.path.join(x, 'notebook_templates') for x in jupyter_core.paths.jupyter_path()])
    print('Search paths:\n\t%s' % '\n\t'.join(template_dirs))

    loader = TemplatesLoader(template_dirs)
    print('Available templates:\n\t%s' % '\n\t'.join(t for t in loader.get_templates()))

    web_app.add_handlers(host_pattern,
                         [(url_path_join(base_url, 'templates/names'), TemplateNamesHandler, {'loader': loader})])
    web_app.add_handlers(host_pattern,
                         [(url_path_join(base_url, 'templates/get'), TemplatesHandler, {'loader': loader})])
    web_app.add_handlers(host_pattern,
                         [(url_path_join(base_url, 'templates/get_totorial_path'), TemplateTotorialPathHandler,
                           {'totorial_path': (convert_template_to_relative_path(totorial_path, template_dirs)
                                              if totorial_path else None)})])
