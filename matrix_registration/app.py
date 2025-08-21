import json
import logging
import logging.config
import os

import click
from flask import Flask
from flask.cli import FlaskGroup, pass_script_info
from flask_cors import CORS
from waitress import serve

from . import config
from . import tokens
from .limiter import limiter
from .tokens import db


def create_app(testing=False):
    app = Flask(__name__)
    app.testing = testing

    with app.app_context():
        from .api import api, healthcheck

        app.register_blueprint(api)
        app.register_blueprint(healthcheck)

    limiter.init_app(app)
    return app


@click.group(
    cls=FlaskGroup,
    add_default_commands=False,
    create_app=create_app,
    context_settings=dict(help_option_names=["-h", "--help"]),
)
@click.option("--config-path", help="specifies the config file to be used")
@pass_script_info
def cli(info, config_path):
    """a token based matrix registration app"""
    config.config = config.Config(path=config_path)
    logging.config.dictConfig(config.config.logging)
    app = info.load_app()
    with app.app_context():
        app.config.from_mapping(
            SQLALCHEMY_DATABASE_URI=config.config.db.format(cwd=f"{os.getcwd()}"),
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
        )
        db.init_app(app)
        db.create_all()
        tokens.tokens = tokens.Tokens()


@cli.command("serve", help="start api server")
@pass_script_info
def run_server(info):
    app = info.load_app()
    if config.config.allow_cors:
        CORS(app)
    serve(
        app,
        host=config.config.host,
        port=config.config.port,
        url_prefix=config.config.base_url,
    )


@cli.command("generate", help="generate new token")
@click.option("-m", "--maximum", default=None, help="times token can be used")
@click.option(
    "-e",
    "--expires",
    default=None,
    help="expire date: one of 'never', 'day', 'week', 'month' or ISO-8601 date (YYYY-MM-DD)"
)
def generate_token(maximum, expires):
    if maximum is None:
        maximum = config.config.default_token_maximum
    if expires is None:
        expires = config.config.default_token_expiration
    expireTime = tokens.Token.convert(expires)

    if expireTime is None and expires != "never":
        print(f"expires '{expires}' is not valid. Expected 'never', 'day', 'week', 'month' or ISO-8601 date (YYYY-MM-DD)")
        return -1

    token = tokens.tokens.new(expiration_date=expireTime, max_usage=maximum)
    # print(token.name)

    print(f"Token generated: {token.name}")
    if token.max_usage != 0:
        print(f"With maximum usage: {token.max_usage}")
    else:
        print("With no maximum usage")
    if token.expiration_date is not None:
        print(f"expires at: {token.expiration_date}")
    else:
        print("Never expires")
    print(f"URL: {config.config.registration_url}/register?token={token.name}")


@cli.command("status", help="view status or disable")
@click.option("-s", "--status", default=None, help="token status")
@click.option("-l", "--list", is_flag=True, help="list tokens")
@click.option("-d", "--disable", default=None, help="disable token")
def status_token(status, list, disable):
    if disable:
        if tokens.tokens.disable(disable):
            print("Token disabled")
        else:
            print("Token couldn't be disabled")
    elif status:
        token = tokens.tokens.get_token(status)
        if token:
            print(f"This token is{' ' if token.active() else ' not '}valid")
            print(json.dumps(token.toDict(), indent=2))
        else:
            print("No token with that name")
    elif list:
        print(tokens.tokens)
