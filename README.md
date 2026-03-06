[![Unit tests](https://github.com/ccs-amsterdam/amcat4/actions/workflows/unittests.yml/badge.svg)](https://github.com/ccs-amsterdam/amcat4/actions/workflows/unittests.yml)
[![Flake8 & Mypy linting](https://github.com/ccs-amsterdam/amcat4/actions/workflows/linting.yml/badge.svg)](https://github.com/ccs-amsterdam/amcat4/actions/workflows/linting.yml)
[![pip version](https://badge.fury.io/py/amcat4.svg)](https://pypi.org/project/amcat4/)
![Python](https://img.shields.io/badge/python-3.10,3.11,3.12,3.13-blue.svg)
![Elasticsearch](https://img.shields.io/badge/elasticsearch-8.17-green)

# AmCAT4

Server for document management and automatic text analysis, developed as part of [OPTED](https://opted.eu).
[Learn more](https://opted.eu/fileadmin/user_upload/k_opted/OPTED_deliverable_D7.1.pdf) See also the [AmCAT book (in progress)](https://amcat.nl/book/02._getting-started).

# Installing AmCAT

The recommended way to install AmCAT either for local use or in a production environment is through docker:

0. [Install docker compose](https://docs.docker.com/compose/install/) if needed
1. Download the [amcat4-deploy.zip](https://github.com/ccs-amsterdam/amcat4/releases/latest/download/amcat4-deploy.zip)
2. Unzip the the archive, creating the amcat4-deploy folder on your computer
3. If needed, edit the .env file (which is based on [.env.example](deploy/.env.example)) for local configuration. For private use, this step can be skipped. For setting up a shared server you certainly want to set up authentication, change the cookie secret, add a https address etc.
4. Run `docker compose up -d`

On linux-like systems, you can also use the commands below to go through these steps:

```{sh}
wget https://github.com/ccs-amsterdam/amcat4/releases/latest/download/amcat4-deploy.zip
unzip amcat4-deploy.zip
cd amcat4-deploy
editor .env   # if needed; replace 'editor' by an editor of your choice
docker compose up -d
```

## General code overview

AmCAT4 is a 'monorepo' containing the code for both the [python FastAPI backend API](backend/) and the [vite react frontend](frontend/). 
The root folder contains a [package.json](package.json) script which contains a number of commands to manage both frontend and backend. 

In production, the front-end is built and statically served. In development, the front-end is dynamically served using vite, which can be started with the various `pnpm` commands listed in the next section.

The backend uses a ElasticSearch document storage as a database. Each project in AmCAT is represented as a single index within elastic. In addition, a number of 'system indices' represent server and project metadata including users, roles, and fields. 

A number of important configuration options for both AmCAT and Elastic are set using a `.env` file, with reasonable defaults for single-user. See [deploy/.env.example](deploy/.env.example) for an overview of options.  

## Development

### Before starting, ensure you have the following installed:

* [Python 3.11+](https://www.python.org/downloads/)
* [Node.js 20+](https://nodejs.org/en)

Once Node.js is installed, run the following command to install pnpm globally:

```
npm install -g pnpm
```

### Install and run AmCAT4 in development mode

The easiest way to install AmCAT4 for local development mode is to use the following commands:

```
# Clone the repo
git clone https://github.com/ccs-amsterdam/amcat4

# Install the monorepo 
pnpm install

# install AmCAT4 in development mode
pnpm dev:install

# TUI for creating AmCAT4 .env file
pnpm dev:config
```

Then we need an ElasticSearch instance, and optionally a SeaweedFS instance. An easy way to fire this up is to use the [deploy/docker-compose.yml](deploy/docker-compose.yml) file with the `dev` profile. The `start:db` command runs this from the root folder, ensuring the root `.env` file is used to configure the elastic:

```
pnpm start:db
```

Then to start the development servers for both the frontend and backend, run

```
pnpm dev      
```

When you stop the dev server, the docker containers will keep running.
To shut them down, run:

```
pnpm stop:db
```


