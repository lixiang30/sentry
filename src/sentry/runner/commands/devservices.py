from __future__ import absolute_import, print_function

import click

from sentry.runner.decorators import configuration


def get_or_create(client, thing, name):
    import docker
    try:
        return getattr(client, thing + 's').get(name)
    except docker.errors.NotFound:
        click.secho("> Creating '%s' %s" % (name, thing), err=True, fg='yellow')
        return getattr(client, thing + 's').create(name)


@click.group()
def devservices():
    """
    Manage dependent development services required for Sentry.

    Do not use in production!
    """


@devservices.command()
@click.option('--project', default='sentry')
@configuration
def up(project):
    "Run/update dependent services."
    import docker
    from django.conf import settings
    client = docker.from_env()

    get_or_create(client, 'network', project)

    containers = {}
    for name, options in settings.SENTRY_DEVSERVICES.items():
        options = options.copy()
        options['network'] = project
        options['detach'] = True
        options['name'] = project + '_' + name
        options.setdefault('ports', {})
        options.setdefault('environment', {})
        options.setdefault('restart_policy', {'Name': 'on-failure'})
        containers[name] = options

    pulled = set()
    for name, options in containers.items():
        for key, value in options['environment'].items():
            options['environment'][key] = value.format(containers=containers)
        if options.pop('pull', False) and options['image'] not in pulled:
            click.secho("> Pulling image '%s'" % options['image'], err=True, fg='green')
            client.images.pull(options['image'])
            pulled.add(options['image'])
        for mount in options.get('volumes', {}).keys():
            if '/' not in mount:
                get_or_create(client, 'volume', project + '_' + mount)
                options['volumes'][project + '_' + mount] = options['volumes'].pop(mount)
        try:
            container = client.containers.get(options['name'])
        except docker.errors.NotFound:
            pass
        else:
            container.stop()
            container.remove()
        click.secho("> Creating '%s' container" % options['name'], err=True, fg='yellow')
        client.containers.run(**options)


@devservices.command()
@click.option('--project', default='sentry')
def down(project):
    "Shut down all services."
    import docker
    from django.conf import settings
    client = docker.from_env()

    prefix = project + '_'

    for container in client.containers.list():
        if container.name.startswith(prefix):
            click.secho("> Removing '%s' container" % container.name, err=True, fg='red')
            container.stop()
            container.remove()


@devservices.command()
@click.option('--project', default='sentry')
def rm(project):
    "Delete all services and associated data."

    click.confirm('Are you sure you want to continue?\nThis will delete all of your Sentry related data!', abort=True)

    import docker
    from django.conf import settings
    client = docker.from_env()

    prefix = project + '_'

    for container in client.containers.list():
        if container.name.startswith(prefix):
            click.secho("> Removing '%s' container" % container.name, err=True, fg='red')
            container.stop()
            container.remove()

    for volume in client.volumes.list():
        if volume.name.startswith(prefix):
            click.secho("> Removing '%s' volume" % volume.name, err=True, fg='red')
            volume.remove()

    try:
        network = client.networks.get(project)
    except docker.errors.NotFound:
        pass
    else:
        click.secho("> Removing '%s' network" % network.name, err=True, fg='red')
        network.remove()
