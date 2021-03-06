import glob
import json
import os
import sys

import click
import yaml
from jinja2 import Environment, FileSystemLoader
from jinja2.exceptions import TemplateSyntaxError

from .exceptions import FormicaArgumentException

LINE_WHITESPACE_OFFSET = '  |'

YAML_FILE_TYPES = ['yml', 'yaml']
JSON_FILE_TYPES = ['json']
FILE_TYPES = YAML_FILE_TYPES + JSON_FILE_TYPES

MODULES_ATTRIBUTE = 'Modules'

try:
    basestring
except NameError:
    basestring = str

ALLOWED_ATTRIBUTES = {
    "AWSTemplateFormatVersion": basestring,
    "Description": basestring,
    "Metadata": dict,
    "Parameters": dict,
    "Mappings": dict,
    "Conditions": dict,
    "Transform": dict,
    "Resources": dict,
    "Outputs": dict,
    MODULES_ATTRIBUTE: list
}


def code_escape(source):
    return source.replace('\n', '\\n').replace('"', '\\"')


def mandatory(a):
    from jinja2.runtime import Undefined

    if isinstance(a, Undefined):
        raise FormicaArgumentException('Mandatory variable not set.')
    return a


def resource(name):
    name = ''.join(e for e in name.title() if e.isalnum())
    return name


class Loader(object):
    def __init__(self, path='.', file='*', variables=None):
        if variables is None:
            variables = {}
        self.cftemplate = {}
        self.path = path
        self.file = file
        self.env = Environment(loader=FileSystemLoader(path))
        self.env.filters.update({
            'code_escape': code_escape,
            'mandatory': mandatory,
            'resource': resource
        })
        self.variables = variables

    def include_file(self, filename, **args):
        source = self.render(filename, **args)
        value = code_escape(source)
        return value

    def render(self, filename, **args):
        return self.env.get_template(filename).render(code=self.include_file, **args)

    def template(self, indent=4, sort_keys=True, separators=(',', ': ')):
        return json.dumps(self.cftemplate, indent=indent, sort_keys=sort_keys, separators=separators)

    def template_dictionary(self):
        return self.cftemplate

    def merge(self, template, file):
        for key in template.keys():
            new = template[key]
            if key in ALLOWED_ATTRIBUTES.keys() and isinstance(new, ALLOWED_ATTRIBUTES[key]):
                if ALLOWED_ATTRIBUTES[key] == basestring:
                    self.cftemplate[key] = new
                elif ALLOWED_ATTRIBUTES[key] == dict:
                    for element in template[key].keys():
                        self.cftemplate.setdefault(key, {})[element] = template[key][element]
                elif key == MODULES_ATTRIBUTE and ALLOWED_ATTRIBUTES[key] == list:
                    for module in template[key]:
                        module_path = module.get('path')
                        file_name = module.get('template', '*')
                        vars = module.get('vars', {})
                        loader = Loader(self.path + '/' + module_path, file_name, vars)
                        loader.load()
                        self.merge(loader.template_dictionary(), file=file_name)
                else:
                    click.echo("Key '{}' in file {} is not valid".format(key, file))
                    sys.exit(1)
            else:
                click.echo("Key '{}' in file {} is not valid".format(key, file))
                sys.exit(1)

    def load(self):
        files = []

        for file_type in FILE_TYPES:
            files.extend(glob.glob('{}/{}.template.{}'.format(self.path, self.file, file_type)))

        if not files:
            click.echo("Could not find any template files in {}".format(self.path))
            sys.exit(1)

        for file in files:
            try:
                result = str(self.render(os.path.basename(file), **self.variables))
            except TemplateSyntaxError as e:
                click.echo(e.__class__.__name__ + ': ' + e.message)
                click.echo(
                    'File: "' + e.filename + '", line ' + str(e.lineno))
                click.echo(LINE_WHITESPACE_OFFSET + e.source.rstrip('\n'))
                sys.exit(1)
            except FormicaArgumentException as e:
                click.echo(e.__class__.__name__ + ': ' + e.args[0])
                click.echo(
                    'For Template: "' + file + '"')
                click.echo('If you use it as a template make sure you\'re setting all necessary vars')
                sys.exit(1)
            if file.endswith(tuple(YAML_FILE_TYPES)):
                template = yaml.load(result)
            elif file.endswith(tuple(JSON_FILE_TYPES)):
                template = json.loads(result)
            else:
                template = {}
            self.merge(template, file)
